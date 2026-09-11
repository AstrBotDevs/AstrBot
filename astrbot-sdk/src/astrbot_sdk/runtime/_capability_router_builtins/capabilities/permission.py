from __future__ import annotations

from typing import Any

from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


class PermissionCapabilityMixin(CapabilityRouterBridgeBase):
    def _register_permission_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("permission.check", "查询用户权限角色"),
            call_handler=self._permission_check,
        )
        self.register(
            self._builtin_descriptor("permission.get_admins", "列出管理员 ID"),
            call_handler=self._permission_get_admins,
        )
        self.register(
            self._builtin_descriptor(
                "permission.manager.add_admin",
                "添加管理员 ID",
            ),
            call_handler=self._permission_manager_add_admin,
        )
        self.register(
            self._builtin_descriptor(
                "permission.manager.remove_admin",
                "移除管理员 ID",
            ),
            call_handler=self._permission_manager_remove_admin,
        )

    @staticmethod
    def _normalize_admin_ids(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized: list[str] = []
        for item in values:
            user_id = str(item).strip()
            if user_id:
                normalized.append(user_id)
        return normalized

    def _admin_ids_snapshot(self) -> list[str]:
        normalized = self._normalize_admin_ids(
            getattr(self, "_permission_admin_ids", [])
        )
        self._permission_admin_ids = list(normalized)
        return normalized

    @staticmethod
    def _required_user_id(payload: dict[str, Any], capability_name: str) -> str:
        user_id = str(payload.get("user_id", "")).strip()
        if not user_id:
            raise AstrBotError.invalid_input(f"{capability_name} requires user_id")
        return user_id

    def _require_reserved_plugin(self, capability_name: str) -> str:
        plugin_id = self._require_caller_plugin_id(capability_name)
        plugin = self._plugins.get(plugin_id)
        if plugin is not None and bool(plugin.metadata.get("reserved", False)):
            return plugin_id
        if plugin_id in {"system", "__system__"}:
            return plugin_id
        raise AstrBotError.invalid_input(
            f"{capability_name} is restricted to reserved/system plugins"
        )

    @staticmethod
    def _require_admin_event_context(
        payload: dict[str, Any],
        capability_name: str,
    ) -> None:
        if bool(payload.get("_caller_is_admin", False)):
            return
        raise AstrBotError.invalid_input(
            f"{capability_name} requires an active admin event context"
        )

    async def _permission_check(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        user_id = self._required_user_id(payload, "permission.check")
        admins = self._admin_ids_snapshot()
        is_admin = user_id in admins
        return {
            "is_admin": is_admin,
            "role": "admin" if is_admin else "member",
        }

    async def _permission_get_admins(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return {"admins": self._admin_ids_snapshot()}

    async def _permission_manager_add_admin(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin("permission.manager.add_admin")
        self._require_admin_event_context(payload, "permission.manager.add_admin")
        user_id = self._required_user_id(payload, "permission.manager.add_admin")
        admins = self._admin_ids_snapshot()
        if user_id in admins:
            return {"changed": False}
        admins.append(user_id)
        self._permission_admin_ids = admins
        return {"changed": True}

    async def _permission_manager_remove_admin(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin("permission.manager.remove_admin")
        self._require_admin_event_context(payload, "permission.manager.remove_admin")
        user_id = self._required_user_id(payload, "permission.manager.remove_admin")
        admins = self._admin_ids_snapshot()
        if user_id not in admins:
            return {"changed": False}
        admins.remove(user_id)
        self._permission_admin_ids = admins
        return {"changed": True}
