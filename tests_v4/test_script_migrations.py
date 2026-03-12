from __future__ import annotations

import asyncio
import contextlib
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.bootstrap import PluginWorkerRuntime, SupervisorRuntime
from astrbot_sdk.runtime.capability_router import CapabilityRouter
from astrbot_sdk.runtime.peer import Peer
from astrbot_sdk.runtime.transport import (
    WebSocketClientTransport,
    WebSocketServerTransport,
)

from tests_v4.helpers import FakeEnvManager, make_transport_pair


def write_websocket_plugin(plugin_root: Path) -> None:
    (plugin_root / "commands").mkdir(parents=True, exist_ok=True)
    (plugin_root / "commands" / "__init__.py").write_text("", encoding="utf-8")
    (plugin_root / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_root / "plugin.yaml").write_text(
        textwrap.dedent(
            f"""\
            _schema_version: 2
            name: websocket_plugin
            display_name: WebSocket Plugin
            desc: websocket test
            author: tester
            version: 0.1.0
            runtime:
              python: "{sys.version_info.major}.{sys.version_info.minor}"
            components:
              - class: commands.sample:MyPlugin
                type: command
                name: hello
                description: hello
            """
        ),
        encoding="utf-8",
    )
    (plugin_root / "commands" / "sample.py").write_text(
        textwrap.dedent(
            """\
            from astrbot_sdk import Context, MessageEvent, Star, on_command


            class MyPlugin(Star):
                @on_command("hello")
                async def hello(self, event: MessageEvent, ctx: Context):
                    await event.reply(f"ws:{event.text}")
            """
        ),
        encoding="utf-8",
    )


def write_benchmark_plugin(plugins_dir: Path, index: int) -> None:
    plugin_name = f"plugin_{index:03d}"
    command_name = f"bench_{index:03d}"
    plugin_dir = plugins_dir / plugin_name
    commands_dir = plugin_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "plugin.yaml").write_text(
        textwrap.dedent(
            f"""\
            _schema_version: 2
            name: {plugin_name}
            display_name: {plugin_name}
            desc: benchmark plugin {index}
            author: tester
            version: 0.1.0
            runtime:
              python: "{sys.version_info.major}.{sys.version_info.minor}"
            components:
              - class: commands.plugin_{index:03d}:BenchmarkCommand{index:03d}
                type: command
                name: {command_name}
                description: {command_name}
            """
        ),
        encoding="utf-8",
    )
    (commands_dir / f"plugin_{index:03d}.py").write_text(
        textwrap.dedent(
            f"""\
            from astrbot_sdk.api.components.command import CommandComponent
            from astrbot_sdk.api.event import AstrMessageEvent, filter
            from astrbot_sdk.api.star.context import Context


            class BenchmarkCommand{index:03d}(CommandComponent):
                def __init__(self, context: Context):
                    self.context = context

                @filter.command("{command_name}")
                async def handle(self, event: AstrMessageEvent):
                    yield event.plain_result("{plugin_name}:{command_name}")
            """
        ),
        encoding="utf-8",
    )


class StartClientMigrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_plugin_worker_supports_handshake_and_handler_invoke(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "websocket_plugin"
            write_websocket_plugin(plugin_root)

            server_transport = WebSocketServerTransport(
                host="127.0.0.1", port=0, path="/ws"
            )
            runtime = PluginWorkerRuntime(
                plugin_dir=plugin_root, transport=server_transport
            )
            runtime_task = asyncio.create_task(runtime.start())

            try:
                for _ in range(100):
                    if server_transport.port != 0:
                        break
                    await asyncio.sleep(0.02)

                core_router = CapabilityRouter()
                core_peer = Peer(
                    transport=WebSocketClientTransport(url=server_transport.url),
                    peer_info=PeerInfo(
                        name="websocket-core", role="core", version="v4"
                    ),
                )
                core_peer.set_initialize_handler(
                    lambda _message: asyncio.sleep(
                        0,
                        result=InitializeOutput(
                            peer=PeerInfo(
                                name="websocket-core", role="core", version="v4"
                            ),
                            capabilities=core_router.descriptors(),
                            metadata={},
                        ),
                    )
                )
                core_peer.set_invoke_handler(
                    lambda message, cancel_token: core_router.execute(
                        message.capability,
                        message.input,
                        stream=message.stream,
                        cancel_token=cancel_token,
                        request_id=message.id,
                    )
                )
                await core_peer.start()
                try:
                    await asyncio.wait_for(runtime_task, timeout=5)
                    await core_peer.wait_until_remote_initialized()
                    handler_id = core_peer.remote_handlers[0].id
                    self.assertEqual(
                        core_peer.remote_metadata["plugin_id"], "websocket_plugin"
                    )
                    self.assertEqual(
                        core_peer.remote_handlers[0].trigger.command, "hello"
                    )

                    await core_peer.invoke(
                        "handler.invoke",
                        {
                            "handler_id": handler_id,
                            "event": {
                                "text": "hello-websocket",
                                "session_id": "session-ws",
                                "user_id": "user-1",
                                "platform": "test",
                            },
                        },
                        request_id="call-ws",
                    )

                    self.assertEqual(
                        [item.get("text") for item in core_router.sent_messages],
                        ["ws:hello-websocket"],
                    )
                finally:
                    await core_peer.stop()
            finally:
                if not runtime_task.done():
                    runtime_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await runtime_task
                await runtime.stop()


class BenchmarkMigrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.left, self.right = make_transport_pair()
        self.core = Peer(
            transport=self.left,
            peer_info=PeerInfo(name="benchmark-core", role="core", version="v4"),
        )
        self.core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="benchmark-core", role="core", version="v4"),
                    capabilities=[],
                    metadata={},
                ),
            )
        )
        await self.core.start()

    async def asyncTearDown(self) -> None:
        await self.core.stop()

    async def test_benchmark_style_runtime_report_covers_multi_plugin_workers(
        self,
    ) -> None:
        plugin_count = 8
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir) / "plugins"
            for index in range(plugin_count):
                write_benchmark_plugin(plugins_dir, index)

            runtime = SupervisorRuntime(
                transport=self.right,
                plugins_dir=plugins_dir,
                env_manager=FakeEnvManager(),
            )
            started_at = time.perf_counter()
            try:
                await runtime.start()
                await self.core.wait_until_remote_initialized()
                measured_at = time.perf_counter()

                worker_pids = sorted(
                    process.pid
                    for session in runtime.worker_sessions.values()
                    if (
                        process := getattr(
                            getattr(session.peer, "transport", None), "_process", None
                        )
                    )
                    is not None
                    and process.returncode is None
                )
                report = {
                    "plugin_count": plugin_count,
                    "loaded_plugin_count": len(runtime.loaded_plugins),
                    "loaded_plugins": sorted(runtime.loaded_plugins),
                    "aggregated_handler_ids": list(
                        self.core.remote_metadata["aggregated_handler_ids"]
                    ),
                    "startup_total_duration_ms": round(
                        (measured_at - started_at) * 1000, 2
                    ),
                    "worker_pids": worker_pids,
                }

                handler_id = next(
                    item.id
                    for item in self.core.remote_handlers
                    if item.id.startswith("plugin_002:")
                )
                await self.core.invoke(
                    "handler.invoke",
                    {
                        "handler_id": handler_id,
                        "event": {
                            "text": "/bench_002",
                            "session_id": "bench-session",
                            "user_id": "user-1",
                            "platform": "test",
                        },
                    },
                    request_id="bench-call",
                )

                self.assertEqual(report["loaded_plugin_count"], plugin_count)
                self.assertEqual(len(report["worker_pids"]), plugin_count)
                self.assertEqual(len(report["aggregated_handler_ids"]), plugin_count)
                self.assertEqual(
                    report["loaded_plugins"],
                    [f"plugin_{index:03d}" for index in range(plugin_count)],
                )
                self.assertGreaterEqual(report["startup_total_duration_ms"], 0)
                self.assertIn(
                    "plugin_002:bench_002",
                    runtime.capability_router.sent_messages[-1]["text"],
                )
            finally:
                await runtime.stop()


if __name__ == "__main__":
    unittest.main()
