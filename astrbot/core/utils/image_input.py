"""Prepare current local-agent images and generate their original-path notices."""

from pathlib import Path

from astrbot.core.agent.message import ImageURLPart, TextPart
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.media_utils import (
    MODEL_IMAGE_MAX_INPUT_BYTES,
    ImageInputTooLargeError,
    describe_media_ref,
    prepare_model_image,
)
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings


async def prepare_request_images(
    req: ProviderRequest,
    event: AstrMessageEvent,
    *,
    max_size: int,
    output_dir: Path | None = None,
    prepared: dict[str, dict],
    quote_image_ref: str | None = None,
    quoted_refs: set[str] | None = None,
    captioned_refs: set[str] | None = None,
    finalize: bool = True,
    supports_image: bool = True,
) -> None:
    """Prepare new references and generate notices from actual processing results.

    Args:
        req: Working request; shared lists and image blocks are copied on write.
        event: Owner of prepared working files.
        max_size: Normalized longest-edge limit for this request.
        output_dir: Event working file directory, defaulting to AstrBot temp.
        prepared: Request-local cache of paths, processing outcomes, and owned
            notice objects. Original and prepared references share each result.
        quote_image_ref: Optional input for the dedicated quote caption branch.
        quoted_refs: References collected directly from quoted message components.
        captioned_refs: References successfully described by a caption provider.
        finalize: Generate notices after captioning or the request hook finishes.
        supports_image: Whether the final provider accepts visual input.
    """
    output_dir = output_dir if output_dir is not None else Path(get_astrbot_temp_path())
    req.image_urls = normalize_and_dedupe_strings(req.image_urls)
    refs = list(req.image_urls)
    persistent_refs = set(refs)
    for part in req.extra_user_content_parts:
        if isinstance(part, ImageURLPart):
            refs.append(part.image_url.url)
            if not part._no_save:
                persistent_refs.add(part.image_url.url)
        elif isinstance(part, dict) and part.get("type") == "image_url":
            refs.append(part["image_url"]["url"])
            if not part.get("_no_save"):
                persistent_refs.add(part["image_url"]["url"])
    if quote_image_ref:
        refs.append(quote_image_ref)
        persistent_refs.add(quote_image_ref)

    for ref in dict.fromkeys(refs):
        if ref in prepared:
            if ref in persistent_refs:
                prepared[ref]["temporary"] = False
            continue
        path = None
        original_path = describe_media_ref(ref)
        status = None
        is_montage = False
        try:
            image = await prepare_model_image(
                ref, max_size=max_size, output_dir=output_dir
            )
        except ImageInputTooLargeError as exc:
            image = None
            original_path = str(exc)
            status = "oversized"
        if image:
            path, is_montage, needs_cleanup, original_path = image
            if needs_cleanup:
                event.track_temporary_local_file(path)
        elif status is None:
            status = "unavailable"
        result = {
            "path": path,
            "original_path": original_path,
            "quoted": ref == quote_image_ref or ref in (quoted_refs or ()),
            "montage": is_montage,
            "status": status,
            "temporary": ref not in persistent_refs,
            "notices": [],
        }
        prepared[ref] = result
        if path:
            prepared[path] = result

    for ref in captioned_refs or ():
        if ref in prepared:
            prepared[ref]["status"] = "captioned"

    req.image_urls = normalize_and_dedupe_strings(
        [prepared[ref]["path"] for ref in req.image_urls if prepared[ref]["path"]]
    )
    parts = []
    visuals = []
    for part in req.extra_user_content_parts:
        if isinstance(part, ImageURLPart):
            result = prepared[part.image_url.url]
            path = result["path"]
            if path is None:
                continue
            part = part.model_copy(
                update={"image_url": part.image_url.model_copy(update={"url": path})}
            )
            visuals.append((result, part._no_save))
        elif isinstance(part, dict) and part.get("type") == "image_url":
            result = prepared[part["image_url"]["url"]]
            path = result["path"]
            if path is None:
                continue
            part = {**part, "image_url": {**part["image_url"], "url": path}}
            visuals.append((result, bool(part.get("_no_save"))))
        parts.append(part)
    visuals.extend((prepared[path], False) for path in req.image_urls)
    req.extra_user_content_parts = parts
    if refs and not visuals and not (req.prompt or "").strip() and not req.audio_urls:
        if not any(
            (part.get("type") != "text" or part.get("text", "").strip())
            if isinstance(part, dict)
            else (part.type != "text" or part.text.strip())
            for part in parts
        ):
            req.prompt = "[Image unavailable]"
    if not finalize:
        return

    results = list({id(result): result for result in prepared.values()}.values())
    # Only replace objects produced by this request. Plugin text is never parsed
    # or removed, even when it is identical to one of our notices.
    owned = {id(part) for result in results for part in result["notices"]}
    parts = [part for part in parts if id(part) not in owned]
    for result in results:
        result["notices"] = []

    if not supports_image:
        visuals = []
    active = {id(result) for result, _ in visuals}
    rows = [
        (result, None, result["temporary"])
        for result in results
        if id(result) not in active
    ]
    # Extra image parts precede image_urls in the provider's visual order.
    rows.extend(
        (result, index, temporary)
        for index, (result, temporary) in enumerate(visuals, 1)
    )
    oversized = None
    montage = None
    for result, index, temporary in rows:
        name = f"Image {index}" if index is not None else "Image Attachment"
        origin = " in quoted message" if result["quoted"] else ""
        status = ""
        if index is not None:
            if result["montage"]:
                status = "; animation converted to a 3x3 frame montage"
                montage = result
        elif result["status"] == "oversized":
            status = (
                f"; skipped: exceeds {MODEL_IMAGE_MAX_INPUT_BYTES // (1024 * 1024)} MiB"
            )
            oversized = result
        elif result["status"] == "unavailable":
            status = "; skipped: image unavailable"
        elif result["status"] == "captioned":
            status = "; sent to image-captioning model; description included as text"
        else:
            status = "; not included in this request"
        label = TextPart(
            text=f"[{name}{origin}: original path {result['original_path']}{status}]"
        )
        if temporary:
            label.mark_as_temp()
        result["notices"].append(label)
        parts.append(label)
    if oversized is not None:
        advice = TextPart(
            text="<system_notice>\n"
            "For skipped images, use astrbot_file_read_tool if available, "
            "or ask the user to resend a smaller image.\n"
            "</system_notice>"
        ).mark_as_temp()
        oversized["notices"].append(advice)
        parts.append(advice)
    if montage is not None:
        advice = TextPart(
            text="<system_notice>\n"
            "Images labeled as animation montages contain frames in reading order. "
            "Treat them as animations; do not mention the conversion or frame layout.\n"
            "</system_notice>"
        ).mark_as_temp()
        montage["notices"].append(advice)
        parts.append(advice)
    req.extra_user_content_parts = parts
