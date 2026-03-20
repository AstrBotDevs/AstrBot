from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_sdk.errors import AstrBotError, ErrorCodes
from astrbot_sdk.runtime.capability_router import CapabilityRouter
import astrbot_sdk.runtime.supervisor as supervisor_module
from astrbot_sdk.runtime.environment_groups import EnvironmentPlanResult
from astrbot_sdk.runtime.loader import PluginDiscoveryResult, PluginSpec
from astrbot_sdk.runtime.supervisor import SupervisorRuntime, WorkerSession
from astrbot_sdk.runtime.transport import Transport


class _DummyTransport(Transport):
    async def start(self) -> None:
        self._closed.clear()

    async def stop(self) -> None:
        self._closed.set()

    async def send(self, payload: str) -> None:
        return None


class _RecordingPeer:
    def __init__(self) -> None:
        self.initialize_calls: list[dict[str, object]] = []
        self.started = False
        self.stopped = False

    def set_invoke_handler(self, _handler) -> None:
        return None

    def set_cancel_handler(self, _handler) -> None:
        return None

    async def start(self) -> None:
        self.started = True

    async def initialize(
        self,
        handlers,
        *,
        provided_capabilities,
        metadata,
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


class _StaticEnvManager:
    def __init__(self, plugins: list[PluginSpec]) -> None:
        self._plugins = list(plugins)

    def plan(self, _plugins: list[PluginSpec]) -> EnvironmentPlanResult:
        return EnvironmentPlanResult(plugins=list(self._plugins))


def _write_plugin_spec(tmp_path: Path, plugin_name: str) -> PluginSpec:
    plugin_dir = tmp_path / plugin_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = plugin_dir / "plugin.yaml"
    manifest_path.write_text(
        f"""
_schema_version: 2
name: {plugin_name}
author: tests
version: 1.0.0
desc: supervisor registry sync tests

runtime:
  python: "3.12"

components:
  - class: main:TestPlugin
""".strip()
        + "\n",
        encoding="utf-8",
    )
    requirements_path = plugin_dir / "requirements.txt"
    requirements_path.write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(
        "from astrbot_sdk import Star\n\n\nclass TestPlugin(Star):\n    pass\n",
        encoding="utf-8",
    )
    return PluginSpec(
        name=plugin_name,
        plugin_dir=plugin_dir,
        manifest_path=manifest_path,
        requirements_path=requirements_path,
        python_version="3.12",
        manifest_data={
            "name": plugin_name,
            "author": "tests",
            "version": "1.0.0",
            "desc": "supervisor registry sync tests",
            "components": [{"class": "main:TestPlugin"}],
            "runtime": {"python": "3.12"},
        },
    )


@pytest.mark.asyncio
async def test_supervisor_publishes_plugin_registry_in_two_phases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alpha = _write_plugin_spec(tmp_path, "alpha")
    beta = _write_plugin_spec(tmp_path, "beta")
    plugins = [alpha, beta]
    runtime = SupervisorRuntime(
        transport=_DummyTransport(),
        plugins_dir=tmp_path,
        env_manager=_StaticEnvManager(plugins),
    )
    peer = _RecordingPeer()
    runtime.peer = peer  # type: ignore[assignment]

    monkeypatch.setattr(
        supervisor_module,
        "discover_plugins",
        lambda _plugins_dir: PluginDiscoveryResult(
            plugins=list(plugins),
            skipped_plugins={},
            issues=[],
        ),
    )

    phase_snapshots: list[tuple[str, dict[str, bool]]] = []

    class _FakeWorkerSession:
        def __init__(
            self,
            *,
            plugin=None,
            group=None,
            repo_root,
            env_manager,
            capability_router,
            on_closed=None,
        ) -> None:
            del group, repo_root, env_manager, capability_router, on_closed
            assert plugin is not None
            self.plugin = plugin
            self.plugins = [plugin]
            self.group_id = plugin.name
            self.handlers = []
            self.provided_capabilities = []
            self.loaded_plugins: list[str] = []
            self.skipped_plugins: dict[str, str] = {}
            self.issues = []
            self.capability_sources: dict[str, str] = {}

        async def start(self) -> None:
            phase_snapshots.append(
                (
                    self.plugin.name,
                    {
                        name: bool(entry.metadata.get("enabled", False))
                        for name, entry in runtime.capability_router._plugins.items()
                    },
                )
            )
            if self.plugin.name == "beta":
                raise RuntimeError("beta worker failed")
            self.loaded_plugins = [self.plugin.name]

        async def stop(self) -> None:
            return None

        def start_close_watch(self) -> None:
            return None

        def describe(self) -> dict[str, object]:
            return {
                "group_id": self.group_id,
                "plugins": [plugin.name for plugin in self.plugins],
                "loaded_plugins": list(self.loaded_plugins),
                "skipped_plugins": dict(self.skipped_plugins),
                "issues": list(self.issues),
            }

    monkeypatch.setattr(supervisor_module, "WorkerSession", _FakeWorkerSession)

    await runtime.start()

    assert phase_snapshots == [
        ("alpha", {"alpha": False, "beta": False}),
        ("beta", {"alpha": False, "beta": False}),
    ]
    assert runtime.loaded_plugins == ["alpha"]
    assert runtime.skipped_plugins["beta"] == "beta worker failed"
    assert runtime.capability_router._plugins["alpha"].metadata["enabled"] is True
    assert runtime.capability_router._plugins["beta"].metadata["enabled"] is False
    assert peer.started is True
    assert len(peer.initialize_calls) == 1
    assert peer.initialize_calls[0]["metadata"] == {
        "plugins": ["alpha"],
        "skipped_plugins": {"beta": "beta worker failed"},
        "issues": [
            {
                "severity": "error",
                "phase": "load",
                "plugin_id": "beta",
                "message": "插件 worker 启动失败",
                "details": "beta worker failed",
                "hint": "",
            }
        ],
        "aggregated_handler_ids": [],
        "worker_groups": [
            {
                "group_id": "alpha",
                "plugins": ["alpha"],
                "loaded_plugins": ["alpha"],
                "skipped_plugins": {},
                "issues": [],
            }
        ],
        "worker_group_count": 1,
    }


@pytest.mark.asyncio
async def test_worker_session_start_surfaces_init_waiter_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin = _write_plugin_spec(tmp_path, "alpha")
    session = WorkerSession(
        plugin=plugin,
        repo_root=tmp_path,
        env_manager=_StaticEnvManager([plugin]),
        capability_router=CapabilityRouter(),
    )
    session._worker_command = lambda: (
        Path("/usr/bin/python3"),
        ["/usr/bin/python3", "-m", "astrbot_sdk", "worker"],
        str(tmp_path),
    )

    class _StubStdioTransport:
        def __init__(self, *, command, cwd, env) -> None:
            self.command = command
            self.cwd = cwd
            self.env = env

    created_peers: list[object] = []

    class _FailingInitPeer:
        def __init__(self, *, transport, peer_info) -> None:
            del transport, peer_info
            self.remote_handlers = []
            self.remote_provided_capabilities = []
            self.remote_metadata = {}
            self.stopped = False
            created_peers.append(self)

        def set_initialize_handler(self, _handler) -> None:
            return None

        def set_invoke_handler(self, _handler) -> None:
            return None

        async def start(self) -> None:
            return None

        async def wait_until_remote_initialized(
            self, timeout: float | None = None
        ) -> None:
            del timeout
            raise AstrBotError.protocol_error("连接在初始化完成前关闭")

        async def wait_closed(self) -> None:
            return None

        async def stop(self) -> None:
            self.stopped = True

    monkeypatch.setattr(supervisor_module, "StdioTransport", _StubStdioTransport)
    monkeypatch.setattr(supervisor_module, "Peer", _FailingInitPeer)

    with pytest.raises(AstrBotError, match="连接在初始化完成前关闭") as exc_info:
        await session.start()

    assert exc_info.value.code == ErrorCodes.PROTOCOL_ERROR
    assert len(created_peers) == 1
    assert created_peers[0].stopped is True
