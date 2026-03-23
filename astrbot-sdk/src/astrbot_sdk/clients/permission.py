"""Permission capability clients."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ._proxy import CapabilityProxy


class PermissionCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_admin: bool
    role: Literal["member", "admin"]

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> PermissionCheckResult | None:
        if not isinstance(payload, dict):
            return None
        return cls.model_validate(payload)


class PermissionClient:
    def __init__(self, proxy: CapabilityProxy) -> None:
        self._proxy = proxy

    async def check(
        self,
        user_id: str,
        session_id: str | None = None,
    ) -> PermissionCheckResult:
        payload: dict[str, Any] = {"user_id": str(user_id)}
        if session_id is not None:
            payload["session_id"] = str(session_id)
        output = await self._proxy.call("permission.check", payload)
        result = PermissionCheckResult.from_payload(output)
        if result is None:
            return PermissionCheckResult(is_admin=False, role="member")
        return result

    async def get_admins(self) -> list[str]:
        output = await self._proxy.call("permission.get_admins", {})
        admins = output.get("admins")
        if not isinstance(admins, list):
            return []
        return [str(item) for item in admins]


class PermissionManagerClient:
    def __init__(
        self,
        proxy: CapabilityProxy,
        *,
        source_event_payload: dict[str, Any] | None = None,
    ) -> None:
        self._proxy = proxy
        self._source_event_payload = (
            dict(source_event_payload) if isinstance(source_event_payload, dict) else {}
        )

    def _caller_is_admin(self) -> bool:
        return bool(self._source_event_payload.get("is_admin", False))

    async def add_admin(self, user_id: str) -> bool:
        output = await self._proxy.call(
            "permission.manager.add_admin",
            {
                "user_id": str(user_id),
                "_caller_is_admin": self._caller_is_admin(),
            },
        )
        return bool(output.get("changed", False))

    async def remove_admin(self, user_id: str) -> bool:
        output = await self._proxy.call(
            "permission.manager.remove_admin",
            {
                "user_id": str(user_id),
                "_caller_is_admin": self._caller_is_admin(),
            },
        )
        return bool(output.get("changed", False))


__all__ = [
    "PermissionCheckResult",
    "PermissionClient",
    "PermissionManagerClient",
]
