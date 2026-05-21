from __future__ import annotations

from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


class PersonaCapabilityMixin(CapabilityRouterBridgeBase):
    async def _persona_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        persona_id = str(payload.get("persona_id", "")).strip()
        record = self._persona_store.get(persona_id)
        if record is None:
            raise AstrBotError.invalid_input(f"persona not found: {persona_id}")
        return {"persona": dict(record)}

    async def _persona_list(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        personas = [
            dict(self._persona_store[persona_id])
            for persona_id in sorted(self._persona_store.keys())
        ]
        return {"personas": personas}

    async def _persona_create(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        raw_persona = payload.get("persona")
        if not isinstance(raw_persona, dict):
            raise AstrBotError.invalid_input("persona.create requires persona object")
        persona_id = str(raw_persona.get("persona_id", "")).strip()
        if not persona_id:
            raise AstrBotError.invalid_input("persona.create requires persona_id")
        if persona_id in self._persona_store:
            raise AstrBotError.invalid_input(f"persona already exists: {persona_id}")
        now = self._now_iso()
        record = {
            "persona_id": persona_id,
            "system_prompt": str(raw_persona.get("system_prompt", "")),
            "begin_dialogs": self._normalize_persona_dialogs_payload(
                raw_persona.get("begin_dialogs")
            ),
            "tools": (
                [str(item) for item in raw_persona.get("tools", [])]
                if isinstance(raw_persona.get("tools"), list)
                else None
            ),
            "skills": (
                [str(item) for item in raw_persona.get("skills", [])]
                if isinstance(raw_persona.get("skills"), list)
                else None
            ),
            "custom_error_message": (
                str(raw_persona.get("custom_error_message"))
                if raw_persona.get("custom_error_message") is not None
                else None
            ),
            "folder_id": (
                str(raw_persona.get("folder_id"))
                if raw_persona.get("folder_id") is not None
                else None
            ),
            "sort_order": int(raw_persona.get("sort_order", 0)),
            "created_at": now,
            "updated_at": now,
        }
        self._persona_store[persona_id] = record
        return {"persona": dict(record)}

    async def _persona_update(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        persona_id = str(payload.get("persona_id", "")).strip()
        record = self._persona_store.get(persona_id)
        if record is None:
            return {"persona": None}
        raw_persona = payload.get("persona")
        if not isinstance(raw_persona, dict):
            raise AstrBotError.invalid_input("persona.update requires persona object")
        if (
            "system_prompt" in raw_persona
            and raw_persona.get("system_prompt") is not None
        ):
            record["system_prompt"] = str(raw_persona.get("system_prompt", ""))
        if "begin_dialogs" in raw_persona:
            begin_dialogs = raw_persona.get("begin_dialogs")
            record["begin_dialogs"] = (
                self._normalize_persona_dialogs_payload(begin_dialogs)
                if begin_dialogs is not None
                else []
            )
        if "tools" in raw_persona:
            tools = raw_persona.get("tools")
            record["tools"] = (
                [str(item) for item in tools] if isinstance(tools, list) else None
            )
        if "skills" in raw_persona:
            skills = raw_persona.get("skills")
            record["skills"] = (
                [str(item) for item in skills] if isinstance(skills, list) else None
            )
        if "custom_error_message" in raw_persona:
            custom_error_message = raw_persona.get("custom_error_message")
            record["custom_error_message"] = (
                str(custom_error_message) if custom_error_message is not None else None
            )
        record["updated_at"] = self._now_iso()
        return {"persona": dict(record)}

    async def _persona_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        persona_id = str(payload.get("persona_id", "")).strip()
        if persona_id not in self._persona_store:
            raise AstrBotError.invalid_input(f"persona not found: {persona_id}")
        del self._persona_store[persona_id]
        return {}

    def _register_persona_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("persona.get", "获取人格"),
            call_handler=self._persona_get,
        )
        self.register(
            self._builtin_descriptor("persona.list", "列出人格"),
            call_handler=self._persona_list,
        )
        self.register(
            self._builtin_descriptor("persona.create", "创建人格"),
            call_handler=self._persona_create,
        )
        self.register(
            self._builtin_descriptor("persona.update", "更新人格"),
            call_handler=self._persona_update,
        )
        self.register(
            self._builtin_descriptor("persona.delete", "删除人格"),
            call_handler=self._persona_delete,
        )
