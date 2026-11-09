"""Native conversation binding before Core-owned input preprocessing."""

import copy
import json
from pathlib import Path

from astrbot.core import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.agent_input import (
    CollectedInput,
    InputProcessingSettings,
    PreparedRequest,
    prepare_input_content,
)
from astrbot.core.agent_input import (
    append_system_reminders as append_system_reminders,
)
from astrbot.core.agent_input import (
    apply_prompt_prefix as apply_prompt_prefix,
)
from astrbot.core.agent_input import (
    matches_provider_wake_prefix as matches_provider_wake_prefix,
)
from astrbot.core.conversation_mgr import Conversation
from astrbot.core.llm_error_messages import LLM_ERROR_MESSAGE_EXTRA_KEY
from astrbot.core.message.components import File, Image, Record, Reply, Video
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.utils.media_utils import (
    describe_media_ref,
    is_file_uri,
    is_recoverable_image_error,
)
from astrbot.core.utils.quoted_message_parser import extract_quoted_message_images
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from .config import MainAgentBuildConfig


async def collect_initial_request(
    event: AstrMessageEvent,
    plugin_context: Context,
    config: InputProcessingSettings,
    req: ProviderRequest | None = None,
    *,
    quoted_image_refs: set[str] | None = None,
    materialized_paths: list[str] | None = None,
) -> tuple[ProviderRequest | None, str | None]:
    """Collect raw attachments without applying model image policy.

    Args:
        event: Incoming event, including any plugin-provided request.
        plugin_context: Services used to resolve the conversation and attachments.
        config: Existing request collection settings.
        req: Explicit request for direct callers; its attachments are already
            collected, so only its quote reference needs to be resolved.
        quoted_image_refs: Optional output set populated from quoted image components.
        materialized_paths: Optional output list of temporary files adopted on success.

    Returns:
        The initial request and the first embedded quote image reference used by
        the dedicated quote caption branch. A rejected wake prefix returns None.
    """
    from astrbot.core import agent_media as media

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
    if materialized_paths is not None:
        materialized_paths.extend(attachment_paths)
    return req, quote_image_ref


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


async def prepare_request(
    event: AstrMessageEvent,
    plugin_context: Context,
    config: MainAgentBuildConfig,
    provider: Provider,
    req: ProviderRequest | None,
    collected_input: CollectedInput | None = None,
) -> PreparedRequest | None:
    """Bind fresh native history and ask Core to prepare this turn's content.

    Args:
        event: Incoming message, wakeup, or explicit SDK event.
        plugin_context: Native conversation storage and Core input services.
        config: Resolved settings for this turn.
        provider: Selected model used for image capability negotiation.
        req: Optional explicit native request retaining its SDK semantics.
        collected_input: Optional Core-collected input with reusable quote metadata.

    Returns:
        Input and media state, or None when Core rejects the input.
    """
    explicit = req is not None or collected_input is not None
    collected = req is None or (
        any(isinstance(part, Reply) for part in event.message_obj.message)
        and not any(
            isinstance(part, TextPart) and part.text.startswith("<Quoted Message>\n")
            for part in req.extra_user_content_parts
        )
    )
    quote_ref = None
    quote_refs: set[str] = set()
    sources: list[str] = []
    if collected_input is not None:
        req = collected_input.request
        quote_ref = collected_input.quote_image_ref
        quote_refs = collected_input.quoted_image_refs
        collected = collected_input.parse_quoted
        sources = collected_input.source_paths
    elif collected:
        req, quote_ref = await collect_initial_request(
            event,
            plugin_context,
            config,
            req=req,
            quoted_image_refs=quote_refs,
            materialized_paths=sources,
        )
        if req is None:
            return None
    if req is None:
        return None
    if not explicit:
        if req.conversation is not None:
            conversation = await plugin_context.conversation_manager.get_conversation(
                event.unified_msg_origin,
                req.conversation.cid,
            )
            if conversation is None:
                event.set_extra(
                    LLM_ERROR_MESSAGE_EXTRA_KEY,
                    "The requested conversation no longer exists. Please send a new message.",
                )
                return None
        else:
            conversation = await _get_session_conv(event, plugin_context)
        req.conversation = conversation
        req.contexts = json.loads(conversation.history)
        event.set_extra("provider_request", req)
    prepared = await prepare_input_content(
        event,
        plugin_context,
        config,
        provider,
        req,
        collected_request=collected,
        quote_image_ref=quote_ref,
        quoted_image_refs=quote_refs,
    )
    if prepared is not None:
        for path in sources:
            event.untrack_temporary_local_file(path)
    return prepared
