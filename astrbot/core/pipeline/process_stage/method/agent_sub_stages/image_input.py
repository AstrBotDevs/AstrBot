"""Prepare current local-agent input; history and tool results are not inputs here."""

from pathlib import Path

from astrbot.core.agent.message import ImageURLPart, TextPart
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.media_utils import prepare_model_image
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings


async def prepare_request_images(
    req: ProviderRequest,
    event: AstrMessageEvent,
    *,
    max_size: int,
    output_dir: Path,
    prepared: dict[str, str | None],
    quote_image_ref: str | None = None,
) -> None:
    """Replace current images on a working request and track their owned files.

    Args:
        req: Working request; shared lists and image blocks are copied on write.
        event: Owner of downloaded source files and prepared working files.
        max_size: Normalized longest-edge limit for this request.
        output_dir: Event working file directory.
        prepared: Per-request mapping reused after the request hook.
        quote_image_ref: Optional input for the dedicated quote caption branch.
    """
    req.image_urls = normalize_and_dedupe_strings(req.image_urls)
    refs = list(req.image_urls)
    for part in req.extra_user_content_parts:
        if isinstance(part, ImageURLPart):
            refs.append(part.image_url.url)
        elif isinstance(part, dict) and part.get("type") == "image_url":
            refs.append(part["image_url"]["url"])
    if quote_image_ref:
        refs.append(quote_image_ref)
    failed = False
    has_montage = False
    for ref in dict.fromkeys(refs):
        if ref not in prepared:
            path = None
            image = await prepare_model_image(
                ref,
                max_size=max_size,
                output_dir=output_dir,
            )
            if image:
                path, is_montage = image
                event.track_temporary_local_file(path)
                has_montage |= is_montage
            prepared[ref] = path
            if path:
                prepared[path] = path
        failed |= prepared[ref] is None

    req.image_urls = normalize_and_dedupe_strings(
        [prepared[ref] for ref in req.image_urls if prepared[ref] is not None]
    )
    parts = []
    for part in req.extra_user_content_parts:
        if isinstance(part, ImageURLPart):
            path = prepared[part.image_url.url]
            if path is None:
                continue
            part = part.model_copy(
                update={"image_url": part.image_url.model_copy(update={"url": path})}
            )
        elif isinstance(part, dict) and part.get("type") == "image_url":
            path = prepared[part["image_url"]["url"]]
            if path is None:
                continue
            part = {**part, "image_url": {**part["image_url"], "url": path}}
        parts.append(part)
    req.extra_user_content_parts = parts
    if (
        failed
        and not (req.prompt or "").strip()
        and not req.image_urls
        and not req.audio_urls
    ):
        if not any(
            (part.get("type") != "text" or part.get("text", "").strip())
            if isinstance(part, dict)
            else (part.type != "text" or part.text.strip())
            for part in parts
        ):
            req.prompt = "[Image unavailable]"

    if has_montage:
        # Transient per-request hint; the montage file itself is not persisted.
        req.extra_user_content_parts = [
            *req.extra_user_content_parts,
            TextPart(
                text="<system_notice>\n"
                "The input includes a GIF converted into a single image with frames "
                "in reading order. Treat it as an animation; "
                "do not mention the conversion or frame layout.\n"
                "</system_notice>"
            ).mark_as_temp(),
        ]
