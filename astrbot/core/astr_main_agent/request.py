"""Conversation loading and preparation of message content and media."""

from __future__ import annotations

import asyncio
import copy
import datetime
import json
import zoneinfo
from dataclasses import dataclass, field
from pathlib import Path

from astrbot.core import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.astr_main_agent_resources import LLM_ERROR_MESSAGE_EXTRA_KEY
from astrbot.core.conversation_mgr import Conversation
from astrbot.core.message.components import File, Image, Record, Reply, Video
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.utils.file_extract import extract_file_moonshotai
from astrbot.core.utils.image_input import prepare_request_images
from astrbot.core.utils.media_utils import (
    describe_media_ref,
    is_file_uri,
    is_recoverable_image_error,
    normalize_model_image_max_size,
)
from astrbot.core.utils.quoted_message_parser import (
    extract_quoted_message_images,
)
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from . import media, providers
from .config import MainAgentBuildConfig

WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def apply_prompt_prefix(req: ProviderRequest, cfg: dict) -> None:
    """Apply the configured prefix or prompt template to the current input.

    Args:
        req: Request whose current prompt is updated in place.
        cfg: Provider settings containing the optional prompt prefix.
    """
    prefix = cfg.get("prompt_prefix")
    if not prefix:
        return
    if "{{prompt}}" in prefix:
        req.prompt = prefix.replace("{{prompt}}", req.prompt)
    else:
        req.prompt = f"{prefix}{req.prompt}"


def append_system_reminders(
    event: AstrMessageEvent,
    req: ProviderRequest,
    cfg: dict,
    timezone: str | None,
) -> None:
    """Append configured sender, group, and time information to the user content.

    Args:
        event: Event providing sender and group details.
        req: Request receiving the additional user content.
        cfg: Provider settings controlling which reminders are included.
        timezone: Configured IANA timezone, or None for the local timezone.
    """
    system_parts: list[str] = []
    if cfg.get("identifier"):
        user_id = event.message_obj.sender.user_id
        user_nickname = event.message_obj.sender.nickname
        system_parts.append(f"User ID: {user_id}, Nickname: {user_nickname}")

    if cfg.get("group_name_display") and event.message_obj.group_id:
        if not event.message_obj.group:
            logger.error(
                "Group name display enabled but group object is None. Group ID: %s",
                event.message_obj.group_id,
            )
        else:
            group_name = event.message_obj.group.group_name
            if group_name:
                system_parts.append(f"Group name: {group_name}")

    if cfg.get("datetime_system_prompt"):
        now = None
        if timezone:
            try:
                now = datetime.datetime.now(zoneinfo.ZoneInfo(timezone))
            except Exception as exc:  # noqa: BLE001
                logger.error("Invalid timezone: %s; using the local timezone.", exc)
        if now is None:
            now = datetime.datetime.now().astimezone()
        current_time = now.strftime("%Y-%m-%d %H:%M (%Z)")
        weekday = WEEKDAY_NAMES[now.weekday()]
        system_parts.append(f"Current datetime: {current_time}, Weekday: {weekday}")

    if system_parts:
        system_content = (
            "<system_reminder>" + "\n".join(system_parts) + "</system_reminder>"
        )
        req.extra_user_content_parts.append(TextPart(text=system_content))


async def _get_session_conv(
    event: AstrMessageEvent, plugin_context: Context
) -> Conversation:
    conv_mgr = plugin_context.conversation_manager
    umo = event.unified_msg_origin
    cid = await conv_mgr.get_curr_conversation_id(umo)
    if not cid:
        cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
    conversation = await conv_mgr.get_conversation(umo, cid)
    if not conversation:
        cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
        conversation = await conv_mgr.get_conversation(umo, cid)
    if not conversation:
        raise RuntimeError("无法创建新的对话。")
    return conversation


async def _apply_file_extract(
    event: AstrMessageEvent,
    req: ProviderRequest,
    config: MainAgentBuildConfig,
) -> None:
    file_paths = []
    file_names = []
    for comp in event.message_obj.message:
        if isinstance(comp, File):
            file_paths.append(await comp.get_file())
            file_names.append(comp.name)
        elif isinstance(comp, Reply) and comp.chain:
            for reply_comp in comp.chain:
                if isinstance(reply_comp, File):
                    file_paths.append(await reply_comp.get_file())
                    file_names.append(reply_comp.name)
    if not file_paths:
        return
    if not req.prompt:
        req.prompt = "总结一下文件里面讲了什么？"
    if config.file_extract_prov == "moonshotai":
        if not config.file_extract_msh_api_key:
            logger.error("Moonshot AI API key for file extract is not set")
            return
        file_contents = await asyncio.gather(
            *[
                extract_file_moonshotai(
                    file_path,
                    config.file_extract_msh_api_key,
                )
                for file_path in file_paths
            ]
        )
    else:
        logger.error("Unsupported file extract provider: %s", config.file_extract_prov)
        return

    for file_content, file_name in zip(file_contents, file_names):
        req.contexts.append(
            {
                "role": "system",
                "content": (
                    "File Extract Results of user uploaded files:\n"
                    f"{file_content}\nFile Name: {file_name or 'Unknown'}"
                ),
            },
        )


def matches_provider_wake_prefix(
    event: AstrMessageEvent,
    provider_wake_prefix: str,
) -> bool:
    """Return whether an event satisfies the provider wake prefix.

    Args:
        event: Incoming event whose message and platform should be inspected.
        provider_wake_prefix: Prefix required by the provider, if any.

    Returns:
        True for programmatic wakeups, when no prefix is configured, when
        WebChat is exempt, or when the message starts with the prefix.
    """
    message_str = event.message_str or ""
    if event.get_platform_name() == "lark":
        message_str = message_str.lstrip()
    return (
        isinstance(event, AgentWakeupEvent)
        or not provider_wake_prefix
        or event.get_platform_name() == "webchat"
        or message_str.startswith(provider_wake_prefix)
    )


async def collect_initial_request(
    event: AstrMessageEvent,
    plugin_context: Context,
    config: MainAgentBuildConfig,
    req: ProviderRequest | None = None,
    *,
    quoted_image_refs: set[str] | None = None,
) -> tuple[ProviderRequest | None, str | None]:
    """Collect raw attachments without applying model image policy.

    Args:
        event: Incoming event, including any plugin-provided request.
        plugin_context: Services used to resolve the conversation and attachments.
        config: Existing request collection settings.
        req: Explicit request for direct callers; its attachments are already
            collected, so only its quote reference needs to be resolved.
        quoted_image_refs: Optional output set populated from quoted image components.

    Returns:
        The initial request and the first embedded quote image reference used by
        the dedicated quote caption branch. A rejected wake prefix returns None.
    """
    if quoted_image_refs is None:
        quoted_image_refs = set()
    attachment_paths: list[str] = []
    if req is None:
        if event.get_extra("provider_request"):
            req = event.get_extra("provider_request")
            assert isinstance(req, ProviderRequest), (
                "provider_request 必须是 ProviderRequest 类型。"
            )
            req = copy.copy(req)
            req.image_urls = list(req.image_urls or [])
            req.extra_user_content_parts = list(req.extra_user_content_parts)
            req.contexts = (
                list(req.contexts) if isinstance(req.contexts, list) else req.contexts
            )
            if req.conversation:
                # Handler requests can be prepared before the pipeline acquires
                # the session lock. Reload the bound conversation here so queued
                # turns include replies saved while they were waiting.
                conversation = (
                    await plugin_context.conversation_manager.get_conversation(
                        event.unified_msg_origin, req.conversation.cid
                    )
                )
                if conversation is None:
                    event.set_extra(
                        LLM_ERROR_MESSAGE_EXTRA_KEY,
                        "The requested conversation no longer exists. Please send a new message.",
                    )
                    return None, None
                req.conversation = conversation
                req.contexts = json.loads(conversation.history)
        else:
            req = ProviderRequest()
            req.prompt = ""
            req.image_urls = []
            req.audio_urls = []
            if sel_model := event.get_extra("selected_model"):
                req.model = sel_model
            provider_wake_prefix = config.provider_wake_prefix
            if not matches_provider_wake_prefix(event, provider_wake_prefix):
                return None, None

            req.prompt = event.message_str
            prefix_text = event.message_str
            if event.get_platform_name() == "lark":
                prefix_text = prefix_text.lstrip()
            if (
                provider_wake_prefix
                and not isinstance(event, AgentWakeupEvent)
                and prefix_text.startswith(provider_wake_prefix)
            ):
                req.prompt = prefix_text[len(provider_wake_prefix) :]

            # media files attachments
            for comp in event.message_obj.message:
                if isinstance(comp, Image):
                    try:
                        image_path = await comp.convert_to_file_path()
                    except Exception as exc:
                        if not is_recoverable_image_error(exc):
                            raise
                        logger.warning(
                            "Image attachment is unavailable (%s): %s",
                            type(exc).__name__,
                            describe_media_ref(comp.url or comp.file),
                        )
                        req.extra_user_content_parts.append(
                            TextPart(text="[Image unavailable]")
                        )
                        continue
                    req.image_urls.append(image_path)
                    attachment_paths.append(image_path)
                    # Adopt sources created after PreProcess, before another
                    # attachment or conversation lookup can fail or be cancelled.
                    source_ref = comp.url or comp.file or ""
                    if not is_file_uri(source_ref):
                        try:
                            source_is_local = Path(source_ref).is_file()
                        except OSError as exc:
                            if not is_recoverable_image_error(exc):
                                raise
                            source_is_local = False
                        if not source_is_local and Path(image_path).is_file():
                            event.track_temporary_local_file(image_path)
                elif isinstance(comp, Record):
                    try:
                        audio_path = await comp.convert_to_file_path()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Voice attachment is unavailable (%s).",
                            type(exc).__name__,
                        )
                        req.extra_user_content_parts.append(
                            TextPart(text="[Voice unavailable]")
                        )
                        continue
                    req.audio_urls.append(audio_path)
                    media.append_audio_attachment(req, audio_path)
                elif isinstance(comp, File):
                    file_path = await comp.get_file()
                    file_name = comp.name or Path(file_path).name
                    req.extra_user_content_parts.append(
                        TextPart(
                            text=f"[File Attachment: name {file_name}, path {file_path}]"
                        )
                    )
                elif isinstance(comp, Video):
                    await media.append_video_attachment(req, comp)
            # quoted message attachments
            reply_comps = [
                comp for comp in event.message_obj.message if isinstance(comp, Reply)
            ]
            quoted_message_settings = media.get_quoted_message_settings(
                config.provider_settings
            )
            fallback_quoted_image_count = 0
            for comp in reply_comps:
                has_embedded_image = False
                if comp.chain:
                    for reply_comp in comp.chain:
                        if isinstance(reply_comp, Image):
                            has_embedded_image = True
                            try:
                                image_path = await reply_comp.convert_to_file_path()
                            except Exception as exc:
                                if not is_recoverable_image_error(exc):
                                    raise
                                logger.warning(
                                    "Quoted image is unavailable (%s): %s",
                                    type(exc).__name__,
                                    describe_media_ref(
                                        reply_comp.url or reply_comp.file
                                    ),
                                )
                                req.extra_user_content_parts.append(
                                    TextPart(text="[Image unavailable]")
                                )
                                continue
                            req.image_urls.append(image_path)
                            attachment_paths.append(image_path)
                            source_ref = reply_comp.url or reply_comp.file or ""
                            if not is_file_uri(source_ref):
                                try:
                                    source_is_local = Path(source_ref).is_file()
                                except OSError as exc:
                                    if not is_recoverable_image_error(exc):
                                        raise
                                    source_is_local = False
                                if not source_is_local and Path(image_path).is_file():
                                    event.track_temporary_local_file(image_path)
                            quoted_image_refs.add(image_path)
                        elif isinstance(reply_comp, Record):
                            try:
                                audio_path = await reply_comp.convert_to_file_path()
                            except Exception as exc:  # noqa: BLE001
                                logger.warning(
                                    "Quoted voice is unavailable (%s).",
                                    type(exc).__name__,
                                )
                                req.extra_user_content_parts.append(
                                    TextPart(text="[Voice unavailable]")
                                )
                                continue
                            req.audio_urls.append(audio_path)
                            media.append_quoted_audio_attachment(req, audio_path)
                        elif isinstance(reply_comp, File):
                            file_path = await reply_comp.get_file()
                            file_name = reply_comp.name or Path(file_path).name
                            req.extra_user_content_parts.append(
                                TextPart(
                                    text=(
                                        f"[File Attachment in quoted message: "
                                        f"name {file_name}, path {file_path}]"
                                    )
                                )
                            )
                        elif isinstance(reply_comp, Video):
                            await media.append_video_attachment(
                                req, reply_comp, quoted=True
                            )

                # Fallback quoted image extraction for reply-id-only payloads, or when
                # embedded reply chain only contains placeholders (e.g. [Forward Message], [Image]).
                if not has_embedded_image:
                    try:
                        fallback_images = normalize_and_dedupe_strings(
                            await extract_quoted_message_images(
                                event,
                                comp,
                                settings=quoted_message_settings,
                            )
                        )
                        remaining_limit = max(
                            config.max_quoted_fallback_images
                            - fallback_quoted_image_count,
                            0,
                        )
                        if remaining_limit <= 0 and fallback_images:
                            logger.warning(
                                "Skip quoted fallback images due to limit=%d for umo=%s",
                                config.max_quoted_fallback_images,
                                event.unified_msg_origin,
                            )
                            continue
                        if len(fallback_images) > remaining_limit:
                            logger.warning(
                                "Truncate quoted fallback images for umo=%s, reply_id=%s from %d to %d",
                                event.unified_msg_origin,
                                getattr(comp, "id", None),
                                len(fallback_images),
                                remaining_limit,
                            )
                            fallback_images = fallback_images[:remaining_limit]
                        for image_ref in fallback_images:
                            if image_ref in req.image_urls:
                                continue
                            req.image_urls.append(image_ref)
                            fallback_quoted_image_count += 1
                            quoted_image_refs.add(image_ref)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to resolve fallback quoted images for umo=%s, reply_id=%s: %s",
                            event.unified_msg_origin,
                            getattr(comp, "id", None),
                            exc,
                            exc_info=True,
                        )

            conversation = await _get_session_conv(event, plugin_context)
            req.conversation = conversation
            req.contexts = json.loads(conversation.history)
            event.set_extra("provider_request", req)

    req.image_urls = normalize_and_dedupe_strings(req.image_urls)
    quote_image_ref = None
    quote = next(
        (part for part in event.message_obj.message if isinstance(part, Reply)), None
    )
    if quote and quote.chain:
        image = next((part for part in quote.chain if isinstance(part, Image)), None)
        if image:
            quote_image_ref = image.url or image.file
    # Keep adopted source paths usable after cleanup, but retain provisional
    # ownership until collection succeeds so errors and cancellation can clean up.
    for image_path in attachment_paths:
        event.untrack_temporary_local_file(image_path)
    return req, quote_image_ref


@dataclass(slots=True)
class PreparedRequest:
    """Request content and the media state reused during finalization."""

    request: ProviderRequest
    images: dict[str, dict] = field(default_factory=dict)
    captioned_refs: set[str] = field(default_factory=set)
    image_max_size: int | None = None


async def prepare_request(
    event: AstrMessageEvent,
    plugin_context: Context,
    config: MainAgentBuildConfig,
    provider: Provider,
    req: ProviderRequest | None,
) -> PreparedRequest | None:
    """Load input/history, prepare attachments and describe unsupported images.

    Args:
        event: Triggering event and attachment source.
        plugin_context: Conversation, provider, and attachment services.
        config: Resolved input settings.
        provider: Initial model, used for the established caption policy.
        req: Optional caller-supplied request; None collects the event's input.

    Returns:
        Prepared content and image state, or None for a rejected, stopped, or empty input.
    """
    collected_request = req is None or (
        any(isinstance(part, Reply) for part in event.message_obj.message)
        and not any(
            isinstance(part, TextPart) and part.text.startswith("<Quoted Message>\n")
            for part in req.extra_user_content_parts
        )
    )
    quote_image_ref = None
    quoted_image_refs: set[str] = set()
    if collected_request:
        req, quote_image_ref = await collect_initial_request(
            event, plugin_context, config, req=req, quoted_image_refs=quoted_image_refs
        )
        if req is None:
            return None

    # A background task may be stopped while conversation loading is pending.
    stop_signal = event.get_extra("_background_stop_signal")
    if isinstance(stop_signal, asyncio.Event) and stop_signal.is_set():
        return None

    cfg = config.provider_settings
    options = cfg.get("image_compress_options", {})
    max_size = normalize_model_image_max_size(
        options.get("max_size") if isinstance(options, dict) else None
    )
    prepared_images: dict[str, dict] = {}
    supports_image = providers.supports_modality(provider, "image")
    caption_provider_id = cfg.get("default_image_caption_provider_id") or ""
    if (
        supports_image
        or not caption_provider_id
        or (req.conversation and req.image_urls)
    ):
        quote_image_ref = None
    await prepare_request_images(
        req,
        event,
        max_size=max_size,
        prepared=prepared_images,
        quote_image_ref=quote_image_ref,
        quoted_refs=quoted_image_refs,
        finalize=False,
    )

    if isinstance(req.contexts, str):
        req.contexts = json.loads(req.contexts)
    thread_selected_text = event.get_extra("thread_selected_text")
    if isinstance(thread_selected_text, str) and thread_selected_text.strip():
        req.extra_user_content_parts.append(
            TextPart(
                text=(
                    "The user is asking in a side thread about this selected "
                    "excerpt from the previous assistant answer:\n"
                    f"<selected_excerpt>{thread_selected_text.strip()}</selected_excerpt>"
                )
            )
        )
    req.image_urls = normalize_and_dedupe_strings(req.image_urls)
    req.audio_urls = normalize_and_dedupe_strings(req.audio_urls)

    if config.file_extract_enabled:
        try:
            await _apply_file_extract(event, req, config)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error occurred while applying file extract: %s", exc)

    has_reply = any(isinstance(comp, Reply) for comp in event.message_obj.message)

    if not req.prompt and not req.image_urls and not req.audio_urls:
        if has_reply or req.extra_user_content_parts:
            req.prompt = "<attachment>"
        else:
            return None

    captioned_refs: set[str] = set()
    montage_refs = {
        result["path"]
        for result in prepared_images.values()
        if result["path"] and result["montage"]
    }
    if collected_request:
        captioned_ref = await media.append_quoted_content(
            event,
            req,
            cfg.get("default_image_caption_provider_id") or "",
            plugin_context,
            media.get_quoted_message_settings(cfg),
            main_provider_supports_image=providers.supports_modality(provider, "image"),
            skip_quote_image_caption=bool(req.conversation and req.image_urls),
            image_ref=prepared_images[quote_image_ref]["path"]
            if quote_image_ref
            else None,
            image_is_montage=bool(
                quote_image_ref and prepared_images[quote_image_ref]["montage"]
            ),
        )
        if captioned_ref:
            captioned_refs.add(captioned_ref)
    apply_prompt_prefix(req, cfg)
    if (
        req.conversation
        and caption_provider_id
        and req.image_urls
        and not supports_image
    ):
        captioned_refs.update(
            await media.caption_request_images(
                event,
                req,
                cfg,
                plugin_context,
                caption_provider_id,
                montage_refs=montage_refs,
            )
        )
    if not req.session_id:
        req.session_id = event.unified_msg_origin
    return PreparedRequest(req, prepared_images, captioned_refs, max_size)
