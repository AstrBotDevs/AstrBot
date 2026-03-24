from __future__ import annotations

from typing import Any

import pytest

from astrbot_sdk.clients.permission import PermissionClient, PermissionManagerClient


class _FakeProxy:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, dict(payload)))
        return dict(self.responses.get(name, {}))


@pytest.mark.asyncio
async def test_permission_client_check_preserves_optional_session_id() -> None:
    proxy = _FakeProxy({"permission.check": {"is_admin": True, "role": "admin"}})
    client = PermissionClient(proxy)  # type: ignore[arg-type]

    result = await client.check("user-1", session_id="demo:group:42")

    assert proxy.calls == [
        (
            "permission.check",
            {"user_id": "user-1", "session_id": "demo:group:42"},
        )
    ]
    assert result.is_admin is True
    assert result.role == "admin"


@pytest.mark.asyncio
async def test_permission_client_get_admins_returns_strings() -> None:
    proxy = _FakeProxy({"permission.get_admins": {"admins": ["alpha", 42]}})
    client = PermissionClient(proxy)  # type: ignore[arg-type]

    admins = await client.get_admins()

    assert proxy.calls == [("permission.get_admins", {})]
    assert admins == ["alpha", "42"]


@pytest.mark.asyncio
async def test_permission_manager_client_forwards_admin_event_flag() -> None:
    proxy = _FakeProxy({"permission.manager.add_admin": {"changed": True}})
    client = PermissionManagerClient(
        proxy,  # type: ignore[arg-type]
        source_event_payload={"is_admin": True},
    )

    changed = await client.add_admin("user-2")

    assert changed is True
    assert proxy.calls == [
        (
            "permission.manager.add_admin",
            {"user_id": "user-2", "_caller_is_admin": True},
        )
    ]


@pytest.mark.asyncio
async def test_permission_manager_client_remove_admin_defaults_to_non_admin_context() -> (
    None
):
    proxy = _FakeProxy({"permission.manager.remove_admin": {"changed": False}})
    client = PermissionManagerClient(proxy)  # type: ignore[arg-type]

    changed = await client.remove_admin("user-2")

    assert changed is False
    assert proxy.calls == [
        (
            "permission.manager.remove_admin",
            {"user_id": "user-2", "_caller_is_admin": False},
        )
    ]
