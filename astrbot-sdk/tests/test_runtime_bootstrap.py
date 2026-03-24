from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot_sdk.runtime import bootstrap as bootstrap_module


class _RecordingRuntime:
    def __init__(self, *, peer_name: str = "runtime-peer") -> None:
        self.peer = SimpleNamespace(name=peer_name)
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_run_plugin_worker_requires_exactly_one_target() -> None:
    with pytest.raises(ValueError, match="plugin_dir or group_metadata is required"):
        await bootstrap_module.run_plugin_worker(plugin_dir=None, group_metadata=None)

    with pytest.raises(ValueError, match="mutually exclusive"):
        await bootstrap_module.run_plugin_worker(
            plugin_dir=Path("plugin"),
            group_metadata=Path("group.json"),
        )


@pytest.mark.asyncio
async def test_run_plugin_worker_uses_single_plugin_runtime_and_restores_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_RecordingRuntime] = []
    original_stdout = sys.stdout

    def fake_prepare_stdio_transport(stdin, stdout):
        assert stdin == "stdin"
        assert stdout == "stdout"
        sys.stdout = sys.stderr
        return "transport-stdin", "transport-stdout", original_stdout

    class _FakeTransport:
        def __init__(self, *, stdin, stdout) -> None:
            self.stdin = stdin
            self.stdout = stdout

    def fake_runtime(*, plugin_dir: Path, transport) -> _RecordingRuntime:
        assert plugin_dir == Path("plugin-dir")
        assert transport.stdin == "transport-stdin"
        assert transport.stdout == "transport-stdout"
        runtime = _RecordingRuntime()
        created.append(runtime)
        return runtime

    async def fake_wait_for_shutdown(peer, stop_event) -> None:
        assert peer is created[0].peer
        assert isinstance(stop_event, bootstrap_module.asyncio.Event)

    monkeypatch.setattr(
        bootstrap_module,
        "_prepare_stdio_transport",
        fake_prepare_stdio_transport,
    )
    monkeypatch.setattr(bootstrap_module, "StdioTransport", _FakeTransport)
    monkeypatch.setattr(bootstrap_module, "PluginWorkerRuntime", fake_runtime)
    monkeypatch.setattr(
        bootstrap_module,
        "_install_signal_handlers",
        lambda stop_event: stop_event.set(),
    )
    monkeypatch.setattr(bootstrap_module, "_wait_for_shutdown", fake_wait_for_shutdown)

    await bootstrap_module.run_plugin_worker(
        plugin_dir=Path("plugin-dir"),
        stdin="stdin",
        stdout="stdout",
    )

    assert len(created) == 1
    assert created[0].started is True
    assert created[0].stopped is True
    assert sys.stdout is original_stdout


@pytest.mark.asyncio
async def test_run_plugin_worker_uses_group_runtime_when_group_metadata_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_RecordingRuntime] = []

    monkeypatch.setattr(
        bootstrap_module,
        "_prepare_stdio_transport",
        lambda stdin, stdout: ("stdin", "stdout", None),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "StdioTransport",
        lambda *, stdin, stdout: SimpleNamespace(stdin=stdin, stdout=stdout),
    )

    def fake_group_runtime(
        *, group_metadata_path: Path, transport
    ) -> _RecordingRuntime:
        assert group_metadata_path == Path("group.json")
        assert transport.stdin == "stdin"
        assert transport.stdout == "stdout"
        runtime = _RecordingRuntime(peer_name="group-peer")
        created.append(runtime)
        return runtime

    monkeypatch.setattr(bootstrap_module, "GroupWorkerRuntime", fake_group_runtime)
    monkeypatch.setattr(
        bootstrap_module,
        "_install_signal_handlers",
        lambda stop_event: stop_event.set(),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "_wait_for_shutdown",
        lambda peer, stop_event: (
            created[0].start() if False else bootstrap_module.asyncio.sleep(0)
        ),
    )

    await bootstrap_module.run_plugin_worker(group_metadata=Path("group.json"))

    assert len(created) == 1
    assert created[0].started is True
    assert created[0].stopped is True


@pytest.mark.asyncio
async def test_run_supervisor_passes_env_manager_and_restores_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_RecordingRuntime] = []
    env_manager = object()
    original_stdout = sys.stdout

    monkeypatch.setattr(
        bootstrap_module,
        "_prepare_stdio_transport",
        lambda stdin, stdout: ("stdin", "stdout", original_stdout),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "StdioTransport",
        lambda *, stdin, stdout: SimpleNamespace(stdin=stdin, stdout=stdout),
    )

    def fake_runtime(*, transport, plugins_dir: Path, env_manager) -> _RecordingRuntime:
        assert plugins_dir == Path("plugins-under-test")
        assert env_manager is not None
        assert transport.stdin == "stdin"
        assert transport.stdout == "stdout"
        runtime = _RecordingRuntime(peer_name="supervisor-peer")
        created.append(runtime)
        return runtime

    monkeypatch.setattr(bootstrap_module, "SupervisorRuntime", fake_runtime)
    monkeypatch.setattr(
        bootstrap_module,
        "_install_signal_handlers",
        lambda stop_event: stop_event.set(),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "_wait_for_shutdown",
        lambda peer, stop_event: bootstrap_module.asyncio.sleep(0),
    )

    await bootstrap_module.run_supervisor(
        plugins_dir=Path("plugins-under-test"),
        env_manager=env_manager,
    )

    assert len(created) == 1
    assert created[0].started is True
    assert created[0].stopped is True
    assert sys.stdout is original_stdout


@pytest.mark.asyncio
async def test_run_websocket_server_uses_websocket_transport_and_default_cwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_RecordingRuntime] = []
    websocket_transports: list[SimpleNamespace] = []

    monkeypatch.setattr(bootstrap_module.Path, "cwd", lambda: Path("cwd-plugin"))

    def fake_transport(*, host: str, port: int, path: str):
        transport = SimpleNamespace(host=host, port=port, path=path)
        websocket_transports.append(transport)
        return transport

    def fake_runtime(*, plugin_dir: Path, transport) -> _RecordingRuntime:
        assert plugin_dir == Path("cwd-plugin")
        assert transport is websocket_transports[0]
        runtime = _RecordingRuntime(peer_name="ws-peer")
        created.append(runtime)
        return runtime

    monkeypatch.setattr(bootstrap_module, "WebSocketServerTransport", fake_transport)
    monkeypatch.setattr(bootstrap_module, "PluginWorkerRuntime", fake_runtime)
    monkeypatch.setattr(
        bootstrap_module,
        "_install_signal_handlers",
        lambda stop_event: stop_event.set(),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "_wait_for_shutdown",
        lambda peer, stop_event: bootstrap_module.asyncio.sleep(0),
    )

    await bootstrap_module.run_websocket_server(
        host="0.0.0.0",
        port=9000,
        path="/ws",
        plugin_dir=None,
    )

    assert websocket_transports == [
        SimpleNamespace(host="0.0.0.0", port=9000, path="/ws")
    ]
    assert created[0].started is True
    assert created[0].stopped is True
