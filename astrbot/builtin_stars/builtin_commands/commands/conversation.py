import datetime

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.platform import MessageType
from astrbot.core.agent.runners.deerflow.constants import (
    DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY,
    DEERFLOW_PROVIDER_TYPE,
    DEERFLOW_THREAD_ID_KEY,
)
from astrbot.core.agent.runners.deerflow.deerflow_api_client import DeerFlowAPIClient
from astrbot.core.platform.message_session import MessageSession

THIRD_PARTY_AGENT_RUNNER_KEY = {
    "dify": "dify_conversation_id",
    "coze": "coze_conversation_id",
    "dashscope": "dashscope_conversation_id",
    DEERFLOW_PROVIDER_TYPE: DEERFLOW_THREAD_ID_KEY,
}
THIRD_PARTY_AGENT_RUNNER_STR = ", ".join(THIRD_PARTY_AGENT_RUNNER_KEY.keys())


async def _cleanup_deerflow_thread_if_present(
    context: star.PluginContext,
    umo: str,
) -> None:
    try:
        thread_id = await context.preferences.session_get(
            umo,
            DEERFLOW_THREAD_ID_KEY,
            "",
        )
        if not thread_id:
            return

        cfg = context.config.get(umo=umo)
        provider_id = cfg["provider_settings"].get(
            DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY,
            "",
        )
        if not provider_id:
            return

        merged_provider_config = context.models.configuration(
            provider_id,
            merged=True,
        )
        if not merged_provider_config:
            logger.warning(
                "Failed to resolve DeerFlow provider config for remote thread cleanup: provider_id=%s",
                provider_id,
            )
            return

        client = DeerFlowAPIClient(
            api_base=merged_provider_config.get(
                "deerflow_api_base",
                "http://127.0.0.1:2026",
            ),
            api_key=merged_provider_config.get("deerflow_api_key", ""),
            auth_header=merged_provider_config.get("deerflow_auth_header", ""),
            proxy=merged_provider_config.get("proxy", ""),
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
    context: star.PluginContext,
    umo: str,
    agent_runner_type: str,
) -> None:
    session_key = THIRD_PARTY_AGENT_RUNNER_KEY.get(agent_runner_type)
    if not session_key:
        return

    if agent_runner_type == DEERFLOW_PROVIDER_TYPE:
        await _cleanup_deerflow_thread_if_present(context, umo)

    await context.preferences.session_remove(umo, session_key)


class ConversationCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def _get_current_persona_id(self, session_id):
        curr = await self.context.conversations.current_id(
            session_id,
        )
        if not curr:
            return None
        conv = await self.context.conversations.get(
            session_id,
            curr,
        )
        if not conv:
            return None
        return conv.persona_id

    async def reset(self, message: AstrMessageEvent) -> None:
        """重置 LLM 会话"""
        umo = message.unified_msg_origin
        cfg = self.context.config.get(umo=message.unified_msg_origin)

        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            self.context.conversations.stop_active_events(umo, exclude=message)
            await _clear_third_party_agent_runner_state(
                self.context,
                umo,
                agent_runner_type,
            )
            message.set_result(
                MessageEventResult().message("✅ Conversation reset successfully.")
            )
            return

        if not self.context.models.using_chat(umo):
            message.set_result(
                MessageEventResult().message(
                    "😕 Cannot find any LLM provider. Configure one first."
                ),
            )
            return

        cid = await self.context.conversations.current_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "😕 You are not in a conversation. Use /conversation create to create one.",
                ),
            )
            return

        self.context.conversations.stop_active_events(umo, exclude=message)

        await self.context.conversations.update(
            umo,
            conversation_id=cid,
            history=[],
        )

        ret = "✅ Conversation reset successfully."

        message.set_extra("_clean_group_context_session", True)

        message.set_result(MessageEventResult().message(ret))

    async def stop(self, message: AstrMessageEvent) -> None:
        """停止当前会话正在运行的 Agent"""
        cfg = self.context.config.get(umo=message.unified_msg_origin)
        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        umo = message.unified_msg_origin

        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            stopped_count = self.context.conversations.stop_active_events(
                umo,
                exclude=message,
            )
        else:
            stopped_count = self.context.conversations.request_agent_stop_all(
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

    async def create(self, message: AstrMessageEvent) -> None:
        """创建新对话"""
        cfg = self.context.config.get(umo=message.unified_msg_origin)
        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            self.context.conversations.stop_active_events(
                message.unified_msg_origin,
                exclude=message,
            )
            await _clear_third_party_agent_runner_state(
                self.context,
                message.unified_msg_origin,
                agent_runner_type,
            )
            message.set_result(
                MessageEventResult().message("✅ New conversation created.")
            )
            return

        self.context.conversations.stop_active_events(
            message.unified_msg_origin,
            exclude=message,
        )
        cpersona = await self._get_current_persona_id(message.unified_msg_origin)
        cid = await self.context.conversations.create(
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
        cid = await self.context.conversations.current_id(umo)

        if not cid:
            message.set_result(
                MessageEventResult().message(
                    "❌ You are not in a conversation. Use /conversation create to create one."
                ),
            )
            return

        stats = await self.context.conversations.token_usage(cid)

        if stats.record_count == 0:
            message.set_result(
                MessageEventResult().message(
                    "📊 No stats available for this conversation yet."
                ),
            )
            return

        total_input_other = stats.input_other
        total_input_cached = stats.input_cached
        total_output = stats.output
        total_tokens = stats.total

        ret = (
            f"📊 Conversation Token usage (ID: {cid[:8]}...)\n"
            f"Total:          {total_tokens:,}\n"
            f"Input (cached): {total_input_cached:,}\n"
            f"Input (other):  {total_input_other:,}\n"
            f"Output:         {total_output:,}\n"
        )

        message.set_result(MessageEventResult().message(ret))

    async def history(self, message: AstrMessageEvent, page: int = 1) -> None:
        """Show conversation history."""
        size_per_page = 6
        umo = message.unified_msg_origin
        current_cid = await self.context.conversations.current_id(umo)

        if not current_cid:
            current_cid = await self.context.conversations.create(
                umo,
                message.get_platform_id(),
            )

        contexts, total_pages = await self.context.conversations.readable_history(
            umo,
            current_cid,
            page=page,
            page_size=size_per_page,
        )

        parts: list[str] = []
        for context in contexts:
            if len(context) > 150:
                context = context[:150] + "..."
            parts.append(f"{context}\n")

        history = "".join(parts)
        ret = (
            "Conversation history:\n"
            f"{history or 'No history yet.'}\n\n"
            f"Page {page} / {total_pages}\n"
            "*Use /conversation history --page <page> to jump to another page."
        )
        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    async def list_conversations(
        self,
        message: AstrMessageEvent,
        page: int = 1,
    ) -> None:
        """Show conversation list."""
        cfg = self.context.config.get(umo=message.unified_msg_origin)
        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            message.set_result(
                MessageEventResult().message(
                    f"Conversation listing is not supported for {THIRD_PARTY_AGENT_RUNNER_STR}.",
                ),
            )
            return

        size_per_page = 6
        conversations_all = await self.context.conversations.list(
            message.unified_msg_origin,
        )
        total_pages = max(
            1, (len(conversations_all) + size_per_page - 1) // size_per_page
        )
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * size_per_page
        end_idx = start_idx + size_per_page
        conversations_paged = conversations_all[start_idx:end_idx]

        titles = {
            conv.cid: (conv.title if conv.title else "New conversation")
            for conv in conversations_all
        }
        provider_settings = cfg.get("provider_settings", {})
        platform_name = message.get_platform_name()

        parts = ["Conversations:\n---\n"]
        global_index = start_idx + 1
        for conv in conversations_paged:
            (
                persona_id,
                _,
                force_applied_persona_id,
                _,
            ) = await self.context.personas.resolve(
                umo=message.unified_msg_origin,
                conversation_persona_id=conv.persona_id,
                platform_name=platform_name,
                provider_settings=provider_settings,
            )
            if persona_id == "[%None]":
                persona_name = "none"
            elif persona_id:
                persona_name = persona_id
            else:
                persona_name = "none"

            if force_applied_persona_id:
                persona_name = f"{persona_name} (session rule)"

            title = titles.get(conv.cid, "New conversation")
            updated_at = datetime.datetime.fromtimestamp(conv.updated_at).strftime(
                "%m-%d %H:%M"
            )
            parts.append(
                f"{global_index}. {title} ({conv.cid[:4]})\n"
                f"  Persona: {persona_name}\n"
                f"  Updated: {updated_at}\n"
            )
            global_index += 1

        parts.append("---\n")
        ret = "".join(parts)
        current_cid = await self.context.conversations.current_id(
            message.unified_msg_origin,
        )
        if current_cid:
            ret += (
                f"\nCurrent conversation: {titles.get(current_cid, 'New conversation')} "
                f"({current_cid[:4]})"
            )
        else:
            ret += "\nCurrent conversation: none"

        unique_session = cfg["platform_settings"]["unique_session"]
        ret += (
            "\nSession isolation: user"
            if unique_session
            else "\nSession isolation: group"
        )
        ret += f"\nPage {page} / {total_pages}"
        ret += "\n*Use /conversation list --page <page> to jump to another page."
        message.set_result(MessageEventResult().message(ret).use_t2i(False))

    async def create_for(self, message: AstrMessageEvent, session_id: str) -> None:
        """Create a new conversation for a target group session."""
        session = str(
            MessageSession(
                platform_name=message.get_platform_id(),
                message_type=MessageType.GROUP_MESSAGE,
                session_id=str(session_id),
            ),
        )
        for action in ("session.assign", "session.manage"):
            decision = await self.context.authz.authorize_target_session(
                message,
                action=action,
                umo=session,
            )
            if not decision.allowed:
                message.set_result(
                    MessageEventResult().message(
                        "❌ You are not authorized to manage this target session.",
                    )
                )
                return
        current_persona = await self._get_current_persona_id(session)
        cid = await self.context.conversations.create(
            session,
            message.get_platform_id(),
            persona_id=current_persona,
        )
        message.set_result(
            MessageEventResult().message(
                f"✅ Group session {session} switched to a new conversation: {cid[:4]}.",
            ),
        )

    async def switch(
        self,
        message: AstrMessageEvent,
        index: int,
    ) -> None:
        """Switch to a conversation returned by /conversation list."""
        conversations = await self.context.conversations.list(
            message.unified_msg_origin,
        )
        if index < 1 or index > len(conversations):
            message.set_result(
                MessageEventResult().message(
                    "❌ Invalid conversation index. Use /conversation list to inspect available conversations.",
                ),
            )
            return

        conversation = conversations[index - 1]
        await self.context.conversations.switch(
            message.unified_msg_origin,
            conversation.cid,
        )
        title = conversation.title or "New conversation"
        message.set_result(
            MessageEventResult().message(
                f"✅ Switched to conversation: {title} ({conversation.cid[:4]}).",
            ),
        )

    async def rename(self, message: AstrMessageEvent, title: str) -> None:
        """Rename the current conversation."""
        new_name = title.strip()
        if not new_name:
            message.set_result(
                MessageEventResult().message("The conversation title cannot be empty."),
            )
            return

        await self.context.conversations.update(
            message.unified_msg_origin,
            title=new_name,
        )
        message.set_result(
            MessageEventResult().message("✅ Conversation renamed successfully."),
        )

    async def delete(self, message: AstrMessageEvent) -> None:
        """Delete the current conversation."""
        umo = message.unified_msg_origin
        cfg = self.context.config.get(umo=umo)

        agent_runner_type = cfg["provider_settings"]["agent_runner_type"]
        if agent_runner_type in THIRD_PARTY_AGENT_RUNNER_KEY:
            self.context.conversations.stop_active_events(umo, exclude=message)
            await _clear_third_party_agent_runner_state(
                self.context,
                umo,
                agent_runner_type,
            )
            message.set_result(
                MessageEventResult().message("✅ Conversation state cleared."),
            )
            return

        current_cid = await self.context.conversations.current_id(
            umo,
        )
        if not current_cid:
            message.set_result(
                MessageEventResult().message(
                    "There is no active conversation. Use /conversation create to create one or /conversation switch to enter another conversation.",
                ),
            )
            return

        self.context.conversations.stop_active_events(umo, exclude=message)
        await self.context.conversations.delete(
            umo,
            current_cid,
        )
        message.set_extra("_clean_group_context_session", True)
        message.set_result(
            MessageEventResult().message(
                "✅ Deleted the current conversation. Use /conversation create to create one or /conversation switch to enter another conversation.",
            ),
        )
