from __future__ import annotations

from astrbot_sdk.errors import AstrBotError

from ._host import CapabilityMixinHost


class ConversationCapabilityMixin(CapabilityMixinHost):
    def _register_conversation_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("conversation.new", "Create conversation"),
            call_handler=self._conversation_new,
        )
        self.register(
            self._builtin_descriptor("conversation.switch", "Switch conversation"),
            call_handler=self._conversation_switch,
        )
        self.register(
            self._builtin_descriptor("conversation.delete", "Delete conversation"),
            call_handler=self._conversation_delete,
        )
        self.register(
            self._builtin_descriptor("conversation.get", "Get conversation"),
            call_handler=self._conversation_get,
        )
        self.register(
            self._builtin_descriptor(
                "conversation.get_current",
                "Get current conversation",
            ),
            call_handler=self._conversation_get_current,
        )
        self.register(
            self._builtin_descriptor("conversation.list", "List conversations"),
            call_handler=self._conversation_list,
        )
        self.register(
            self._builtin_descriptor("conversation.update", "Update conversation"),
            call_handler=self._conversation_update,
        )

    async def _conversation_new(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = str(payload.get("session", "")).strip()
        if not session:
            raise AstrBotError.invalid_input("conversation.new requires session")
        raw_conversation = payload.get("conversation")
        if raw_conversation is None:
            raw_conversation = {}
        if not isinstance(raw_conversation, dict):
            raise AstrBotError.invalid_input(
                "conversation.new requires conversation object"
            )
        conversation_id = (
            await self._star_context.conversation_manager.new_conversation(
                unified_msg_origin=session,
                platform_id=(
                    str(raw_conversation.get("platform_id"))
                    if raw_conversation.get("platform_id") is not None
                    else None
                ),
                content=self._normalize_history_items(raw_conversation.get("history")),
                title=(
                    str(raw_conversation.get("title"))
                    if raw_conversation.get("title") is not None
                    else None
                ),
                persona_id=(
                    str(raw_conversation.get("persona_id"))
                    if raw_conversation.get("persona_id") is not None
                    else None
                ),
            )
        )
        return {"conversation_id": conversation_id}

    async def _conversation_switch(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = str(payload.get("session", "")).strip()
        conversation_id = str(payload.get("conversation_id", "")).strip()
        if not session:
            raise AstrBotError.invalid_input("conversation.switch requires session")
        if not conversation_id:
            raise AstrBotError.invalid_input(
                "conversation.switch requires conversation_id"
            )
        await self._star_context.conversation_manager.switch_conversation(
            unified_msg_origin=session,
            conversation_id=conversation_id,
        )
        return {}

    async def _conversation_delete(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        await self._star_context.conversation_manager.delete_conversation(
            unified_msg_origin=str(payload.get("session", "")),
            conversation_id=(
                str(payload.get("conversation_id"))
                if payload.get("conversation_id") is not None
                else None
            ),
        )
        return {}

    async def _conversation_get(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        conversation = await self._star_context.conversation_manager.get_conversation(
            unified_msg_origin=str(payload.get("session", "")),
            conversation_id=str(payload.get("conversation_id", "")),
            create_if_not_exists=bool(payload.get("create_if_not_exists", False)),
        )
        return {"conversation": self._serialize_conversation(conversation)}

    async def _conversation_get_current(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = str(payload.get("session", ""))
        conversation_id = (
            await self._star_context.conversation_manager.get_curr_conversation_id(
                session
            )
        )
        if not conversation_id and bool(payload.get("create_if_not_exists", False)):
            conversation_id = (
                await self._star_context.conversation_manager.new_conversation(session)
            )
        if not conversation_id:
            return {"conversation": None}
        conversation = await self._star_context.conversation_manager.get_conversation(
            unified_msg_origin=session,
            conversation_id=conversation_id,
            create_if_not_exists=bool(payload.get("create_if_not_exists", False)),
        )
        return {"conversation": self._serialize_conversation(conversation)}

    async def _conversation_list(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        session = payload.get("session")
        platform_id = payload.get("platform_id")
        conversations = await self._star_context.conversation_manager.get_conversations(
            unified_msg_origin=(
                str(session) if session is not None and str(session).strip() else None
            ),
            platform_id=(
                str(platform_id)
                if platform_id is not None and str(platform_id).strip()
                else None
            ),
        )
        return {
            "conversations": [
                item
                for item in (
                    self._serialize_conversation(conversation)
                    for conversation in conversations
                )
                if item is not None
            ]
        }

    async def _conversation_update(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        raw_conversation = payload.get("conversation")
        if raw_conversation is None:
            raw_conversation = {}
        if not isinstance(raw_conversation, dict):
            raise AstrBotError.invalid_input(
                "conversation.update requires conversation object"
            )
        await self._star_context.conversation_manager.update_conversation(
            unified_msg_origin=str(payload.get("session", "")),
            conversation_id=(
                str(payload.get("conversation_id"))
                if payload.get("conversation_id") is not None
                else None
            ),
            history=(
                self._normalize_history_items(raw_conversation.get("history"))
                if "history" in raw_conversation
                else None
            ),
            title=(
                str(raw_conversation.get("title"))
                if raw_conversation.get("title") is not None
                else None
            ),
            persona_id=(
                str(raw_conversation.get("persona_id"))
                if raw_conversation.get("persona_id") is not None
                else None
            ),
            token_usage=self._optional_int(raw_conversation.get("token_usage")),
        )
        return {}
