from __future__ import annotations

from astrbot.core import logger

from ._host import CapabilityMixinHost


class SkillCapabilityMixin(CapabilityMixinHost):
    def _register_skill_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("skill.register", "Register SDK skill"),
            call_handler=self._skill_register,
        )
        self.register(
            self._builtin_descriptor("skill.unregister", "Unregister SDK skill"),
            call_handler=self._skill_unregister,
        )
        self.register(
            self._builtin_descriptor("skill.list", "List SDK skills"),
            call_handler=self._skill_list,
        )

    async def _skill_register(
        self,
        request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, str]:
        plugin_id = self._resolve_plugin_id(request_id)
        result = self._plugin_bridge.register_skill(
            plugin_id=plugin_id,
            name=str(payload.get("name", "")),
            path=str(payload.get("path", "")),
            description=str(payload.get("description", "")),
        )
        await self._sync_registered_skills_to_sandboxes()
        return result

    async def _skill_unregister(
        self,
        request_id: str,
        payload: dict[str, object],
        _token,
    ) -> dict[str, bool]:
        plugin_id = self._resolve_plugin_id(request_id)
        removed = self._plugin_bridge.unregister_skill(
            plugin_id=plugin_id,
            name=str(payload.get("name", "")),
        )
        if removed:
            await self._sync_registered_skills_to_sandboxes()
        return {"removed": removed}

    async def _skill_list(
        self,
        request_id: str,
        _payload: dict[str, object],
        _token,
    ) -> dict[str, list[dict[str, str]]]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {"skills": self._plugin_bridge.list_registered_skills(plugin_id)}

    async def _sync_registered_skills_to_sandboxes(self) -> None:
        try:
            from astrbot.core.computer.computer_client import (
                sync_skills_to_active_sandboxes,
            )

            await sync_skills_to_active_sandboxes()
        except Exception as exc:
            logger.warning(
                "Failed to sync skills to active sandboxes after SDK skill update: %s",
                exc,
            )
