from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from astrbot_sdk._internal.testing_support import MockContext
from astrbot_sdk.clients._proxy import CapabilityProxy
from astrbot_sdk.clients.platform import PlatformStatus
from astrbot_sdk.clients.provider import ProviderManagerClient
from astrbot_sdk.context import PlatformCompatFacade
from astrbot_sdk.llm.entities import ProviderType


async def _wait_until(
    predicate,
    *,
    timeout: float = 0.2,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not satisfied before timeout")


class _HookLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[str, str]] = []
        self.exception_calls: list[tuple[str, str]] = []

    def debug(self, message: str, plugin_id: str) -> None:
        self.debug_calls.append((message, plugin_id))

    def exception(self, message: str, plugin_id: str) -> None:
        self.exception_calls.append((message, plugin_id))


@dataclass(slots=True)
class _CapabilityDescriptor:
    supports_stream: bool | None = False


class _ProviderMutationPeer:
    def __init__(self) -> None:
        self.remote_peer = object()
        self.remote_capability_map = {
            "provider.manager.create": _CapabilityDescriptor(),
            "provider.manager.load": _CapabilityDescriptor(),
            "provider.manager.update": _CapabilityDescriptor(),
            "provider.manager.get_merged_provider_config": _CapabilityDescriptor(),
        }
        self.stored_config = {"id": "provider-1", "model": "original-model"}

    async def invoke(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        stream: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        assert not stream
        if capability in {"provider.manager.create", "provider.manager.load"}:
            provider_config = payload["provider_config"]
            assert isinstance(provider_config, dict)
            provider_config["id"] = "mutated-by-peer"
            provider_config["model"] = "mutated-model"
            return {
                "provider": {
                    "id": "provider-1",
                    "model": "created-model",
                    "type": "mock",
                    "provider_type": "chat_completion",
                    "loaded": True,
                    "enabled": True,
                    "provider_source_id": None,
                }
            }
        if capability == "provider.manager.update":
            new_config = payload["new_config"]
            assert isinstance(new_config, dict)
            new_config["id"] = "mutated-by-peer"
            new_config["model"] = "mutated-model"
            return {
                "provider": {
                    "id": "provider-1",
                    "model": "updated-model",
                    "type": "mock",
                    "provider_type": "chat_completion",
                    "loaded": True,
                    "enabled": True,
                    "provider_source_id": None,
                }
            }
        if capability == "provider.manager.get_merged_provider_config":
            return {"config": self.stored_config}
        raise AssertionError(f"unexpected capability: {capability}")

    async def invoke_stream(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
        include_completed: bool = False,
    ):
        raise AssertionError(f"unexpected stream capability: {capability}")


class _ControlledPlatformProxy:
    def __init__(
        self,
        *,
        snapshots: list[dict[str, Any]],
        cleared_snapshot: dict[str, Any] | None = None,
    ) -> None:
        self._snapshots = [dict(item) for item in snapshots]
        self._cleared_snapshot = (
            dict(cleared_snapshot) if isinstance(cleared_snapshot, dict) else None
        )
        self.call_order: list[str] = []
        self.get_by_id_calls = 0
        self.clear_errors_calls = 0
        self.first_get_started = asyncio.Event()
        self.release_first_get = asyncio.Event()
        self._cleared = False

    async def call(self, capability: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.call_order.append(capability)
        if capability == "platform.manager.get_by_id":
            call_index = self.get_by_id_calls
            self.get_by_id_calls += 1
            if call_index == 0:
                self.first_get_started.set()
                await self.release_first_get.wait()
            if self._cleared and self._cleared_snapshot is not None:
                snapshot = self._cleared_snapshot
            else:
                snapshot = self._snapshots[min(call_index, len(self._snapshots) - 1)]
            return {"platform": dict(snapshot)}
        if capability == "platform.manager.clear_errors":
            self.clear_errors_calls += 1
            self._cleared = True
            return {}
        raise AssertionError(f"unexpected capability: {capability}")


@pytest.mark.asyncio
async def test_provider_change_hook_receives_events_and_unregisters_cleanly() -> None:
    ctx = MockContext(plugin_metadata={"reserved": True})
    received: list[tuple[str, ProviderType, str | None]] = []
    event_received = asyncio.Event()

    async def callback(
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None,
    ) -> None:
        received.append((provider_id, provider_type, umo))
        event_received.set()

    task = await ctx.provider_manager.register_provider_change_hook(callback)
    await _wait_until(lambda: len(ctx.router._provider_change_subscriptions) == 1)

    ctx.router.emit_provider_change(
        "mock-embedding-provider",
        ProviderType.EMBEDDING.value,
        "mock:session:user",
    )
    await asyncio.wait_for(event_received.wait(), timeout=0.2)

    assert received == [
        (
            "mock-embedding-provider",
            ProviderType.EMBEDDING,
            "mock:session:user",
        )
    ]

    await ctx.provider_manager.unregister_provider_change_hook(task)
    await _wait_until(lambda: not ctx.router._provider_change_subscriptions)
    assert task.cancelled()
    assert not ctx.provider_manager._change_hook_tasks

    ctx.router.emit_provider_change(
        "mock-rerank-provider",
        ProviderType.RERANK.value,
        None,
    )
    await asyncio.sleep(0)
    assert received == [
        (
            "mock-embedding-provider",
            ProviderType.EMBEDDING,
            "mock:session:user",
        )
    ]


@pytest.mark.asyncio
async def test_provider_change_hook_task_cancellation_cleans_up_and_logs_once() -> None:
    logger = _HookLogger()
    ctx = MockContext(plugin_metadata={"reserved": True}, logger=logger)

    task = await ctx.provider_manager.register_provider_change_hook(lambda *_args: None)
    await _wait_until(lambda: len(ctx.router._provider_change_subscriptions) == 1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await _wait_until(lambda: not ctx.router._provider_change_subscriptions)
    assert not ctx.provider_manager._change_hook_tasks
    assert logger.debug_calls == [
        ("Provider change hook cancelled: plugin_id={}", "test-plugin")
    ]
    assert logger.exception_calls == []


@pytest.mark.asyncio
async def test_platform_compat_refresh_serializes_concurrent_state_updates() -> None:
    proxy = _ControlledPlatformProxy(
        snapshots=[
            {
                "id": "mock-platform",
                "name": "First Snapshot",
                "type": "mock",
                "status": "error",
                "errors": [
                    {
                        "message": "first error",
                        "timestamp": "2026-03-20T00:00:00+00:00",
                        "traceback": None,
                    }
                ],
                "last_error": {
                    "message": "first error",
                    "timestamp": "2026-03-20T00:00:00+00:00",
                    "traceback": None,
                },
                "unified_webhook": False,
            },
            {
                "id": "mock-platform",
                "name": "Second Snapshot",
                "type": "mock-updated",
                "status": "running",
                "errors": [],
                "last_error": None,
                "unified_webhook": True,
            },
        ]
    )
    facade = PlatformCompatFacade(
        _ctx=SimpleNamespace(_proxy=proxy),
        id="mock-platform",
        name="Initial Snapshot",
        type="mock",
    )

    first = asyncio.create_task(facade.refresh())
    await asyncio.wait_for(proxy.first_get_started.wait(), timeout=0.2)

    second = asyncio.create_task(facade.refresh())
    await asyncio.sleep(0)
    assert proxy.get_by_id_calls == 1

    proxy.release_first_get.set()
    await asyncio.gather(first, second)

    assert proxy.call_order == [
        "platform.manager.get_by_id",
        "platform.manager.get_by_id",
    ]
    assert facade.name == "Second Snapshot"
    assert facade.type == "mock-updated"
    assert facade.status == PlatformStatus.RUNNING
    assert facade.errors == []
    assert facade.last_error is None
    assert facade.unified_webhook is True


@pytest.mark.asyncio
async def test_platform_compat_clear_errors_waits_for_inflight_refresh() -> None:
    proxy = _ControlledPlatformProxy(
        snapshots=[
            {
                "id": "mock-platform",
                "name": "Errored Platform",
                "type": "mock",
                "status": "error",
                "errors": [
                    {
                        "message": "boom",
                        "timestamp": "2026-03-20T00:00:00+00:00",
                        "traceback": "trace",
                    }
                ],
                "last_error": {
                    "message": "boom",
                    "timestamp": "2026-03-20T00:00:00+00:00",
                    "traceback": "trace",
                },
                "unified_webhook": False,
            }
        ],
        cleared_snapshot={
            "id": "mock-platform",
            "name": "Recovered Platform",
            "type": "mock",
            "status": "running",
            "errors": [],
            "last_error": None,
            "unified_webhook": False,
        },
    )
    facade = PlatformCompatFacade(
        _ctx=SimpleNamespace(_proxy=proxy),
        id="mock-platform",
        name="Initial Snapshot",
        type="mock",
    )

    refresh_task = asyncio.create_task(facade.refresh())
    await asyncio.wait_for(proxy.first_get_started.wait(), timeout=0.2)

    clear_task = asyncio.create_task(facade.clear_errors())
    await asyncio.sleep(0)
    assert proxy.clear_errors_calls == 0

    proxy.release_first_get.set()
    await asyncio.gather(refresh_task, clear_task)

    assert proxy.call_order == [
        "platform.manager.get_by_id",
        "platform.manager.clear_errors",
        "platform.manager.get_by_id",
    ]
    assert facade.name == "Recovered Platform"
    assert facade.status == PlatformStatus.RUNNING
    assert facade.errors == []
    assert facade.last_error is None


@pytest.mark.asyncio
async def test_provider_manager_methods_copy_caller_supplied_config_dicts() -> None:
    peer = _ProviderMutationPeer()
    manager = ProviderManagerClient(
        CapabilityProxy(peer),
        plugin_id="test-plugin",
        logger=None,
    )

    create_config = {
        "id": "provider-create",
        "model": "create-model",
        "type": "mock",
        "provider_type": ProviderType.CHAT_COMPLETION.value,
    }
    load_config = {
        "id": "provider-load",
        "model": "load-model",
        "type": "mock",
        "provider_type": ProviderType.CHAT_COMPLETION.value,
    }
    update_config = {
        "id": "provider-update",
        "model": "update-model",
        "type": "mock",
        "provider_type": ProviderType.CHAT_COMPLETION.value,
    }

    create_snapshot = deepcopy(create_config)
    load_snapshot = deepcopy(load_config)
    update_snapshot = deepcopy(update_config)

    await manager.create_provider(create_config)
    await manager.load_provider(load_config)
    await manager.update_provider("provider-origin", update_config)

    assert create_config == create_snapshot
    assert load_config == load_snapshot
    assert update_config == update_snapshot


@pytest.mark.asyncio
async def test_provider_manager_get_merged_provider_config_returns_detached_dict() -> (
    None
):
    peer = _ProviderMutationPeer()
    manager = ProviderManagerClient(
        CapabilityProxy(peer),
        plugin_id="test-plugin",
        logger=None,
    )

    config = await manager.get_merged_provider_config("provider-1")
    assert config == {"id": "provider-1", "model": "original-model"}

    assert config is not peer.stored_config
    config["model"] = "changed-by-caller"
    assert peer.stored_config == {"id": "provider-1", "model": "original-model"}
