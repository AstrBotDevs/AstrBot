"""Prepare current local-agent input; history and tool results are not inputs here."""

from pathlib import Path

from astrbot.core import logger
from astrbot.core.agent.message import ImageURLPart
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.media_utils import (
    MediaResolver,
    is_recoverable_image_error,
    prepare_model_image,
)
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings


async def prepare_request_images(
    req: ProviderRequest,
    event: AstrMessageEvent,
    *,
    enabled: bool,
    max_size: int,
    output_dir: Path,
    prepared: dict[str, str | None],
    quote_image_ref: str | None = None,
) -> None:
    """Replace current images on a working request and track their owned files.

    Args:
        req: Working request; shared lists and image blocks are copied on write.
        event: Owner of downloaded source files and prepared working files.
        enabled: Whether the current pipeline profile enables PNG preparation.
        max_size: Normalized longest-edge limit for this request.
        output_dir: Event working file directory, separate from the shared cache.
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
    for ref in dict.fromkeys(refs):
        if ref not in prepared:
            path = None
            if enabled:
                path = await prepare_model_image(
                    ref, max_size=max_size, output_dir=output_dir
                )
                if path:
                    event.track_temporary_local_file(path)
            else:
                try:
                    async with MediaResolver(
                        ref, media_type="image"
                    ).as_path() as source:
                        # Transfer only resolver-owned downloads, never user files.
                        if not source.path.is_file():
                            raise FileNotFoundError("Image source is unavailable")
                        path = str(source.path.resolve())
                        for owned_path in source.cleanup_paths:
                            event.track_temporary_local_file(str(owned_path))
                        source.detach()
                except Exception as exc:
                    if not is_recoverable_image_error(exc):
                        raise
                    logger.warning(
                        "Image localization failed; skipping image (%s).",
                        type(exc).__name__,
                    )
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
