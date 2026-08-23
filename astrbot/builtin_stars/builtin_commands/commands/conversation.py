import datetime

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.platform import MessageSession, MessageType

from .reply import reply_i18n


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
        """Reset LLM conversation history."""
        umo = message.unified_msg_origin
        if self.context.conversations.third_party_agent_runner(umo):
            self.context.conversations.stop_active_events(umo, exclude=message)
            await self.context.conversations.reset_session_state(umo)
            await reply_i18n(self.context, message, "conversation.reset.ok")
            return

        if not self.context.models.using_chat(umo):
            await reply_i18n(self.context, message, "conversation.reset.no_provider")
            return

        cid = await self.context.conversations.current_id(umo)
        if not cid:
            await reply_i18n(
                self.context, message, "conversation.reset.no_conversation"
            )
            return

        self.context.conversations.stop_active_events(umo, exclude=message)
        await self.context.conversations.update(
            umo,
            conversation_id=cid,
            history=[],
        )
        message.set_extra("_clean_group_context_session", True)
        await reply_i18n(self.context, message, "conversation.reset.ok")

    async def stop(self, message: AstrMessageEvent) -> None:
        """Stop running tasks in the current session."""
        umo = message.unified_msg_origin
        if self.context.conversations.third_party_agent_runner(umo):
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
            await reply_i18n(
                self.context,
                message,
                "task.stop.requested",
                count=stopped_count,
            )
            return
        await reply_i18n(self.context, message, "task.stop.none")

    async def create(self, message: AstrMessageEvent) -> None:
        """Create a new conversation."""
        umo = message.unified_msg_origin
        if self.context.conversations.third_party_agent_runner(umo):
            self.context.conversations.stop_active_events(umo, exclude=message)
            await self.context.conversations.reset_session_state(umo)
            await reply_i18n(self.context, message, "conversation.create.ok")
            return

        self.context.conversations.stop_active_events(umo, exclude=message)
        cpersona = await self._get_current_persona_id(umo)
        cid = await self.context.conversations.create(
            umo,
            message.get_platform_id(),
            persona_id=cpersona,
        )
        message.set_extra("_clean_group_context_session", True)
        await reply_i18n(
            self.context,
            message,
            "conversation.create.switched",
            cid=cid[:4],
        )

    async def stats(self, message: AstrMessageEvent) -> None:
        """Show token usage statistics for the current conversation."""
        umo = message.unified_msg_origin
        cid = await self.context.conversations.current_id(umo)
        if not cid:
            await reply_i18n(
                self.context, message, "conversation.stats.no_conversation"
            )
            return

        stats = await self.context.conversations.token_usage(cid)
        if stats.record_count == 0:
            await reply_i18n(self.context, message, "conversation.stats.empty")
            return

        await reply_i18n(
            self.context,
            message,
            "conversation.stats.body",
            cid=cid[:8],
            total=f"{stats.total:,}",
            input_cached=f"{stats.input_cached:,}",
            input_other=f"{stats.input_other:,}",
            output=f"{stats.output:,}",
        )

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
        history = "".join(parts) or await self.context.i18n.t(
            message, "conversation.history.empty"
        )
        await reply_i18n(
            self.context,
            message,
            "conversation.history.body",
            history=history,
            page=page,
            total_pages=total_pages,
        )

    async def list_conversations(
        self,
        message: AstrMessageEvent,
        page: int = 1,
    ) -> None:
        """Show conversation list."""
        if self.context.conversations.third_party_agent_runner(
            message.unified_msg_origin
        ):
            await reply_i18n(
                self.context,
                message,
                "conversation.list.unsupported",
                runners=self.context.conversations.third_party_agent_runner_names(),
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

        new_title = await self.context.i18n.t(message, "conversation.list.new")
        titles = {
            conv.cid: (conv.title if conv.title else new_title)
            for conv in conversations_all
        }
        cfg = self.context.config.get(umo=message.unified_msg_origin)
        provider_settings = cfg.get("provider_settings", {})
        platform_name = message.get_platform_name()
        none_persona = await self.context.i18n.t(
            message, "conversation.list.none_persona"
        )
        session_rule = await self.context.i18n.t(
            message, "conversation.list.session_rule"
        )

        parts = [await self.context.i18n.t(message, "conversation.list.header")]
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
                persona_name = none_persona
            elif persona_id:
                persona_name = persona_id
            else:
                persona_name = none_persona
            if force_applied_persona_id:
                persona_name = f"{persona_name} {session_rule}"
            title = titles.get(conv.cid, new_title)
            updated_at = datetime.datetime.fromtimestamp(conv.updated_at).strftime(
                "%m-%d %H:%M"
            )
            parts.append(
                await self.context.i18n.t(
                    message,
                    "conversation.list.item",
                    index=global_index,
                    title=title,
                    cid=conv.cid[:4],
                    persona=persona_name,
                    updated=updated_at,
                )
            )
            global_index += 1

        current_cid = await self.context.conversations.current_id(
            message.unified_msg_origin,
        )
        if current_cid:
            current = await self.context.i18n.t(
                message,
                "conversation.list.current",
                title=titles.get(current_cid, new_title),
                cid=current_cid[:4],
            )
        else:
            current = await self.context.i18n.t(
                message, "conversation.list.current_none"
            )
        unique_session = cfg["platform_settings"]["unique_session"]
        isolation = await self.context.i18n.t(
            message,
            "conversation.list.isolation_user"
            if unique_session
            else "conversation.list.isolation_group",
        )
        await reply_i18n(
            self.context,
            message,
            "conversation.list.body",
            items="".join(parts),
            current=current,
            isolation=isolation,
            page=page,
            total_pages=total_pages,
        )

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
                await reply_i18n(
                    self.context, message, "conversation.create_for.denied"
                )
                return
        current_persona = await self._get_current_persona_id(session)
        cid = await self.context.conversations.create(
            session,
            message.get_platform_id(),
            persona_id=current_persona,
        )
        await reply_i18n(
            self.context,
            message,
            "conversation.create_for.ok",
            session=session,
            cid=cid[:4],
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
            await reply_i18n(self.context, message, "conversation.switch.invalid")
            return

        conversation = conversations[index - 1]
        await self.context.conversations.switch(
            message.unified_msg_origin,
            conversation.cid,
        )
        new_title = await self.context.i18n.t(message, "conversation.list.new")
        title = conversation.title or new_title
        await reply_i18n(
            self.context,
            message,
            "conversation.switch.ok",
            title=title,
            cid=conversation.cid[:4],
        )

    async def rename(self, message: AstrMessageEvent, title: str) -> None:
        """Rename the current conversation."""
        new_name = title.strip()
        if not new_name:
            await reply_i18n(self.context, message, "conversation.rename.empty")
            return
        await self.context.conversations.update(
            message.unified_msg_origin,
            title=new_name,
        )
        await reply_i18n(self.context, message, "conversation.rename.ok")

    async def delete(self, message: AstrMessageEvent) -> None:
        """Delete the current conversation."""
        umo = message.unified_msg_origin
        if self.context.conversations.third_party_agent_runner(umo):
            self.context.conversations.stop_active_events(umo, exclude=message)
            await self.context.conversations.reset_session_state(umo)
            await reply_i18n(self.context, message, "conversation.delete.cleared")
            return

        current_cid = await self.context.conversations.current_id(umo)
        if not current_cid:
            await reply_i18n(self.context, message, "conversation.delete.none")
            return

        self.context.conversations.stop_active_events(umo, exclude=message)
        await self.context.conversations.delete(umo, current_cid)
        message.set_extra("_clean_group_context_session", True)
        await reply_i18n(self.context, message, "conversation.delete.ok")
