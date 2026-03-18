from __future__ import annotations

from astrbot_sdk.errors import AstrBotError

from ._host import CapabilityMixinHost


class PersonaCapabilityMixin(CapabilityMixinHost):
    def _register_persona_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("persona.get", "Get persona"),
            call_handler=self._persona_get,
        )
        self.register(
            self._builtin_descriptor("persona.list", "List personas"),
            call_handler=self._persona_list,
        )
        self.register(
            self._builtin_descriptor("persona.create", "Create persona"),
            call_handler=self._persona_create,
        )
        self.register(
            self._builtin_descriptor("persona.update", "Update persona"),
            call_handler=self._persona_update,
        )
        self.register(
            self._builtin_descriptor("persona.delete", "Delete persona"),
            call_handler=self._persona_delete,
        )

    async def _persona_get(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        persona_id = str(payload.get("persona_id", "")).strip()
        try:
            persona = await self._star_context.persona_manager.get_persona(persona_id)
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {"persona": self._serialize_persona(persona)}

    async def _persona_list(
        self,
        _request_id: str,
        _payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        personas = await self._star_context.persona_manager.get_all_personas()
        return {
            "personas": [
                payload
                for payload in (
                    self._serialize_persona(persona) for persona in personas
                )
                if payload is not None
            ]
        }

    async def _persona_create(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        raw_persona = payload.get("persona")
        if not isinstance(raw_persona, dict):
            raise AstrBotError.invalid_input("persona.create requires persona object")
        try:
            persona = await self._star_context.persona_manager.create_persona(
                persona_id=str(raw_persona.get("persona_id", "")),
                system_prompt=str(raw_persona.get("system_prompt", "")),
                begin_dialogs=self._normalize_persona_dialogs(
                    raw_persona.get("begin_dialogs")
                ),
                tools=(
                    [str(item) for item in raw_persona.get("tools", [])]
                    if isinstance(raw_persona.get("tools"), list)
                    else None
                ),
                skills=(
                    [str(item) for item in raw_persona.get("skills", [])]
                    if isinstance(raw_persona.get("skills"), list)
                    else None
                ),
                custom_error_message=(
                    str(raw_persona.get("custom_error_message"))
                    if raw_persona.get("custom_error_message") is not None
                    else None
                ),
                folder_id=(
                    str(raw_persona.get("folder_id"))
                    if raw_persona.get("folder_id") is not None
                    else None
                ),
                sort_order=int(raw_persona.get("sort_order", 0)),
            )
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {"persona": self._serialize_persona(persona)}

    async def _persona_update(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        raw_persona = payload.get("persona")
        if not isinstance(raw_persona, dict):
            raise AstrBotError.invalid_input("persona.update requires persona object")
        persona = await self._star_context.persona_manager.update_persona(
            persona_id=str(payload.get("persona_id", "")),
            system_prompt=raw_persona.get("system_prompt"),
            begin_dialogs=(
                self._normalize_persona_dialogs(raw_persona.get("begin_dialogs"))
                if "begin_dialogs" in raw_persona
                else None
            ),
            tools=(
                [str(item) for item in raw_persona.get("tools", [])]
                if isinstance(raw_persona.get("tools"), list)
                else raw_persona.get("tools")
            ),
            skills=(
                [str(item) for item in raw_persona.get("skills", [])]
                if isinstance(raw_persona.get("skills"), list)
                else raw_persona.get("skills")
            ),
            custom_error_message=raw_persona.get("custom_error_message"),
        )
        return {"persona": self._serialize_persona(persona)}

    async def _persona_delete(
        self,
        _request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, object]:
        persona_id = str(payload.get("persona_id", "")).strip()
        try:
            await self._star_context.persona_manager.delete_persona(persona_id)
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {}
