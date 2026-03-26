from __future__ import annotations

from typing import Any

from astrbot_sdk.errors import AstrBotError

from ._host import CapabilityMixinHost


class PermissionCapabilityMixin(CapabilityMixinHost):
    def _register_permission_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("permission.check", "Check user permission role"),
            call_handler=self._permission_check,
        )
        self.register(
            self._builtin_descriptor("permission.get_admins", "List admin ids"),
            call_handler=self._permission_get_admins,
        )
        self.register(
            self._builtin_descriptor(
                "permission.manager.add_admin",
                "Add admin id",
            ),
            call_handler=self._permission_manager_add_admin,
        )
        self.register(
            self._builtin_descriptor(
                "permission.manager.remove_admin",
                "Remove admin id",
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

    def _permission_config(self) -> Any:
        get_config = getattr(self._star_context, "get_config", None)
        if callable(get_config):
            return get_config()
        config = getattr(self._star_context, "_config", None)
        if config is not None:
            return config
        raise AstrBotError.invalid_input("permission capabilities require core config")

    def _admin_ids_snapshot(self, config: Any) -> list[str]:
        admins = self._normalize_admin_ids(
            config.get("admins_id", []) if hasattr(config, "get") else []
        )
        config["admins_id"] = list(admins)
        return admins

    @staticmethod
    def _save_config(config: Any) -> None:
        save_config = getattr(config, "save_config", None)
        if callable(save_config):
            save_config()

    @staticmethod
    def _required_user_id(payload: dict[str, Any], capability_name: str) -> str:
        user_id = str(payload.get("user_id", "")).strip()
        if not user_id:
            raise AstrBotError.invalid_input(f"{capability_name} requires user_id")
        return user_id

    def _require_admin_event_context(
        self,
        request_id: str,
        payload: dict[str, Any],
        capability_name: str,
    ) -> None:
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None or bool(
            getattr(request_context, "cancelled", False)
        ):
            if bool(payload.get("_caller_is_admin", False)):
                return
            raise AstrBotError.invalid_input(
                f"{capability_name} requires an active event context"
            )
        event = getattr(request_context, "event", None)
        if event is None or not callable(getattr(event, "is_admin", None)):
            raise AstrBotError.invalid_input(
                f"{capability_name} requires an active event context"
            )
        # Prefer the authenticated event context whenever one is available.
        # The payload hint is only a fallback for proactive calls that were
        # created from an admin-triggered flow but no longer have a live event.
        if not bool(event.is_admin()):
            raise AstrBotError.invalid_input(
                f"{capability_name} requires admin privileges"
            )

    async def _permission_check(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        user_id = self._required_user_id(payload, "permission.check")
        config = self._permission_config()
        admins = self._admin_ids_snapshot(config)
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
        config = self._permission_config()
        return {"admins": self._admin_ids_snapshot(config)}

    async def _permission_manager_add_admin(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "permission.manager.add_admin")
        self._require_admin_event_context(
            request_id,
            payload,
            "permission.manager.add_admin",
        )
        user_id = self._required_user_id(payload, "permission.manager.add_admin")
        config = self._permission_config()
        admins = self._admin_ids_snapshot(config)
        if user_id in admins:
            return {"changed": False}
        admins.append(user_id)
        config["admins_id"] = admins
        self._save_config(config)
        return {"changed": True}

    async def _permission_manager_remove_admin(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "permission.manager.remove_admin")
        self._require_admin_event_context(
            request_id,
            payload,
            "permission.manager.remove_admin",
        )
        user_id = self._required_user_id(payload, "permission.manager.remove_admin")
        config = self._permission_config()
        admins = self._admin_ids_snapshot(config)
        if user_id not in admins:
            return {"changed": False}
        admins.remove(user_id)
        config["admins_id"] = admins
        self._save_config(config)
        return {"changed": True}
