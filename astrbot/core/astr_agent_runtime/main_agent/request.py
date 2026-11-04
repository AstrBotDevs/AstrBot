"""Native conversation binding before Core-owned input preprocessing."""

import json

from astrbot.core.agent.message import TextPart
from astrbot.core.agent_input import (
    CollectedInput,
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
    collect_initial_request as collect_initial_request,
)
from astrbot.core.agent_input import (
    matches_provider_wake_prefix as matches_provider_wake_prefix,
)
from astrbot.core.conversation_mgr import Conversation
from astrbot.core.llm_error_messages import LLM_ERROR_MESSAGE_EXTRA_KEY
from astrbot.core.message.components import Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context

from .config import MainAgentBuildConfig


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
