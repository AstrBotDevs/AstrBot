from __future__ import annotations

from pathlib import Path
from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


class SkillCapabilityMixin(CapabilityRouterBridgeBase):
    def _register_skill_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("skill.register", "注册插件 skill"),
            call_handler=self._skill_register,
        )
        self.register(
            self._builtin_descriptor("skill.unregister", "注销插件 skill"),
            call_handler=self._skill_unregister,
        )
        self.register(
            self._builtin_descriptor("skill.list", "列出插件 skill"),
            call_handler=self._skill_list,
        )

    async def _skill_register(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, str]:
        plugin_id = self._require_caller_plugin_id("skill.register")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise AstrBotError.invalid_input(f"Unknown plugin: {plugin_id}")

        skill_name = str(payload.get("name", "")).strip()
        if not skill_name:
            raise AstrBotError.invalid_input("skill.register requires name")
        skill_path = str(payload.get("path", "")).strip()
        if not skill_path:
            raise AstrBotError.invalid_input("skill.register requires path")

        path_obj = Path(skill_path)
        skill_dir = path_obj.parent if path_obj.name == "SKILL.md" else path_obj

        entry = {
            "name": skill_name,
            "description": str(payload.get("description", "") or ""),
            "path": skill_path,
            "skill_dir": str(skill_dir),
        }
        plugin.skills[skill_name] = entry
        return dict(entry)

    async def _skill_unregister(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, bool]:
        plugin_id = self._require_caller_plugin_id("skill.unregister")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise AstrBotError.invalid_input(f"Unknown plugin: {plugin_id}")
        removed = (
            plugin.skills.pop(str(payload.get("name", "")).strip(), None) is not None
        )
        return {"removed": removed}

    async def _skill_list(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, list[dict[str, str]]]:
        plugin_id = self._require_caller_plugin_id("skill.list")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise AstrBotError.invalid_input(f"Unknown plugin: {plugin_id}")
        return {
            "skills": [
                dict(plugin.skills[name]) for name in sorted(plugin.skills.keys())
            ]
        }
