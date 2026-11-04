"""Quoted content, media attachment descriptions, and image captioning."""

from __future__ import annotations

from pathlib import Path

from astrbot.core import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import Reply, Video
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.utils.quoted_message.settings import (
    SETTINGS as DEFAULT_QUOTED_MESSAGE_SETTINGS,
)
from astrbot.core.utils.quoted_message.settings import (
    QuotedMessageParserSettings,
)
from astrbot.core.utils.quoted_message_parser import (
    extract_quoted_message_text,
)

ANIMATION_CAPTION_NOTICE = (
    "\n<system_notice>\n"
    "Input images at positions {indices} (1-based) are animations (e.g. GIFs), "
    "each converted to a single image of frames in reading order. "
    "Describe them as animations, including motion or changes; "
    "do not mention the conversion or frame layout.\n"
    "</system_notice>"
)


async def _request_img_caption(
    provider_id: str,
    cfg: dict,
    image_urls: list[str],
    plugin_context: Context,
    montage_refs: set[str] | None = None,
) -> str:
    """Describe prepared images, preserving animation semantics.

    Args:
        provider_id: Caption provider ID.
        cfg: Provider settings containing the caption prompt.
        image_urls: Prepared images in their input order.
        plugin_context: Services used to resolve the caption provider.
        montage_refs: Prepared paths containing animation frame montages.

    Returns:
        The generated image description.

    Raises:
        ValueError: If the caption provider is missing or invalid.
    """
    prov = plugin_context.get_provider_by_id(provider_id)
    if prov is None:
        raise ValueError(
            f"Cannot get image caption because provider `{provider_id}` is not exist.",
        )
    if not isinstance(prov, Provider):
        raise ValueError(
            f"Cannot get image caption because provider `{provider_id}` is not a valid Provider, it is {type(prov)}.",
        )

    img_cap_prompt = cfg.get(
        "image_caption_prompt",
        "Please describe the image.",
    )
    montage_indices = [
        str(index)
        for index, ref in enumerate(image_urls, start=1)
        if ref in (montage_refs or ())
    ]
    if montage_indices:
        img_cap_prompt += ANIMATION_CAPTION_NOTICE.format(
            indices=", ".join(montage_indices)
        )
    logger.debug("Processing image caption with provider: %s", provider_id)
    llm_resp = await prov.text_chat(
        prompt=img_cap_prompt,
        image_urls=image_urls,
    )
    return llm_resp.completion_text


async def caption_request_images(
    event: AstrMessageEvent,
    req: ProviderRequest,
    cfg: dict,
    plugin_context: Context,
    image_caption_provider: str,
    montage_refs: set[str] | None = None,
) -> set[str]:
    """Append a caption and return the references actually described.

    Args:
        event: Current event.
        req: Request whose image_urls will be replaced with a text description.
        cfg: Provider settings for caption generation.
        plugin_context: Services used to resolve the caption provider.
        image_caption_provider: Configured caption provider ID.
        montage_refs: Prepared paths containing animation frame montages.

    Returns:
        Successfully described image references, or an empty set on failure.
    """
    image_refs = set(req.image_urls)
    try:
        caption = await _request_img_caption(
            image_caption_provider,
            cfg,
            req.image_urls,
            plugin_context,
            montage_refs=montage_refs,
        )
        if caption:
            req.extra_user_content_parts.append(
                TextPart(text=f"<image_caption>{caption}</image_caption>")
            )
            return image_refs
    except Exception as exc:  # noqa: BLE001
        logger.error("Image captioning failed: %s", exc)
        req.extra_user_content_parts.append(TextPart(text="[Image Captioning Failed]"))
    finally:
        req.image_urls = []
    return set()


def append_audio_attachment(req: ProviderRequest, audio_path: str) -> None:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Audio Attachment: path {audio_path}]")
    )


def append_quoted_audio_attachment(req: ProviderRequest, audio_path: str) -> None:
    req.extra_user_content_parts.append(
        TextPart(text=f"[Audio Attachment in quoted message: path {audio_path}]")
    )


async def append_video_attachment(
    req: ProviderRequest,
    video: Video,
    *,
    quoted: bool = False,
) -> None:
    try:
        video_path = await video.convert_to_file_path()
    except Exception as exc:  # noqa: BLE001
        if quoted:
            logger.debug(
                "Quoted video attachment is not locally resolvable, preserving ref: %s",
                exc,
            )
            video_ref = video.path or video.url or video.file or ""
            ref_name = Path(video_ref.split("?", 1)[0].rstrip("/")).name
            req.extra_user_content_parts.append(
                TextPart(
                    text=(
                        "[Video Attachment in quoted message: "
                        f"name {ref_name or 'video'}, ref {video_ref}]"
                    )
                )
            )
        else:
            logger.error("Error processing video attachment: %s", exc)
        return

    video_name = Path(video_path).name
    if quoted:
        text = (
            f"[Video Attachment in quoted message: "
            f"name {video_name}, path {video_path}]"
        )
    else:
        text = f"[Video Attachment: name {video_name}, path {video_path}]"

    req.extra_user_content_parts.append(TextPart(text=text))


def get_quoted_message_settings(
    provider_settings: dict[str, object] | None,
) -> QuotedMessageParserSettings:
    if not isinstance(provider_settings, dict):
        return DEFAULT_QUOTED_MESSAGE_SETTINGS
    overrides = provider_settings.get("quoted_message_parser")
    if not isinstance(overrides, dict):
        return DEFAULT_QUOTED_MESSAGE_SETTINGS
    return DEFAULT_QUOTED_MESSAGE_SETTINGS.with_overrides(overrides)


async def append_quoted_content(
    event: AstrMessageEvent,
    req: ProviderRequest,
    img_cap_prov_id: str,
    plugin_context: Context,
    quoted_message_settings: QuotedMessageParserSettings = DEFAULT_QUOTED_MESSAGE_SETTINGS,
    main_provider_supports_image: bool = False,
    skip_quote_image_caption: bool = False,
    image_ref: str | None = None,
    image_is_montage: bool = False,
) -> str | None:
    """Append quoted text and optionally describe an explicitly supplied image.

    Args:
        event: Event whose quote text is included in the request.
        req: Working request receiving the quote text and optional caption.
        img_cap_prov_id: Existing dedicated caption provider selection.
        plugin_context: Provider and quoted-message lookup services.
        quoted_message_settings: Existing quote extraction limits and options.
        main_provider_supports_image: Whether the main model can see images.
        skip_quote_image_caption: Whether the main caption branch handles it.
        image_ref: Prepared image path supplied by the builder.
        image_is_montage: Whether the prepared image represents an animation.

    Returns:
        The successfully described image reference, or None if no caption was produced.
    """
    quote = None
    for comp in event.message_obj.message:
        if isinstance(comp, Reply):
            quote = comp
            break
    if not quote:
        return

    captioned_ref = None
    content_parts = []
    sender_info = f"({quote.sender_nickname}): " if quote.sender_nickname else ""
    message_str = (
        await extract_quoted_message_text(
            event,
            quote,
            settings=quoted_message_settings,
        )
        or quote.message_str
        or "[Empty Text]"
    )
    content_parts.append(f"{sender_info}{message_str}")

    if image_ref:
        if skip_quote_image_caption:
            logger.debug(
                "Skipping quote image captioning because image captioning already handled this request."
            )
        elif main_provider_supports_image:
            logger.debug(
                "Skipping quote image captioning because the main provider supports image input."
            )
        elif not img_cap_prov_id:
            logger.debug(
                "No dedicated image caption provider configured. "
                "Skipping quote image captioning."
            )
        else:
            try:
                prov = None
                prov = plugin_context.get_provider_by_id(img_cap_prov_id)
                if prov is None:
                    prov = await plugin_context.get_using_provider_async(
                        event.unified_msg_origin
                    )

                if prov and isinstance(prov, Provider):
                    caption_prompt = "Please describe the image content."
                    if image_is_montage:
                        caption_prompt += ANIMATION_CAPTION_NOTICE.format(indices="1")
                    llm_resp = await prov.text_chat(
                        prompt=caption_prompt,
                        image_urls=[image_ref],
                    )
                    if llm_resp.completion_text:
                        captioned_ref = image_ref
                        content_parts.append(
                            f"[Image Caption in quoted message]: {llm_resp.completion_text}"
                        )
                else:
                    logger.warning("No provider found for image captioning in quote.")
            except Exception as exc:
                logger.error("Quote image captioning failed (%s).", type(exc).__name__)

    quoted_content = "\n".join(content_parts)
    quoted_text = f"<Quoted Message>\n{quoted_content}\n</Quoted Message>"
    req.extra_user_content_parts.append(TextPart(text=quoted_text))
    return captioned_ref
