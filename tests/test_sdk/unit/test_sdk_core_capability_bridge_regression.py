# ruff: noqa: E402
from __future__ import annotations

import sys
import types
from types import SimpleNamespace

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

from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge


class _FakePluginBridge:
    def __init__(self) -> None:
        self.configs = {"ai_girlfriend": {"enable_morning": True}}

    def resolve_request_plugin_id(self, _request_id: str) -> str:
        return "ai_girlfriend"

    def get_plugin_config(self, plugin_id: str) -> dict[str, object] | None:
        return self.configs.get(plugin_id)

    def get_plugin_metadata(self, plugin_id: str) -> dict[str, object] | None:
        return {"name": plugin_id}

    def list_plugin_metadata(self) -> list[dict[str, object]]:
        return [{"name": "ai_girlfriend"}]

    def resolve_request_session(self, _request_id: str):
        return SimpleNamespace(event=SimpleNamespace(unified_msg_origin="umo:test"))


class _FakeStarContext:
    def get_all_stars(self):
        return []


class _FakeCancelToken:
    def raise_if_cancelled(self) -> None:
        return None


@pytest.mark.unit
def test_core_capability_bridge_keeps_runtime_router_methods() -> None:
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(),
        plugin_bridge=_FakePluginBridge(),
    )

    assert CoreCapabilityBridge.register.__qualname__ == "CapabilityRouter.register"
    assert len(bridge._registrations) > 0
    assert "metadata.get_plugin_config" in bridge._registrations


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_capability_bridge_serves_registered_plugin_config() -> None:
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(),
        plugin_bridge=_FakePluginBridge(),
    )

    payload = {"name": "ai_girlfriend"}
    result = await bridge.execute(
        "metadata.get_plugin_config",
        payload,
        stream=False,
        cancel_token=_FakeCancelToken(),
        request_id="req-1",
    )

    assert result == {"config": {"enable_morning": True}}
