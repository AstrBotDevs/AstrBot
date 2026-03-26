# ruff: noqa: E402
from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})


_install_optional_dependency_stubs()

from astrbot_sdk.errors import AstrBotError

from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge


class _FakeCancelToken:
    def raise_if_cancelled(self) -> None:
        return None


class _FakeConfig(dict):
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        super().__init__(initial or {})
        self.save_calls = 0

    def save_config(self) -> None:
        self.save_calls += 1


class _FakeEvent:
    def __init__(self, *, admin: bool) -> None:
        self._admin = admin

    def is_admin(self) -> bool:
        return self._admin


@dataclass(slots=True)
class _FakeRequestContext:
    event: _FakeEvent
    cancelled: bool = False
    has_event: bool = True


class _FakePluginBridge:
    def __init__(self) -> None:
        self._plugin_ids = {
            "reserved-admin-request": "reserved-plugin",
            "reserved-viewer-request": "reserved-plugin",
            "reserved-no-event-request": "reserved-plugin",
            "plain-request": "plain-plugin",
        }
        self._contexts = {
            "reserved-admin-request": _FakeRequestContext(_FakeEvent(admin=True)),
            "reserved-viewer-request": _FakeRequestContext(_FakeEvent(admin=False)),
        }

    def resolve_request_plugin_id(self, request_id: str) -> str:
        return self._plugin_ids[request_id]

    def resolve_request_session(self, request_id: str) -> _FakeRequestContext | None:
        return self._contexts.get(request_id)

    def get_request_context_by_token(self, _dispatch_token: str):
        return None


class _FakeStarContext:
    def __init__(self, config: _FakeConfig) -> None:
        self._config = config

    def get_config(self) -> _FakeConfig:
        return self._config

    def get_all_stars(self) -> list[object]:
        return [
            types.SimpleNamespace(name="reserved-plugin", reserved=True),
            types.SimpleNamespace(name="plain-plugin", reserved=False),
        ]


async def _call(
    bridge: CoreCapabilityBridge,
    capability: str,
    payload: dict[str, object],
    *,
    request_id: str,
) -> dict[str, object]:
    result = await bridge.execute(
        capability,
        payload,
        stream=False,
        cancel_token=_FakeCancelToken(),
        request_id=request_id,
    )
    assert isinstance(result, dict)
    return result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_permission_reads_and_mutates_single_admin_source() -> None:
    config = _FakeConfig({"admins_id": ["root", "maintainer", ""]})
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(config),
        plugin_bridge=_FakePluginBridge(),
    )

    root_check = await _call(
        bridge,
        "permission.check",
        {"user_id": "root", "session_id": "demo:group:42"},
        request_id="plain-request",
    )
    member_check = await _call(
        bridge,
        "permission.check",
        {"user_id": "guest"},
        request_id="plain-request",
    )
    admins = await _call(
        bridge,
        "permission.get_admins",
        {},
        request_id="plain-request",
    )

    assert root_check == {"is_admin": True, "role": "admin"}
    assert member_check == {"is_admin": False, "role": "member"}
    assert admins == {"admins": ["root", "maintainer"]}

    with pytest.raises(AstrBotError, match="reserved/system"):
        await _call(
            bridge,
            "permission.manager.add_admin",
            {"user_id": "alice"},
            request_id="plain-request",
        )

    with pytest.raises(AstrBotError, match="admin privileges"):
        await _call(
            bridge,
            "permission.manager.add_admin",
            {"user_id": "alice"},
            request_id="reserved-viewer-request",
        )

    with pytest.raises(AstrBotError, match="active event context"):
        await _call(
            bridge,
            "permission.manager.add_admin",
            {"user_id": "alice"},
            request_id="reserved-no-event-request",
        )

    added_without_event = await _call(
        bridge,
        "permission.manager.add_admin",
        {"user_id": "alice", "_caller_is_admin": True},
        request_id="reserved-no-event-request",
    )
    removed_without_event = await _call(
        bridge,
        "permission.manager.remove_admin",
        {"user_id": "alice", "_caller_is_admin": True},
        request_id="reserved-no-event-request",
    )

    with pytest.raises(AstrBotError, match="admin privileges"):
        await _call(
            bridge,
            "permission.manager.add_admin",
            {"user_id": "alice", "_caller_is_admin": True},
            request_id="reserved-viewer-request",
        )

    added = await _call(
        bridge,
        "permission.manager.add_admin",
        {"user_id": "alice"},
        request_id="reserved-admin-request",
    )
    added_again = await _call(
        bridge,
        "permission.manager.add_admin",
        {"user_id": "alice"},
        request_id="reserved-admin-request",
    )
    removed = await _call(
        bridge,
        "permission.manager.remove_admin",
        {"user_id": "alice"},
        request_id="reserved-admin-request",
    )
    removed_again = await _call(
        bridge,
        "permission.manager.remove_admin",
        {"user_id": "alice"},
        request_id="reserved-admin-request",
    )

    assert added_without_event == {"changed": True}
    assert removed_without_event == {"changed": True}
    assert added == {"changed": True}
    assert added_again == {"changed": False}
    assert removed == {"changed": True}
    assert removed_again == {"changed": False}
    assert config["admins_id"] == ["root", "maintainer"]
    assert config.save_calls == 4
