# ruff: noqa: E402
from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

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
    install(
        "aiocqhttp",
        {
            "CQHttp": type("CQHttp", (), {}),
            "Event": type("Event", (), {}),
        },
    )
    install(
        "aiocqhttp.exceptions",
        {"ActionFailed": type("ActionFailed", (Exception,), {})},
    )


_install_optional_dependency_stubs()

from astrbot_sdk import PlatformStatus
from astrbot_sdk._invocation_context import caller_plugin_scope
from astrbot_sdk.clients.provider import ProviderManagerClient
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.llm.entities import ProviderType
from astrbot_sdk.testing import MockContext

from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_p1_3_merged_provider_config_is_reserved_only() -> None:
    ordinary_ctx = MockContext(plugin_id="plain-plugin")
    with caller_plugin_scope("plain-plugin"):
        with pytest.raises(AstrBotError, match="reserved/system"):
            await ordinary_ctx.mock_peer.invoke(
                "provider.manager.get_merged_provider_config",
                {"provider_id": "mock-chat-provider"},
            )

    ctx = MockContext(
        plugin_id="reserved-plugin",
        plugin_metadata={"reserved": True},
    )
    assert (
        "provider.manager.get_merged_provider_config"
        in ctx.mock_peer.remote_capability_map
    )
    with caller_plugin_scope("reserved-plugin"):
        output = await ctx.mock_peer.invoke(
            "provider.manager.get_merged_provider_config",
            {"provider_id": "mock-chat-provider"},
        )
    assert output["config"]["id"] == "mock-chat-provider"
    assert output["config"]["provider_type"] == "chat_completion"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_p1_3_merged_provider_config_keeps_nested_payload() -> None:
    ctx = MockContext(
        plugin_id="reserved-plugin",
        plugin_metadata={"reserved": True},
    )
    nested_config = {
        "id": "mock-chat-provider",
        "type": "mock",
        "provider_type": "chat_completion",
        "enable": True,
        "provider_settings": {
            "headers": {"x-trace-id": "trace-1"},
            "options": {"temperature": 0.2, "top_p": 0.9},
        },
    }
    ctx.router._provider_configs["mock-chat-provider"] = dict(nested_config)

    with caller_plugin_scope("reserved-plugin"):
        output = await ctx.mock_peer.invoke(
            "provider.manager.get_merged_provider_config",
            {"provider_id": "mock-chat-provider"},
        )

    assert output["config"]["provider_settings"] == nested_config["provider_settings"]
    assert output["config"]["enable"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_provider_client_get_merged_provider_config_returns_plain_dict_copy() -> (
    None
):
    ctx = MockContext(
        plugin_id="reserved-plugin",
        plugin_metadata={"reserved": True},
    )
    nested_config = {
        "id": "mock-chat-provider",
        "type": "mock",
        "provider_type": "chat_completion",
        "enable": True,
        "provider_settings": {
            "headers": {"x-trace-id": "trace-2"},
            "options": {"temperature": 0.3},
        },
    }
    ctx.router._provider_configs["mock-chat-provider"] = dict(nested_config)

    output = await ctx.provider_manager.get_merged_provider_config("mock-chat-provider")

    assert output is not None
    assert output["id"] == nested_config["id"]
    assert output["type"] == nested_config["type"]
    assert output["provider_type"] == nested_config["provider_type"]
    assert output["enable"] is True
    assert output["provider_settings"] == nested_config["provider_settings"]
    assert output is not ctx.router._provider_configs["mock-chat-provider"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_provider_client_get_merged_provider_config_strips_provider_id() -> None:
    class _RecordingProxy:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        async def call(
            self,
            capability: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            self.calls.append((capability, dict(payload)))
            return {"config": {"id": "mock-chat-provider"}}

    proxy = _RecordingProxy()
    client = ProviderManagerClient(cast(Any, proxy))

    output = await client.get_merged_provider_config("  mock-chat-provider  ")

    assert output == {"id": "mock-chat-provider"}
    assert proxy.calls == [
        (
            "provider.manager.get_merged_provider_config",
            {"provider_id": "mock-chat-provider"},
        )
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_provider_client_get_merged_provider_config_rejects_non_reserved_plugin() -> (
    None
):
    ctx = MockContext(plugin_id="plain-plugin")

    with pytest.raises(AstrBotError, match="reserved/system"):
        await ctx.provider_manager.get_merged_provider_config("mock-chat-provider")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_p1_3_provider_management_is_reserved_only() -> None:
    ordinary_ctx = MockContext(plugin_id="plain-plugin")
    with pytest.raises(AstrBotError, match="reserved/system"):
        await ordinary_ctx.provider_manager.get_insts()

    ctx = MockContext(
        plugin_id="reserved-plugin",
        plugin_metadata={"reserved": True},
    )
    insts = await ctx.provider_manager.get_insts()
    assert [item.id for item in insts] == ["mock-chat-provider"]

    stream = ctx.provider_manager.watch_changes()

    async def _next_provider_change() -> Any:
        return await anext(stream)

    waiter = asyncio.create_task(_next_provider_change())
    await asyncio.sleep(0)
    await ctx.provider_manager.set_provider(
        "mock-chat-provider",
        ProviderType.CHAT_COMPLETION,
        umo="demo-session",
    )
    event = await asyncio.wait_for(waiter, timeout=1)
    assert event.provider_id == "mock-chat-provider"
    assert event.provider_type == ProviderType.CHAT_COMPLETION
    assert event.umo == "demo-session"
    await cast(Any, stream).aclose()

    callback_ready = asyncio.Event()
    seen: list[tuple[str, ProviderType, str | None]] = []

    async def on_change(
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None,
    ) -> None:
        seen.append((provider_id, provider_type, umo))
        callback_ready.set()

    task = await ctx.provider_manager.register_provider_change_hook(on_change)
    await asyncio.sleep(0)
    ctx.router.emit_provider_change(
        "mock-chat-provider",
        ProviderType.CHAT_COMPLETION.value,
        "umo-2",
    )
    await asyncio.wait_for(callback_ready.wait(), timeout=1)
    assert seen == [("mock-chat-provider", ProviderType.CHAT_COMPLETION, "umo-2")]
    await ctx.provider_manager.unregister_provider_change_hook(task)
    assert task.done()
    callback_ready.clear()
    ctx.router.emit_provider_change(
        "mock-chat-provider",
        ProviderType.CHAT_COMPLETION.value,
        "umo-3",
    )
    await asyncio.sleep(0.05)
    assert seen == [("mock-chat-provider", ProviderType.CHAT_COMPLETION, "umo-2")]
    assert callback_ready.is_set() is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_p1_3_platform_facade_refresh_and_clear_errors() -> None:
    ordinary_ctx = MockContext(plugin_id="plain-plugin")
    ordinary_platform = await ordinary_ctx.get_platform_inst("mock-platform")
    assert ordinary_platform is not None
    with pytest.raises(AstrBotError, match="reserved/system"):
        await ordinary_platform.refresh()

    ctx = MockContext(
        plugin_id="reserved-plugin",
        plugin_metadata={"reserved": True},
    )
    error_payload = {
        "message": "boom",
        "timestamp": "2026-03-16T00:00:00+00:00",
        "traceback": "traceback",
    }
    ctx.router.set_platform_instances([
        {
            "id": "mock-platform",
            "name": "Mock Platform",
            "type": "mock",
            "status": "error",
            "errors": [error_payload],
            "last_error": error_payload,
            "unified_webhook": True,
            "stats": {
                "id": "mock-platform",
                "type": "mock",
                "display_name": "Mock Platform",
                "status": "error",
                "started_at": None,
                "error_count": 1,
                "last_error": error_payload,
                "unified_webhook": True,
                "meta": {"support_streaming_message": True},
            },
        }
    ])

    platform = await ctx.get_platform_inst("mock-platform")
    assert platform is not None
    assert platform.status == PlatformStatus.ERROR
    await platform.refresh()
    assert platform.unified_webhook is True
    assert platform.last_error is not None
    assert platform.last_error.message == "boom"
    await asyncio.gather(platform.refresh(), platform.refresh())
    stats = await platform.get_stats()
    assert stats is not None
    assert stats.status == PlatformStatus.ERROR
    assert stats.error_count == 1
    await platform.clear_errors()
    assert platform.status == PlatformStatus.RUNNING
    assert platform.errors == []
    assert platform.last_error is None


@dataclass(slots=True)
class _FakeProviderMeta:
    id: str
    model: str | None
    type: str
    provider_type: object


class _FakeProvider:
    def __init__(
        self, provider_id: str, provider_type: str, model: str = "demo"
    ) -> None:
        self.provider_config = {
            "id": provider_id,
            "type": "mock",
            "provider_type": provider_type,
            "enable": True,
        }
        self._meta = _FakeProviderMeta(
            id=provider_id,
            model=model,
            type="mock",
            provider_type=provider_type,
        )

    def meta(self) -> _FakeProviderMeta:
        return self._meta


class _FakeProviderManager:
    def __init__(self) -> None:
        self.providers_config = [
            {
                "id": "chat-main",
                "type": "mock",
                "provider_type": "chat_completion",
                "enable": True,
                "provider_source_id": "shared-source",
                "model_config": {"temperature": 0.6},
                "provider_settings": {
                    "headers": {"x-provider": "chat-main"},
                    "options": {
                        "temperature": 0.6,
                        "penalties": {"frequency": 0.1},
                    },
                },
            },
            {
                "id": "chat-disabled",
                "type": "mock",
                "provider_type": "chat_completion",
                "enable": False,
            },
        ]
        self.provider_sources_config = [
            {
                "id": "shared-source",
                "endpoint": "https://example.invalid/v1",
                "headers": {"x-source": "provider-source"},
                "model_config": {"temperature": 0.3, "top_p": 0.95},
                "source_metadata": {
                    "routing": {
                        "primary": "edge-a",
                        "fallbacks": ["edge-b", "edge-c"],
                    }
                },
            }
        ]
        self.inst_map = {"chat-main": _FakeProvider("chat-main", "chat_completion")}
        self.provider_insts = [self.inst_map["chat-main"]]
        self._hooks: list[Callable[[str, str, str | None], object]] = []

    def get_insts(self) -> list[object]:
        return list(self.provider_insts)

    def register_provider_change_hook(
        self, hook: Callable[[str, str, str | None], object]
    ) -> None:
        self._hooks.append(hook)

    def unregister_provider_change_hook(
        self, hook: Callable[[str, str, str | None], object]
    ) -> None:
        if hook in self._hooks:
            self._hooks.remove(hook)

    def fire_change(
        self, provider_id: str, provider_type: str, umo: str | None
    ) -> None:
        for hook in list(self._hooks):
            hook(provider_id, provider_type, umo)

    def get_merged_provider_config(
        self, provider_config: dict[str, object]
    ) -> dict[str, object]:
        merged = dict(provider_config)
        provider_source_id = merged.get("provider_source_id")
        if not isinstance(provider_source_id, str) or not provider_source_id:
            return merged
        provider_source = next(
            (
                item
                for item in self.provider_sources_config
                if item.get("id") == provider_source_id
            ),
            None,
        )
        if not isinstance(provider_source, dict):
            return merged
        merged = {**provider_source, **merged}
        merged["id"] = str(provider_config["id"])
        return merged


@dataclass(slots=True)
class _FakePlatformError:
    message: str
    timestamp: datetime
    traceback: str | None = None


class _FakePlatform:
    def __init__(self) -> None:
        self._meta = SimpleNamespace(
            id="demo-platform",
            name="mock",
            adapter_display_name="Demo Platform",
        )
        self.status = SimpleNamespace(value="error")
        self.errors = [
            _FakePlatformError(
                message="broken",
                timestamp=datetime(2026, 3, 16, tzinfo=timezone.utc),
                traceback="trace",
            )
        ]
        self.last_error = self.errors[-1]
        self._stats = {
            "id": "demo-platform",
            "type": "mock",
            "display_name": "Demo Platform",
            "status": "error",
            "started_at": None,
            "error_count": 1,
            "last_error": {
                "message": "broken",
                "timestamp": "2026-03-16T00:00:00+00:00",
                "traceback": "trace",
            },
            "unified_webhook": True,
            "meta": {"support_streaming_message": True},
        }

    def meta(self):
        return self._meta

    def unified_webhook(self) -> bool:
        return True

    def clear_errors(self) -> None:
        self.errors = []
        self.last_error = None
        self.status = SimpleNamespace(value="running")
        self._stats["status"] = "running"
        self._stats["error_count"] = 0
        self._stats["last_error"] = None

    def get_stats(self) -> dict[str, object]:
        return dict(self._stats)


class _FakePluginBridge:
    def __init__(self) -> None:
        self._plugin_ids = {
            "reserved-request": "reserved-plugin",
            "plain-request": "plain-plugin",
        }

    def resolve_request_session(self, _request_id: str):
        return None

    def resolve_request_plugin_id(self, request_id: str) -> str:
        return self._plugin_ids[request_id]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_p1_3_core_bridge_reserved_gate_and_stream_cleanup() -> None:
    provider_manager = _FakeProviderManager()
    platform = _FakePlatform()
    bridge = CoreCapabilityBridge(
        star_context=cast(
            Any,
            SimpleNamespace(
                provider_manager=provider_manager,
                platform_manager=SimpleNamespace(get_insts=lambda: [platform]),
                get_provider_by_id=lambda provider_id: provider_manager.inst_map.get(
                    provider_id
                ),
                get_all_stars=lambda: [
                    SimpleNamespace(name="reserved-plugin", reserved=True),
                    SimpleNamespace(name="plain-plugin", reserved=False),
                ],
            ),
        ),
        plugin_bridge=_FakePluginBridge(),
    )

    with pytest.raises(AstrBotError, match="reserved/system"):
        await bridge._provider_manager_get_insts("plain-request", {}, None)

    output = await bridge._provider_manager_get_insts("reserved-request", {}, None)
    assert [item["id"] for item in output["providers"]] == ["chat-main"]

    disabled = await bridge._provider_manager_get_by_id(
        "reserved-request",
        {"provider_id": "chat-disabled"},
        None,
    )
    assert disabled["provider"]["loaded"] is False
    assert disabled["provider"]["enabled"] is False

    stream_exec = await bridge._provider_manager_watch_changes(
        "reserved-request",
        {},
        SimpleNamespace(raise_if_cancelled=lambda: None),
    )

    async def _next_bridge_provider_change() -> Any:
        return await anext(stream_exec.iterator)

    waiter = asyncio.create_task(_next_bridge_provider_change())
    await asyncio.sleep(0)
    provider_manager.fire_change("chat-main", "chat_completion", "umo-1")
    event = await asyncio.wait_for(waiter, timeout=1)
    assert event == {
        "provider_id": "chat-main",
        "provider_type": "chat_completion",
        "umo": "umo-1",
    }
    await cast(Any, stream_exec.iterator).aclose()
    assert provider_manager._hooks == []

    platform_snapshot = await bridge._platform_manager_get_by_id(
        "reserved-request",
        {"platform_id": "demo-platform"},
        None,
    )
    assert platform_snapshot["platform"]["status"] == "error"
    assert platform_snapshot["platform"]["unified_webhook"] is True
    assert platform_snapshot["platform"]["last_error"]["message"] == "broken"

    await bridge._platform_manager_clear_errors(
        "reserved-request",
        {"platform_id": "demo-platform"},
        None,
    )
    stats = await bridge._platform_manager_get_stats(
        "reserved-request",
        {"platform_id": "demo-platform"},
        None,
    )
    assert stats["stats"]["status"] == "running"
    assert stats["stats"]["error_count"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_p1_3_core_bridge_merged_provider_config_reserved_gate() -> None:
    provider_manager = _FakeProviderManager()
    bridge = CoreCapabilityBridge(
        star_context=cast(
            Any,
            SimpleNamespace(
                provider_manager=provider_manager,
                platform_manager=SimpleNamespace(get_insts=lambda: []),
                get_provider_by_id=lambda provider_id: provider_manager.inst_map.get(
                    provider_id
                ),
                get_all_stars=lambda: [
                    SimpleNamespace(name="reserved-plugin", reserved=True),
                    SimpleNamespace(name="plain-plugin", reserved=False),
                ],
            ),
        ),
        plugin_bridge=_FakePluginBridge(),
    )

    with pytest.raises(AstrBotError, match="reserved/system"):
        await bridge._provider_manager_get_merged_provider_config(
            "plain-request",
            {"provider_id": "chat-main"},
            None,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_p1_3_core_bridge_merged_provider_config_returns_merged_shape() -> None:
    provider_manager = _FakeProviderManager()
    bridge = CoreCapabilityBridge(
        star_context=cast(
            Any,
            SimpleNamespace(
                provider_manager=provider_manager,
                platform_manager=SimpleNamespace(get_insts=lambda: []),
                get_provider_by_id=lambda provider_id: provider_manager.inst_map.get(
                    provider_id
                ),
                get_all_stars=lambda: [
                    SimpleNamespace(name="reserved-plugin", reserved=True),
                    SimpleNamespace(name="plain-plugin", reserved=False),
                ],
            ),
        ),
        plugin_bridge=_FakePluginBridge(),
    )

    output = await bridge._provider_manager_get_merged_provider_config(
        "reserved-request",
        {"provider_id": "chat-main"},
        None,
    )

    expected_config = provider_manager.get_merged_provider_config(
        provider_manager.providers_config[0]
    )

    assert output["config"]["id"] == "chat-main"
    assert output["config"]["endpoint"] == "https://example.invalid/v1"
    assert output["config"]["headers"] == {"x-source": "provider-source"}
    assert output["config"]["model_config"] == {"temperature": 0.6}
    assert output["config"]["provider_settings"] == {
        "headers": {"x-provider": "chat-main"},
        "options": {
            "temperature": 0.6,
            "penalties": {"frequency": 0.1},
        },
    }
    assert output["config"]["source_metadata"] == {
        "routing": {
            "primary": "edge-a",
            "fallbacks": ["edge-b", "edge-c"],
        }
    }
    assert set(output["config"].keys()) == set(expected_config.keys())
    assert output["config"] == expected_config


@pytest.mark.unit
@pytest.mark.asyncio
async def test_p1_3_core_bridge_merged_provider_config_unknown_provider_fails() -> None:
    provider_manager = _FakeProviderManager()
    bridge = CoreCapabilityBridge(
        star_context=cast(
            Any,
            SimpleNamespace(
                provider_manager=provider_manager,
                platform_manager=SimpleNamespace(get_insts=lambda: []),
                get_provider_by_id=lambda provider_id: provider_manager.inst_map.get(
                    provider_id
                ),
                get_all_stars=lambda: [
                    SimpleNamespace(name="reserved-plugin", reserved=True),
                    SimpleNamespace(name="plain-plugin", reserved=False),
                ],
            ),
        ),
        plugin_bridge=_FakePluginBridge(),
    )

    with pytest.raises(AstrBotError, match="unknown provider_id"):
        await bridge._provider_manager_get_merged_provider_config(
            "reserved-request",
            {"provider_id": "missing-provider"},
            None,
        )
