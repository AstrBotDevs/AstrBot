import json

from sqlalchemy import case, func, select
from sqlmodel import col

from astrbot.api import sp, star
from astrbot.api.event import AstrMessageEvent, MessageChain, MessageEventResult
from astrbot.api.message_components import Json
from astrbot.core import logger
from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.round_utils import split_into_rounds
from astrbot.core.agent.message import (
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
)
from astrbot.core.agent.response import AgentStats
from astrbot.core.agent.runners.deerflow.constants import (
    DEERFLOW_PROVIDER_TYPE,
    DEERFLOW_THREAD_ID_KEY,
)
from astrbot.core.agent.runners.deerflow.deerflow_api_client import DeerFlowAPIClient
from astrbot.core.astr_main_agent import get_context_compression_provider
from astrbot.core.db.po import ProviderStat
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.session_lock import session_lock_manager

from .utils.rst_scene import RstScene

THIRD_PARTY_AGENT_RUNNER_KEY = {
    "dify": "dify_conversation_id",
    "coze": "coze_conversation_id",
    "dashscope": "dashscope_conversation_id",
    DEERFLOW_PROVIDER_TYPE: DEERFLOW_THREAD_ID_KEY,
}
THIRD_PARTY_AGENT_RUNNER_STR = ", ".join(THIRD_PARTY_AGENT_RUNNER_KEY.keys())


async def _cleanup_deerflow_thread_if_present(
    context: star.Context,
    umo: str,
) -> None:
    try:
        thread_id = await sp.get_async(
            scope="umo",
            scope_id=umo,
            key=DEERFLOW_THREAD_ID_KEY,
            default="",
        )
        if not thread_id:
            return

        cfg = context.get_config(umo=umo)
        agent_runner = cfg.get("agent_runner", {})
        if agent_runner.get("runner_type") != DEERFLOW_PROVIDER_TYPE:
            return
        runner_config = agent_runner.get("config", {})
        if not isinstance(runner_config, dict):
            return

        client = DeerFlowAPIClient(
            api_base=runner_config.get(
                "deerflow_api_base",
                "http://127.0.0.1:2026",
            ),
            api_key=runner_config.get("deerflow_api_key", ""),
            auth_header=runner_config.get("deerflow_auth_header", ""),
            proxy=runner_config.get("proxy", ""),
        )
        try:
            await client.delete_thread(thread_id)
        finally:
            try:
                await client.close()
            except Exception as e:
                logger.warning(
                    "Failed to close DeerFlow API client after thread cleanup: %s",
                    e,
                )
    except Exception as e:
        logger.warning(
            "Failed to clean up DeerFlow thread for session %s: %s",
            umo,
            e,
        )


async def _clear_third_party_agent_runner_state(
    context: star.Context,
    umo: str,
    agent_runner_type: str,
) -> None:
    session_key = THIRD_PARTY_AGENT_RUNNER_KEY.get(agent_runner_type)
    if not session_key:
        return

    if agent_runner_type == DEERFLOW_PROVIDER_TYPE:
        await _cleanup_deerflow_thread_if_present(context, umo)

    await sp.remove_async(
        scope="umo",
        scope_id=umo,
        key=session_key,
    )


class ConversationCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def _get_current_persona_id(self, session_id):
        curr = await self.context.conversation_manager.get_curr_conversation_id(
            session_id,
        )
        if not curr:
            return None
        conv = await self.context.conversation_manager.get_conversation(
            session_id,
            curr,
        )
        if not conv:
            return None
        return conv.persona_id

    async def reset(self, message: AstrMessageEvent) -> None:
        """重置 LLM 会话"""
        umo = message.unified_msg_origin
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        is_unique_session = cfg["platform_settings"]["unique_session"]
        is_group = bool(message.get_group_id())

        scene = RstScene.get_scene(is_group, is_unique_session)

        alter_cmd_cfg = await sp.get_async("global", "global", "alter_cmd", {})
        plugin_config = alter_cmd_cfg.get("astrbot", {})
        reset_cfg = plugin_config.get("reset", {})

        required_perm = reset_cfg.get(
            scene.key,
            "admin" if is_group and not is_unique_session else "member",
        )

        if required_perm == "admin" and message.role != "admin":
            message.set_result(
                MessageEventResult().message(
                    f"Reset command requires admin permission in {scene.name} scenario, "
                    f"you (ID {message.get_sender_id()}) are not admin, cannot perform this action.",
                ),
            )
            return

        agent_runner_type = cfg["agent_runner"]["runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            active_event_registry.stop_all(umo, exclude=message)
            await _clear_third_party_agent_runner_state(
                self.context,
                umo,
                agent_runner_type,
            )
            message.set_result(
                MessageEventResult().message("✅ Conversation reset successfully.")
            )
            return

        if not await self.context.get_using_provider_async(umo):
            message.set_result(
                MessageEventResult().message(
                    "😕 Cannot find any LLM provider. Configure one first."
                ),
            )
            return

        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "😕 You are not in a conversation. Use /new to create one.",
                ),
            )
            return

        active_event_registry.stop_all(umo, exclude=message)

        await self.context.conversation_manager.update_conversation(
            umo,
            cid,
            [],
        )

        ret = "✅ Conversation reset successfully."

        message.set_extra("_clean_group_context_session", True)

        message.set_result(MessageEventResult().message(ret))

    async def stop(self, message: AstrMessageEvent) -> None:
        """停止当前会话正在运行的 Agent"""
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        agent_runner_type = cfg["agent_runner"]["runner_type"]
        umo = message.unified_msg_origin

        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            stopped_count = active_event_registry.stop_all(umo, exclude=message)
        else:
            stopped_count = active_event_registry.request_agent_stop_all(
                umo,
                exclude=message,
            )

        if stopped_count > 0:
            message.set_result(
                MessageEventResult().message(
                    f"✅ Requested to stop {stopped_count} running tasks."
                )
            )
            return

        message.set_result(
            MessageEventResult().message("✅ No running tasks in the current session.")
        )

    async def compact(self, message: AstrMessageEvent) -> None:
        """Compress the persisted history of the current local conversation."""

        def reply(text: str) -> None:
            """Set a plain-text command result.

            Args:
                text: Message shown to the user.
            """
            message.set_result(message.plain_result(text))

        preserved = "❌ Context compression failed; the original context was preserved."
        cancelled = "⚠️ Compression cancelled; original context was preserved."
        unknown = "⚠️ Context state is unknown. Check the conversation before retrying."
        umo = message.unified_msg_origin
        cfg = self.context.get_config(umo=umo)
        provider_settings = cfg.get("provider_settings", {})
        agent_runner = cfg.get("agent_runner", {})
        conversation_manager = self.context.conversation_manager

        is_unique_session = cfg.get("platform_settings", {}).get(
            "unique_session",
            False,
        )
        is_shared_group = bool(message.get_group_id()) and not is_unique_session
        if is_shared_group and message.role != "admin":
            reply(
                "❌ Context compression requires admin permission in a shared "
                "group conversation."
            )
            return

        if not provider_settings.get("enable", True):
            reply("❌ AI features are disabled for this session.")
            return

        if agent_runner.get("runner_type") != "local":
            reply("❌ /compact is supported only by the local agent runner.")
            return

        runner_config = agent_runner.get("config", {})
        compression_config = runner_config.get("compression", {})
        if not compression_config.get("enable_manual_context_compression", False):
            reply(
                "❌ Manual context compression is disabled. Enable it in Context "
                "Management first."
            )
            return

        strategy = compression_config.get("overflow_strategy")
        if strategy != "llm_compress":
            reply("❌ /compact requires the LLM context compression strategy.")
            return

        initial_cid = await conversation_manager.get_curr_conversation_id(umo)
        if not initial_cid:
            reply("❌ You are not in a conversation. Use /new to create one.")
            return

        compression_provider = await get_context_compression_provider(
            strategy,
            compression_config.get("provider_id", ""),
            self.context,
            message,
        )
        if not compression_provider:
            reply("❌ No LLM provider is available for context compression.")
            return

        progress_type = (
            "webchat_ephemeral" if message.get_platform_name() == "webchat" else None
        )
        await message.send(
            MessageChain(type=progress_type).message("⏳ Compressing context...")
        )

        try:
            async with session_lock_manager.acquire_lock(umo):
                if message.is_stopped():
                    return
                if message.get_extra("agent_stop_requested"):
                    reply(cancelled)
                    return

                cid = await conversation_manager.get_curr_conversation_id(umo)
                if not cid or cid != initial_cid:
                    reply("⚠️ The active conversation changed; no changes were saved.")
                    return

                conversation = await conversation_manager.get_conversation(umo, cid)
                if not conversation:
                    reply(
                        "❌ The current conversation could not be loaded; the "
                        "original context was preserved."
                    )
                    return

                original_history_text = conversation.history
                original_history = json.loads(conversation.history)
                if not isinstance(original_history, list) or not original_history:
                    reply("ℹ️ There is not enough conversation history to compress.")
                    return

                messages = bind_checkpoint_messages(original_history)
                complete_rounds = sum(
                    any(segment.role == "user" for segment in round_)
                    and any(segment.role == "assistant" for segment in round_)
                    for round_ in split_into_rounds(messages)
                )
                if complete_rounds <= 1:
                    reply("ℹ️ There is not enough conversation history to compress.")
                    return

                context_manager = ContextManager(
                    ContextConfig(
                        llm_compress_instruction=compression_config.get("instruction"),
                        llm_compress_keep_recent_ratio=compression_config.get(
                            "keep_recent_ratio",
                            0.15,
                        ),
                        llm_compress_preserve_latest_round=True,
                        llm_compress_provider=compression_provider,
                    )
                )
                tokens_before = context_manager.token_counter.count_tokens(messages)
                if tokens_before <= 0:
                    reply("ℹ️ There is not enough conversation history to compress.")
                    return

                compressed_messages = await context_manager.process(
                    messages,
                    force_compress=True,
                )
                tokens_after = context_manager.token_counter.count_tokens(
                    compressed_messages
                )
                if compressed_messages == messages or tokens_after >= tokens_before:
                    reply(preserved)
                    return

                target_history = dump_messages_with_checkpoints(compressed_messages)
                latest_cid = await conversation_manager.get_curr_conversation_id(umo)
                latest_conversation = await conversation_manager.get_conversation(
                    umo, cid
                )
                if (
                    latest_cid != cid
                    or not latest_conversation
                    or latest_conversation.history != original_history_text
                ):
                    reply(
                        "⚠️ Context changed during compression; no changes were saved."
                    )
                    return

                if message.is_stopped():
                    return
                if message.get_extra("agent_stop_requested"):
                    reply(cancelled)
                    return

                try:
                    await conversation_manager.update_conversation(
                        umo,
                        cid,
                        history=target_history,
                        token_usage=0,
                    )
                except Exception as update_error:
                    logger.error(
                        "Context compression storage update failed: %s.",
                        type(update_error).__name__,
                    )
                    try:
                        stored_conversation = (
                            await conversation_manager.get_conversation(umo, cid)
                        )
                        stored_history = json.loads(stored_conversation.history)
                    except Exception as verify_error:
                        logger.error(
                            "Context compression storage verification failed: %s.",
                            type(verify_error).__name__,
                        )
                        reply(unknown)
                        return

                    if stored_history != target_history:
                        reply(
                            preserved if stored_history == original_history else unknown
                        )
                        return
        except Exception as error:
            logger.error(
                "Context compression failed before storage update: %s.",
                type(error).__name__,
            )
            reply(preserved)
            return

        if message.is_stopped():
            return

        if message.get_platform_name() == "webchat":
            try:
                await message.send(
                    MessageChain(
                        type="agent_stats",
                        chain=[
                            Json(
                                data=AgentStats(
                                    current_context_tokens=tokens_after,
                                ).to_dict()
                            )
                        ],
                    )
                )
            except Exception as error:
                logger.warning(
                    "Failed to send context compression stats: %s.",
                    type(error).__name__,
                )

        reply("✅ Context compressed.")

    async def new_conv(self, message: AstrMessageEvent) -> None:
        """创建新对话"""
        cfg = self.context.get_config(umo=message.unified_msg_origin)
        agent_runner_type = cfg["agent_runner"]["runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            active_event_registry.stop_all(message.unified_msg_origin, exclude=message)
            await _clear_third_party_agent_runner_state(
                self.context,
                message.unified_msg_origin,
                agent_runner_type,
            )
            message.set_result(
                MessageEventResult().message("✅ New conversation created.")
            )
            return

        active_event_registry.stop_all(message.unified_msg_origin, exclude=message)
        cpersona = await self._get_current_persona_id(message.unified_msg_origin)
        cid = await self.context.conversation_manager.new_conversation(
            message.unified_msg_origin,
            message.get_platform_id(),
            persona_id=cpersona,
        )

        message.set_extra("_clean_group_context_session", True)

        message.set_result(
            MessageEventResult().message(
                f"✅ Switched to new conversation: {cid[:4]}。"
            ),
        )

    async def stats(self, message: AstrMessageEvent) -> None:
        """Show token usage statistics for the current conversation."""
        umo = message.unified_msg_origin
        cid = await self.context.conversation_manager.get_curr_conversation_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "❌ You are not in a conversation. Use /new to create one."
                ),
            )
            return

        db = self.context.get_db()
        async with db.get_db() as session:
            result = await session.execute(
                select(
                    func.count(case((col(ProviderStat.id).is_not(None), 1))).label(
                        "record_count",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_input_other), 0).label(
                        "total_input_other",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_input_cached), 0).label(
                        "total_input_cached",
                    ),
                    func.coalesce(func.sum(ProviderStat.token_output), 0).label(
                        "total_output",
                    ),
                ).where(
                    col(ProviderStat.agent_type) == "internal",
                    col(ProviderStat.conversation_id) == cid,
                )
            )
            stats = result.one()

        if stats.record_count == 0:
            message.set_result(
                MessageEventResult().message(
                    "📊 No stats available for this conversation yet."
                ),
            )
            return

        total_input_other = stats.total_input_other
        total_input_cached = stats.total_input_cached
        total_output = stats.total_output
        total_tokens = total_input_other + total_input_cached + total_output

        ret = (
            f"📊 Conversation Token usage (ID: {cid[:8]}...)\n"
            f"Total:          {total_tokens:,}\n"
            f"Input (cached): {total_input_cached:,}\n"
            f"Input (other):  {total_input_other:,}\n"
            f"Output:         {total_output:,}\n"
        )

        message.set_result(MessageEventResult().message(ret))
