"""
Tests for runtime/bootstrap.py - Bootstrap and runtime classes.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from astrbot_sdk.context import CancelToken
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    HandlerDescriptor,
)
from astrbot_sdk.protocol.messages import (
    InitializeMessage,
    InitializeOutput,
    InvokeMessage,
    PeerInfo,
)
from astrbot_sdk.runtime.bootstrap import (
    PluginWorkerRuntime,
    SupervisorRuntime,
    WorkerSession,
    _install_signal_handlers,
    _prepare_stdio_transport,
    _wait_for_shutdown,
)
from astrbot_sdk.runtime.capability_router import CapabilityRouter
from astrbot_sdk.runtime.loader import PluginSpec
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import FakeEnvManager, MemoryTransport, make_transport_pair


async def start_test_core_peer(transport: MemoryTransport) -> Peer:
    """Provide an initialize responder so transport-pair startup tests do not deadlock."""
    core = Peer(
        transport=transport,
        peer_info=PeerInfo(name="test-core", role="core", version="v4"),
    )
    core.set_initialize_handler(
        lambda _message: asyncio.sleep(
            0,
            result=InitializeOutput(
                peer=PeerInfo(name="test-core", role="core", version="v4"),
                capabilities=[],
                metadata={},
            ),
        )
    )
    await core.start()
    return core


class TestInstallSignalHandlers:
    """Tests for _install_signal_handlers function."""

    @pytest.mark.asyncio
    async def test_installs_handlers(self):
        """_install_signal_handlers should install signal handlers."""
        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)
        # Just verify it doesn't raise on platforms that support it

    @pytest.mark.asyncio
    async def test_handles_not_implemented(self):
        """_install_signal_handlers should handle NotImplementedError."""
        stop_event = asyncio.Event()
        with patch.object(
            asyncio.get_running_loop(),
            "add_signal_handler",
            side_effect=NotImplementedError,
        ):
            _install_signal_handlers(stop_event)


class TestPrepareStdioTransport:
    """Tests for _prepare_stdio_transport function."""

    def test_with_both_streams(self):
        """_prepare_stdio_transport should use provided streams."""
        stdin = StringIO()
        stdout = StringIO()

        in_stream, out_stream, original = _prepare_stdio_transport(stdin, stdout)

        assert in_stream is stdin
        assert out_stream is stdout
        assert original is None

    def test_without_streams(self):
        """_prepare_stdio_transport should use sys.stdin/stdout."""
        # 保存原始值
        original_stdin = sys.stdin
        original_stdout = sys.stdout

        try:
            in_stream, out_stream, original = _prepare_stdio_transport(None, None)

            # in_stream 应该是原始的 sys.stdin
            assert in_stream is original_stdin
            # out_stream 应该是原始的 sys.stdout（在修改前）
            assert out_stream is original_stdout
            # original 也应该是原始的 sys.stdout
            assert original is original_stdout
            # 函数会修改 sys.stdout 为 sys.stderr
            assert sys.stdout is sys.stderr
        finally:
            # 恢复
            sys.stdout = original_stdout

    def test_redirects_stdout(self):
        """_prepare_stdio_transport should redirect sys.stdout to stderr."""
        original_stdout = sys.stdout

        _prepare_stdio_transport(None, None)

        assert sys.stdout is sys.stderr

        # Restore
        sys.stdout = original_stdout


class TestWaitForShutdown:
    """Tests for _wait_for_shutdown function."""

    @pytest.mark.asyncio
    async def test_waits_for_stop_event(self):
        """_wait_for_shutdown should wait for stop_event."""
        peer = MagicMock()

        # wait_closed 应该返回一个永不完成的协程
        async def never_complete():
            await asyncio.sleep(3600)

        peer.wait_closed = MagicMock(return_value=never_complete())

        stop_event = asyncio.Event()

        async def set_event():
            await asyncio.sleep(0.05)
            stop_event.set()

        asyncio.create_task(set_event())

        await _wait_for_shutdown(peer, stop_event)

        assert stop_event.is_set()

    @pytest.mark.asyncio
    async def test_waits_for_peer_closed(self):
        """_wait_for_shutdown should wait for peer.wait_closed()."""
        peer = MagicMock()

        # wait_closed 应该返回一个会完成的协程
        async def complete_soon():
            await asyncio.sleep(0.05)

        peer.wait_closed = MagicMock(return_value=complete_soon())

        stop_event = asyncio.Event()

        await _wait_for_shutdown(peer, stop_event)

        peer.wait_closed.assert_called_once()


class TestWorkerSessionInit:
    """Tests for WorkerSession initialization."""

    def test_init(self):
        """WorkerSession should store all parameters."""
        plugin = PluginSpec(
            name="test",
            plugin_dir=Path("/tmp"),
            manifest_path=Path("/tmp/plugin.yaml"),
            requirements_path=Path("/tmp/requirements.txt"),
            python_version="3.12",
            manifest_data={},
        )
        router = CapabilityRouter()
        env_manager = FakeEnvManager()

        session = WorkerSession(
            plugin=plugin,
            repo_root=Path("/repo"),
            env_manager=env_manager,
            capability_router=router,
        )

        assert session.plugin == plugin
        assert session.capability_router == router
        assert session.peer is None
        assert session.handlers == []


class TestWorkerSessionMethods:
    """Tests for WorkerSession methods."""

    @pytest.mark.asyncio
    async def test_invoke_handler_without_peer_raises(self):
        """invoke_handler should raise if peer is None."""
        plugin = PluginSpec(
            name="test",
            plugin_dir=Path("/tmp"),
            manifest_path=Path("/tmp/plugin.yaml"),
            requirements_path=Path("/tmp/requirements.txt"),
            python_version="3.12",
            manifest_data={},
        )
        session = WorkerSession(
            plugin=plugin,
            repo_root=Path("/tmp"),
            env_manager=FakeEnvManager(),
            capability_router=CapabilityRouter(),
        )

        with pytest.raises(RuntimeError, match="not running"):
            await session.invoke_handler("handler.id", {}, request_id="req-1")

    @pytest.mark.asyncio
    async def test_cancel_without_peer_does_nothing(self):
        """cancel should do nothing if peer is None."""
        plugin = PluginSpec(
            name="test",
            plugin_dir=Path("/tmp"),
            manifest_path=Path("/tmp/plugin.yaml"),
            requirements_path=Path("/tmp/requirements.txt"),
            python_version="3.12",
            manifest_data={},
        )
        session = WorkerSession(
            plugin=plugin,
            repo_root=Path("/tmp"),
            env_manager=FakeEnvManager(),
            capability_router=CapabilityRouter(),
        )

        # Should not raise
        await session.cancel("req-1")

    @pytest.mark.asyncio
    async def test_handle_initialize(self):
        """_handle_initialize should return InitializeOutput."""
        plugin = PluginSpec(
            name="test_plugin",
            plugin_dir=Path("/tmp"),
            manifest_path=Path("/tmp/plugin.yaml"),
            requirements_path=Path("/tmp/requirements.txt"),
            python_version="3.12",
            manifest_data={},
        )
        router = CapabilityRouter()
        session = WorkerSession(
            plugin=plugin,
            repo_root=Path("/tmp"),
            env_manager=FakeEnvManager(),
            capability_router=router,
        )

        message = InitializeMessage(
            id="init-1",
            protocol_version="1.0",
            peer=PeerInfo(name="test", role="plugin"),
        )

        output = await session._handle_initialize(message)

        assert output.peer.name == "astrbot-supervisor"
        assert output.peer.role == "core"
        assert len(output.capabilities) > 0

    @pytest.mark.asyncio
    async def test_handle_capability_invoke(self):
        """_handle_capability_invoke should route to capability_router."""
        plugin = PluginSpec(
            name="test",
            plugin_dir=Path("/tmp"),
            manifest_path=Path("/tmp/plugin.yaml"),
            requirements_path=Path("/tmp/requirements.txt"),
            python_version="3.12",
            manifest_data={},
        )
        router = CapabilityRouter()
        session = WorkerSession(
            plugin=plugin,
            repo_root=Path("/tmp"),
            env_manager=FakeEnvManager(),
            capability_router=router,
        )

        message = InvokeMessage(
            id="invoke-1",
            capability="llm.chat",
            input={"prompt": "hello"},
        )
        token = CancelToken()

        result = await session._handle_capability_invoke(message, token)

        assert result["text"] == "Echo: hello"


class TestSupervisorRuntimeInit:
    """Tests for SupervisorRuntime initialization."""

    def test_init(self):
        """SupervisorRuntime should initialize correctly."""
        transport = MemoryTransport()

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SupervisorRuntime(
                transport=transport,
                plugins_dir=Path(temp_dir),
            )

            assert runtime.transport is transport
            assert runtime.worker_sessions == {}
            assert runtime.handler_to_worker == {}
            assert runtime.active_requests == {}
            assert runtime.loaded_plugins == []
            assert isinstance(runtime.capability_router, CapabilityRouter)

    def test_registers_internal_capabilities(self):
        """SupervisorRuntime should register internal capabilities."""
        transport = MemoryTransport()

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SupervisorRuntime(
                transport=transport,
                plugins_dir=Path(temp_dir),
            )

            # handler.invoke should be registered (but not exposed)
            assert "handler.invoke" in runtime.capability_router._registrations
            # Should not be in descriptors (exposed=False)
            names = [d.name for d in runtime.capability_router.descriptors()]
            assert "handler.invoke" not in names


class TestSupervisorRuntimeMethods:
    """Tests for SupervisorRuntime methods."""

    @pytest.mark.asyncio
    async def test_start_with_empty_plugins_dir(self):
        """SupervisorRuntime.start should work with empty plugins dir."""
        left, right = make_transport_pair()
        core = await start_test_core_peer(left)

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SupervisorRuntime(
                transport=right,
                plugins_dir=Path(temp_dir),
                env_manager=FakeEnvManager(),
            )

            try:
                await runtime.start()
                await core.wait_until_remote_initialized()
                assert runtime.loaded_plugins == []
                assert runtime.skipped_plugins == {}
            finally:
                await runtime.stop()
                await core.stop()

    @pytest.mark.asyncio
    async def test_route_handler_invoke_missing_handler(self):
        """_route_handler_invoke should raise for missing handler."""
        transport = MemoryTransport()

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SupervisorRuntime(
                transport=transport,
                plugins_dir=Path(temp_dir),
            )

            with pytest.raises(AstrBotError, match="handler not found"):
                await runtime._route_handler_invoke(
                    "req-1",
                    {"handler_id": "missing.handler", "event": {}},
                    CancelToken(),
                )

    @pytest.mark.asyncio
    async def test_handle_worker_closed_removes_session(self):
        """_handle_worker_closed should remove session and handlers."""
        left, right = make_transport_pair()

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SupervisorRuntime(
                transport=right,
                plugins_dir=Path(temp_dir),
                env_manager=FakeEnvManager(),
            )

            # Add fake session
            mock_session = MagicMock()
            mock_session.handlers = [
                HandlerDescriptor(
                    id="test.handler", trigger=CommandTrigger(command="test")
                )
            ]

            runtime.worker_sessions["test_plugin"] = mock_session
            runtime.handler_to_worker["test.handler"] = mock_session
            runtime._handler_sources["test.handler"] = "test_plugin"
            runtime.loaded_plugins.append("test_plugin")

            runtime._handle_worker_closed("test_plugin")

            assert "test_plugin" not in runtime.worker_sessions
            assert "test.handler" not in runtime.handler_to_worker
            assert "test.handler" not in runtime._handler_sources
            assert "test_plugin" not in runtime.loaded_plugins

    @pytest.mark.asyncio
    async def test_handle_worker_closed_removes_active_requests(self):
        """_handle_worker_closed should drop in-flight requests owned by the worker."""
        transport = MemoryTransport()

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SupervisorRuntime(
                transport=transport,
                plugins_dir=Path(temp_dir),
            )

            mock_session = MagicMock()
            mock_session.handlers = [
                HandlerDescriptor(
                    id="test.handler", trigger=CommandTrigger(command="test")
                )
            ]

            runtime.worker_sessions["test_plugin"] = mock_session
            runtime.handler_to_worker["test.handler"] = mock_session
            runtime._handler_sources["test.handler"] = "test_plugin"
            runtime.loaded_plugins.append("test_plugin")
            runtime.active_requests["req-1"] = mock_session

            runtime._handle_worker_closed("test_plugin")

            assert "req-1" not in runtime.active_requests

    @pytest.mark.asyncio
    async def test_handle_worker_closed_unknown_plugin(self):
        """_handle_worker_closed should handle unknown plugin."""
        transport = MemoryTransport()

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SupervisorRuntime(
                transport=transport,
                plugins_dir=Path(temp_dir),
            )

            # Should not raise for unknown plugin
            runtime._handle_worker_closed("unknown_plugin")


class TestPluginWorkerRuntimeInit:
    """Tests for PluginWorkerRuntime initialization."""

    def test_init_with_valid_plugin(self):
        """PluginWorkerRuntime should initialize with valid plugin."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            transport = MemoryTransport()

            # This should work if the plugin is valid
            runtime = PluginWorkerRuntime(plugin_dir=plugin_dir, transport=transport)

            assert runtime.plugin.name == "test_plugin"
            assert runtime.peer is not None
            assert runtime.dispatcher is not None


class TestPluginWorkerRuntimeMethods:
    """Tests for PluginWorkerRuntime methods."""

    @pytest.mark.asyncio
    async def test_handle_invoke_wrong_capability(self):
        """_handle_invoke should raise for wrong capability."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            transport = MemoryTransport()
            runtime = PluginWorkerRuntime(plugin_dir=plugin_dir, transport=transport)

            message = InvokeMessage(
                id="invoke-1",
                capability="wrong.capability",
                input={},
            )
            token = CancelToken()

            with pytest.raises(AstrBotError, match="未找到能力"):
                await runtime._handle_invoke(message, token)

    @pytest.mark.asyncio
    async def test_run_lifecycle_sync_hook(self):
        """_run_lifecycle should call sync hooks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            transport = MemoryTransport()
            runtime = PluginWorkerRuntime(plugin_dir=plugin_dir, transport=transport)

            # Add mock instance with sync hook
            called = []

            class MockInstance:
                def on_start(self, ctx):
                    called.append("on_start")

            runtime.loaded_plugin.instances.append(MockInstance())

            await runtime._run_lifecycle("on_start")

            assert "on_start" in called

    @pytest.mark.asyncio
    async def test_run_lifecycle_async_hook(self):
        """_run_lifecycle should call async hooks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            transport = MemoryTransport()
            runtime = PluginWorkerRuntime(plugin_dir=plugin_dir, transport=transport)

            # Add mock instance with async hook
            called = []

            class MockInstance:
                async def on_stop(self, ctx):
                    called.append("on_stop")

            runtime.loaded_plugin.instances.append(MockInstance())

            await runtime._run_lifecycle("on_stop")

            assert "on_stop" in called

    @pytest.mark.asyncio
    async def test_run_lifecycle_missing_method(self):
        """_run_lifecycle should skip missing methods."""
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_dir = Path(temp_dir)
            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {"python": "3.12"},
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            transport = MemoryTransport()
            runtime = PluginWorkerRuntime(plugin_dir=plugin_dir, transport=transport)

            # Add mock instance without the method
            class MockInstance:
                pass

            runtime.loaded_plugin.instances.append(MockInstance())

            # Should not raise
            await runtime._run_lifecycle("on_start")


class TestIntegrationWithTransportPair:
    """Integration tests using transport pairs."""

    @pytest.mark.asyncio
    async def test_supervisor_responds_to_initialize(self):
        """SupervisorRuntime should respond to initialize messages."""
        left, right = make_transport_pair()
        core = await start_test_core_peer(left)

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = SupervisorRuntime(
                transport=right,
                plugins_dir=Path(temp_dir),
                env_manager=FakeEnvManager(),
            )

            try:
                await runtime.start()
                await core.wait_until_remote_initialized()
                assert core.remote_peer is not None
                assert core.remote_peer.name == "astrbot-supervisor"
                assert core.remote_metadata["plugins"] == []
                assert core.remote_metadata["skipped_plugins"] == {}

            finally:
                await runtime.stop()
                await core.stop()

    @pytest.mark.asyncio
    async def test_worker_session_lifecycle(self):
        """WorkerSession should start and stop cleanly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a minimal plugin
            plugin_dir = Path(temp_dir) / "plugins" / "test_plugin"
            plugin_dir.mkdir(parents=True)

            manifest_path = plugin_dir / "plugin.yaml"
            requirements_path = plugin_dir / "requirements.txt"

            manifest_path.write_text(
                yaml.dump(
                    {
                        "name": "test_plugin",
                        "runtime": {
                            "python": f"{sys.version_info.major}.{sys.version_info.minor}"
                        },
                        "components": [],
                    }
                ),
                encoding="utf-8",
            )
            requirements_path.write_text("", encoding="utf-8")

            plugin = PluginSpec(
                name="test_plugin",
                plugin_dir=plugin_dir,
                manifest_path=manifest_path,
                requirements_path=requirements_path,
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
                manifest_data={"name": "test_plugin"},
            )

            left, right = make_transport_pair()

            session = WorkerSession(
                plugin=plugin,
                repo_root=Path(temp_dir),
                env_manager=FakeEnvManager(),
                capability_router=CapabilityRouter(),
            )

            # Note: Full start would require subprocess, skip for unit test
            # Just verify the session can be created and stopped
            await session.stop()
