from __future__ import annotations

import uuid
from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


class ConversationCapabilityMixin(CapabilityRouterBridgeBase):
    async def _conversation_new(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
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
        conversation_id = uuid.uuid4().hex
        now = self._now_iso()
        record = {
            "conversation_id": conversation_id,
            "session": session,
            "platform_id": (
                str(raw_conversation.get("platform_id"))
                if raw_conversation.get("platform_id") is not None
                else self._session_platform_id(session)
            ),
            "history": self._normalize_history_payload(raw_conversation.get("history")),
            "title": (
                str(raw_conversation.get("title"))
                if raw_conversation.get("title") is not None
                else None
            ),
            "persona_id": (
                str(raw_conversation.get("persona_id"))
                if raw_conversation.get("persona_id") is not None
                else None
            ),
            "created_at": now,
            "updated_at": now,
            "token_usage": None,
        }
        self._conversation_store[conversation_id] = record
        self._session_current_conversation_ids[session] = conversation_id
        return {"conversation_id": conversation_id}

    async def _conversation_switch(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = str(payload.get("conversation_id", "")).strip()
        record = self._conversation_store.get(conversation_id)
        if record is None or str(record.get("session", "")) != session:
            raise AstrBotError.invalid_input(
                "conversation.switch requires a conversation in the same session"
            )
        self._session_current_conversation_ids[session] = conversation_id
        return {}

    async def _conversation_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = payload.get("conversation_id")
        normalized_conversation_id = (
            str(conversation_id).strip() if conversation_id is not None else ""
        )
        if not normalized_conversation_id:
            normalized_conversation_id = self._session_current_conversation_ids.get(
                session, ""
            )
        if not normalized_conversation_id:
            return {}
        record = self._conversation_store.get(normalized_conversation_id)
        if record is None:
            return {}
        if str(record.get("session", "")) != session:
            raise AstrBotError.invalid_input(
                "conversation.delete requires a conversation in the same session"
            )
        del self._conversation_store[normalized_conversation_id]
        current_conversation_id = self._session_current_conversation_ids.get(session)
        if current_conversation_id == normalized_conversation_id:
            replacement = next(
                (
                    conversation_id
                    for conversation_id, item in self._conversation_store.items()
                    if str(item.get("session", "")) == session
                ),
                None,
            )
            if replacement is None:
                self._session_current_conversation_ids.pop(session, None)
            else:
                self._session_current_conversation_ids[session] = replacement
        return {}

    async def _conversation_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = str(payload.get("conversation_id", "")).strip()
        record = self._conversation_store.get(conversation_id)
        if record is None and bool(payload.get("create_if_not_exists", False)):
            created = await self._conversation_new(
                _request_id,
                {"session": session, "conversation": {}},
                _token,
            )
            record = self._conversation_store.get(
                str(created.get("conversation_id", "")).strip()
            )
        if record is None:
            return {"conversation": None}
        if str(record.get("session", "")) != session:
            return {"conversation": None}
        return {"conversation": dict(record)}

    async def _conversation_get_current(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = self._session_current_conversation_ids.get(session, "")
        if not conversation_id and bool(payload.get("create_if_not_exists", False)):
            created = await self._conversation_new(
                _request_id,
                {"session": session, "conversation": {}},
                _token,
            )
            conversation_id = str(created.get("conversation_id", "")).strip()
        if not conversation_id:
            return {"conversation": None}
        record = self._conversation_store.get(conversation_id)
        if record is None or str(record.get("session", "")) != session:
            return {"conversation": None}
        return {"conversation": dict(record)}

    async def _conversation_list(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = payload.get("session")
        platform_id = payload.get("platform_id")
        conversations = []
        for conversation_id in sorted(self._conversation_store.keys()):
            item = self._conversation_store[conversation_id]
            if session is not None and str(item.get("session", "")) != str(session):
                continue
            if platform_id is not None and str(item.get("platform_id", "")) != str(
                platform_id
            ):
                continue
            conversations.append(dict(item))
        return {"conversations": conversations}

    async def _conversation_update(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = payload.get("conversation_id")
        normalized_conversation_id = (
            str(conversation_id).strip() if conversation_id is not None else ""
        )
        if not normalized_conversation_id:
            normalized_conversation_id = self._session_current_conversation_ids.get(
                session, ""
            )
        if not normalized_conversation_id:
            return {}
        record = self._conversation_store.get(normalized_conversation_id)
        if record is None:
            return {}
        if str(record.get("session", "")) != session:
            raise AstrBotError.invalid_input(
                "conversation.update requires a conversation in the same session"
            )
        raw_conversation = payload.get("conversation")
        if not isinstance(raw_conversation, dict):
            raw_conversation = {}
        if "history" in raw_conversation:
            history = raw_conversation.get("history")
            record["history"] = (
                self._normalize_history_payload(history) if history is not None else []
            )
        if "title" in raw_conversation:
            title = raw_conversation.get("title")
            record["title"] = str(title) if title is not None else None
        if "persona_id" in raw_conversation:
            persona_id = raw_conversation.get("persona_id")
            record["persona_id"] = str(persona_id) if persona_id is not None else None
        if "token_usage" in raw_conversation:
            token_usage = raw_conversation.get("token_usage")
            record["token_usage"] = (
                int(token_usage) if token_usage is not None else None
            )
        record["updated_at"] = self._now_iso()
        return {}

    def _register_conversation_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("conversation.new", "新建对话"),
            call_handler=self._conversation_new,
        )
        self.register(
            self._builtin_descriptor("conversation.switch", "切换对话"),
            call_handler=self._conversation_switch,
        )
        self.register(
            self._builtin_descriptor("conversation.delete", "删除对话"),
            call_handler=self._conversation_delete,
        )
        self.register(
            self._builtin_descriptor("conversation.get", "获取对话"),
            call_handler=self._conversation_get,
        )
        self.register(
            self._builtin_descriptor("conversation.get_current", "获取当前对话"),
            call_handler=self._conversation_get_current,
        )
        self.register(
            self._builtin_descriptor("conversation.list", "列出对话"),
            call_handler=self._conversation_list,
        )
        self.register(
            self._builtin_descriptor("conversation.update", "更新对话"),
            call_handler=self._conversation_update,
        )
