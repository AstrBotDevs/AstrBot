from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.errors import AstrBotError, ErrorCodes
from astrbot_sdk.llm.agents import AgentSpec
from astrbot_sdk.llm.entities import LLMToolSpec
from astrbot_sdk.protocol.descriptors import CapabilityDescriptor
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.runtime.loader import (
    LoadedAgent,
    LoadedCapability,
    LoadedPlugin,
    PluginDiscoveryIssue,
    PluginSpec,
)
from astrbot_sdk.runtime.worker import (
    GLOBAL_MCP_RISK_ATTR,
    GroupPluginRuntimeState,
    GroupWorkerRuntime,
    PluginWorkerRuntime,
)


def _plugin_spec(name: str) -> PluginSpec:
    plugin_dir = Path(f"/tmp/{name}")
    return PluginSpec(
        name=name,
        plugin_dir=plugin_dir,
        manifest_path=plugin_dir / "plugin.yaml",
        requirements_path=plugin_dir / "requirements.txt",
        python_version="3.12",
        manifest_data={"name": name},
    )


@pytest.mark.asyncio
async def test_plugin_worker_handle_invoke_maps_lookup_error_to_astrbot_error() -> None:
    runtime = object.__new__(PluginWorkerRuntime)
    runtime.dispatcher = SimpleNamespace(invoke=AsyncMock())
    runtime.capability_dispatcher = SimpleNamespace(
        invoke=AsyncMock(side_effect=LookupError("missing")),
    )

    with pytest.raises(AstrBotError) as exc_info:
        await PluginWorkerRuntime._handle_invoke(
            runtime,
            InvokeMessage(id="req-cap", capability="missing.capability", input={}),
            CancelToken(),
        )

    assert exc_info.value.code == ErrorCodes.CAPABILITY_NOT_FOUND
    assert "missing.capability" in exc_info.value.message


@pytest.mark.asyncio
async def test_plugin_worker_handle_cancel_fans_out_to_both_dispatchers() -> None:
    runtime = object.__new__(PluginWorkerRuntime)
    runtime.dispatcher = SimpleNamespace(cancel=AsyncMock())
    runtime.capability_dispatcher = SimpleNamespace(cancel=AsyncMock())

    await PluginWorkerRuntime._handle_cancel(runtime, "req-123")

    runtime.dispatcher.cancel.assert_awaited_once_with("req-123")
    runtime.capability_dispatcher.cancel.assert_awaited_once_with("req-123")


@pytest.mark.asyncio
async def test_plugin_worker_start_initializes_metadata_and_handlers() -> None:
    runtime = object.__new__(PluginWorkerRuntime)
    runtime.plugin = _plugin_spec("alpha")
    runtime.loaded_plugin = LoadedPlugin(
        plugin=runtime.plugin,
        handlers=[],
        capabilities=[],
        llm_tools=[],
        agents=[],
        instances=[],
    )
    runtime.issues = []
    lifecycle_calls: list[str] = []

    class _Peer:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False
            self.initialize_calls: list[dict[str, object]] = []

        async def start(self) -> None:
            self.started = True

        async def initialize(
            self, handlers, *, provided_capabilities, metadata
        ) -> None:
            self.initialize_calls.append(
                {
                    "handlers": list(handlers),
                    "provided_capabilities": list(provided_capabilities),
                    "metadata": dict(metadata),
                }
            )

        async def stop(self) -> None:
            self.stopped = True

    runtime.peer = _Peer()

    async def fake_run_lifecycle(method_name: str) -> None:
        lifecycle_calls.append(method_name)

    runtime._run_lifecycle = fake_run_lifecycle  # type: ignore[method-assign]

    await PluginWorkerRuntime.start(runtime)

    assert runtime.peer.started is True
    assert lifecycle_calls == ["on_start"]
    assert runtime.peer.initialize_calls[0]["metadata"]["plugin_id"] == "alpha"
    assert runtime.peer.initialize_calls[0]["metadata"]["loaded_plugins"] == ["alpha"]


@pytest.mark.asyncio
async def test_plugin_worker_start_runs_on_stop_when_initialize_fails() -> None:
    runtime = object.__new__(PluginWorkerRuntime)
    runtime.plugin = _plugin_spec("alpha")
    runtime.loaded_plugin = LoadedPlugin(
        plugin=runtime.plugin,
        handlers=[],
        capabilities=[],
        llm_tools=[],
        agents=[],
        instances=[],
    )
    runtime.issues = []
    lifecycle_calls: list[str] = []

    class _Peer:
        def __init__(self) -> None:
            self.stopped = False

        async def start(self) -> None:
            return None

        async def initialize(
            self, handlers, *, provided_capabilities, metadata
        ) -> None:
            del handlers, provided_capabilities, metadata
            raise RuntimeError("initialize failed")

        async def stop(self) -> None:
            self.stopped = True

    runtime.peer = _Peer()

    async def fake_run_lifecycle(method_name: str) -> None:
        lifecycle_calls.append(method_name)

    runtime._run_lifecycle = fake_run_lifecycle  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="initialize failed"):
        await PluginWorkerRuntime.start(runtime)

    assert lifecycle_calls == ["on_start", "on_stop"]
    assert runtime.peer.stopped is True


@pytest.mark.asyncio
async def test_group_worker_start_raises_when_all_plugins_become_inactive() -> None:
    runtime = object.__new__(GroupWorkerRuntime)
    alpha = _plugin_spec("alpha")
    runtime.group_id = "worker-group"
    runtime._plugin_states = [
        GroupPluginRuntimeState(
            plugin=alpha,
            loaded_plugin=LoadedPlugin(plugin=alpha, handlers=[], instances=[]),
            lifecycle_context=Context(peer=SimpleNamespace(), plugin_id="alpha"),
        )
    ]
    runtime._active_plugin_states = list(runtime._plugin_states)
    runtime.skipped_plugins = {}
    runtime.issues = []
    refresh_snapshots: list[list[str]] = []

    class _Peer:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        async def start(self) -> None:
            self.started = True

        async def initialize(
            self, handlers, *, provided_capabilities, metadata
        ) -> None:
            del handlers, provided_capabilities, metadata
            raise AssertionError("initialize should not run without active plugins")

        async def stop(self) -> None:
            self.stopped = True

    runtime.peer = _Peer()

    def fake_refresh_dispatchers() -> None:
        refresh_snapshots.append(
            [state.plugin.name for state in runtime._active_plugin_states]
        )

    async def fake_run_lifecycle(state, method_name: str) -> None:
        del state, method_name
        raise RuntimeError("on_start failed")

    runtime._refresh_dispatchers = fake_refresh_dispatchers  # type: ignore[method-assign]
    runtime._run_lifecycle = fake_run_lifecycle  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="has no active plugins"):
        await GroupWorkerRuntime.start(runtime)

    assert runtime.peer.started is True
    assert runtime.peer.stopped is True
    assert runtime.skipped_plugins == {"alpha": "on_start failed"}
    assert runtime.issues[0].phase == "lifecycle"
    assert refresh_snapshots[-1] == []


def test_group_worker_initialize_metadata_aggregates_runtime_state() -> None:
    class _RiskyPlugin:
        pass

    setattr(_RiskyPlugin, GLOBAL_MCP_RISK_ATTR, True)

    alpha = _plugin_spec("alpha")
    beta = _plugin_spec("beta")
    alpha_capability = LoadedCapability(
        descriptor=CapabilityDescriptor(
            name="alpha.echo",
            description="echo",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        ),
        callable=lambda: None,
        owner=object(),
        plugin_id="alpha",
    )
    alpha_tool = LoadedAgent(
        spec=AgentSpec(
            name="alpha-agent",
            description="agent",
            runner_class="alpha.runner:Runner",
        ),
        runner_class=type("Runner", (), {}),
        plugin_id="alpha",
    )
    alpha_llm_tool = LoadedPlugin(
        plugin=alpha,
        handlers=[],
        capabilities=[alpha_capability],
        llm_tools=[
            SimpleNamespace(
                spec=LLMToolSpec.create(name="alpha-tool", description="tool")
            )
        ],
        agents=[alpha_tool],
        instances=[_RiskyPlugin()],
    )
    beta_plugin = LoadedPlugin(
        plugin=beta,
        handlers=[],
        capabilities=[],
        llm_tools=[],
        agents=[],
        instances=[object()],
    )
    runtime = object.__new__(GroupWorkerRuntime)
    runtime.group_id = "worker-group"
    runtime.plugins = [alpha, beta]
    runtime.skipped_plugins = {"beta": "start failed"}
    runtime.issues = [
        PluginDiscoveryIssue(
            severity="error",
            phase="load",
            plugin_id="beta",
            message="插件加载失败",
            details="start failed",
        )
    ]
    runtime._active_plugin_states = [
        GroupPluginRuntimeState(
            plugin=alpha,
            loaded_plugin=alpha_llm_tool,
            lifecycle_context=Context(peer=SimpleNamespace(), plugin_id="alpha"),
        ),
        GroupPluginRuntimeState(
            plugin=beta,
            loaded_plugin=beta_plugin,
            lifecycle_context=Context(peer=SimpleNamespace(), plugin_id="beta"),
        ),
    ]

    metadata = GroupWorkerRuntime._initialize_metadata(runtime)

    assert metadata["group_id"] == "worker-group"
    assert metadata["plugins"] == ["alpha", "beta"]
    assert metadata["loaded_plugins"] == ["alpha", "beta"]
    assert metadata["skipped_plugins"] == {"beta": "start failed"}
    assert metadata["capability_sources"] == {"alpha.echo": "alpha"}
    assert metadata["llm_tools"] == [
        {
            "name": "alpha-tool",
            "description": "tool",
            "parameters_schema": {"type": "object", "properties": {}},
            "active": True,
            "plugin_id": "alpha",
        }
    ]
    assert metadata["agents"] == [
        {
            "name": "alpha-agent",
            "description": "agent",
            "tool_names": [],
            "runner_class": "alpha.runner:Runner",
            "plugin_id": "alpha",
        }
    ]
    assert metadata["acknowledge_global_mcp_risk"] is True
