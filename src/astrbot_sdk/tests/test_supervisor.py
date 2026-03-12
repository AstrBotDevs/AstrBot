from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from astrbot_sdk.runtime.rpc.jsonrpc import (
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)
from astrbot_sdk.runtime.stars.registry import EventType, StarHandlerMetadata
from astrbot_sdk.runtime.supervisor import (
    PluginEnvironmentManager,
    PluginSpec,
    SupervisorRuntime,
    WorkerRuntime,
    discover_plugins,
)
from astrbot_sdk.runtime.types import CallHandlerRequest


def write_plugin(
    root: Path,
    folder_name: str,
    *,
    plugin_name: str | None = None,
    python_version: str | None = "3.12",
    include_requirements: bool = True,
) -> Path:
    plugin_dir = root / folder_name
    commands_dir = plugin_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "__init__.py").write_text("", encoding="utf-8")

    manifest: dict[str, Any] = {
        "_schema_version": 2,
        "name": plugin_name or folder_name,
        "display_name": folder_name,
        "desc": "test plugin",
        "author": "tester",
        "version": "0.1.0",
        "components": [
            {
                "class": "commands.sample:SampleCommand",
                "type": "command",
                "name": "hello",
                "description": "hello",
            }
        ],
    }
    if python_version is not None:
        manifest["runtime"] = {"python": python_version}

    (plugin_dir / "plugin.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    if include_requirements:
        (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    return plugin_dir


class FakeServer:
    def __init__(self) -> None:
        self.handler = None
        self.sent_messages: list[Any] = []

    def set_message_handler(self, handler) -> None:
        self.handler = handler

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_message(self, message) -> None:
        self.sent_messages.append(message)


class FakeEnvManager(PluginEnvironmentManager):
    def __init__(self) -> None:
        self.prepared: list[str] = []

    def prepare_environment(self, plugin: PluginSpec) -> Path:
        self.prepared.append(plugin.name)
        return Path("/tmp/fake-python")


class FakeWorkerRuntime(WorkerRuntime):
    def __init__(
        self,
        plugin: PluginSpec,
        server,
        repo_root: Path,
        env_manager: PluginEnvironmentManager,
    ) -> None:
        self.plugin = plugin
        self.server = server
        self.repo_root = repo_root
        self.env_manager = env_manager
        self.raw_handshake: dict[str, Any] = {}
        self.handlers: list[StarHandlerMetadata] = []
        self.forwarded_requests: list[JSONRPCRequest] = []
        self.received_context_responses: list[Any] = []
        self.stopped = False

    async def start(self) -> None:
        handler_full_name = (
            f"commands.{self.plugin.name}:SampleCommand.handle_{self.plugin.name}"
        )
        self.raw_handshake = {
            f"{self.plugin.name}.main": {
                "name": self.plugin.name,
                "author": "tester",
                "desc": "test plugin",
                "version": "0.1.0",
                "repo": None,
                "module_path": f"{self.plugin.name}.main",
                "root_dir_name": self.plugin.plugin_dir.name,
                "reserved": False,
                "activated": True,
                "config": None,
                "star_handler_full_names": [handler_full_name],
                "display_name": self.plugin.name,
                "logo_path": None,
                "handlers": [
                    {
                        "event_type": EventType.AdapterMessageEvent.value,
                        "handler_full_name": handler_full_name,
                        "handler_name": f"handle_{self.plugin.name}",
                        "handler_module_path": f"commands.{self.plugin.name}",
                        "desc": "",
                        "extras_configs": {},
                    }
                ],
            }
        }
        self.handlers = [
            StarHandlerMetadata(
                event_type=EventType.AdapterMessageEvent,
                handler_full_name=handler_full_name,
                handler_name=f"handle_{self.plugin.name}",
                handler_module_path=f"commands.{self.plugin.name}",
                handler=lambda *args, **kwargs: None,
                event_filters=[],
            )
        ]

    async def stop(self) -> None:
        self.stopped = True

    async def forward_call_handler(self, request: JSONRPCRequest) -> None:
        self.forwarded_requests.append(request)
        handler_full_name = self.handlers[0].handler_full_name
        await self.server.send_message(
            JSONRPCRequest(
                jsonrpc="2.0",
                method="handler_stream_start",
                params={
                    "id": request.id,
                    "handler_full_name": handler_full_name,
                },
            )
        )
        await self.server.send_message(
            JSONRPCRequest(
                jsonrpc="2.0",
                method="handler_stream_update",
                params={
                    "id": request.id,
                    "handler_full_name": handler_full_name,
                    "data": {"plugin": self.plugin.name},
                },
            )
        )
        await self.server.send_message(
            JSONRPCRequest(
                jsonrpc="2.0",
                method="handler_stream_end",
                params={
                    "id": request.id,
                    "handler_full_name": handler_full_name,
                },
            )
        )
        await self.server.send_message(
            JSONRPCSuccessResponse(
                jsonrpc="2.0",
                id=request.id,
                result={"handled_by": self.plugin.name},
            )
        )

    async def handle_context_response(self, message) -> bool:
        if message.id != f"ctx:{self.plugin.name}:1":
            return False
        self.received_context_responses.append(message)
        return True


class DiscoverPluginsTest(unittest.TestCase):
    def test_discover_plugins_requires_runtime_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_plugin(root, "plugin_one", plugin_name="plugin_one")
            write_plugin(
                root,
                "plugin_two",
                plugin_name="plugin_two",
                python_version=None,
            )
            write_plugin(
                root,
                "plugin_three",
                plugin_name="plugin_three",
                include_requirements=False,
            )

            discovery = discover_plugins(root)

        self.assertEqual([plugin.name for plugin in discovery.plugins], ["plugin_one"])
        self.assertIn("plugin_two", discovery.skipped_plugins)
        self.assertIn("plugin_three", discovery.skipped_plugins)


class SupervisorRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plugins_dir = Path(self.temp_dir.name)
        write_plugin(self.plugins_dir, "plugin_one", plugin_name="plugin_one")
        write_plugin(self.plugins_dir, "plugin_two", plugin_name="plugin_two")
        self.server = FakeServer()

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_handshake_aggregates_workers_and_routes_call_handler(self) -> None:
        runtime = SupervisorRuntime(
            server=self.server,
            plugins_dir=self.plugins_dir,
            env_manager=FakeEnvManager(),
            worker_factory=FakeWorkerRuntime,
        )
        await runtime.start()

        await self.server.handler(
            JSONRPCRequest(jsonrpc="2.0", id="handshake-1", method="handshake")
        )
        handshake_response = self.server.sent_messages[-1]
        self.assertIsInstance(handshake_response, JSONRPCSuccessResponse)
        self.assertEqual(
            sorted(handshake_response.result.keys()),
            ["plugin_one.main", "plugin_two.main"],
        )

        handler_full_name = "commands.plugin_two:SampleCommand.handle_plugin_two"
        await self.server.handler(
            CallHandlerRequest(
                jsonrpc="2.0",
                id="call-1",
                method="call_handler",
                params=CallHandlerRequest.Params(
                    handler_full_name=handler_full_name,
                    event={
                        "message_str": "hello",
                        "message_obj": {
                            "type": "FriendMessage",
                            "self_id": "bot",
                            "session_id": "session",
                            "message_id": "message-id",
                            "sender": {"user_id": "user-1", "nickname": "User 1"},
                            "message": [],
                            "message_str": "hello",
                            "raw_message": {},
                            "timestamp": 0,
                        },
                        "platform_meta": {
                            "name": "fake",
                            "description": "fake",
                            "id": "fake-1",
                        },
                        "session_id": "session",
                        "is_at_or_wake_command": True,
                    },
                    args={},
                ),
            )
        )

        self.assertEqual(
            self.server.sent_messages[-1].result, {"handled_by": "plugin_two"}
        )
        await runtime.stop()

    async def test_routes_context_response_back_to_matching_worker(self) -> None:
        runtime = SupervisorRuntime(
            server=self.server,
            plugins_dir=self.plugins_dir,
            env_manager=FakeEnvManager(),
            worker_factory=FakeWorkerRuntime,
        )
        await runtime.start()

        await self.server.handler(
            JSONRPCSuccessResponse(
                jsonrpc="2.0",
                id="ctx:plugin_one:1",
                result={"data": "ok"},
            )
        )

        worker = runtime._workers_by_name["plugin_one"]
        self.assertEqual(len(worker.received_context_responses), 1)
        await runtime.stop()


if __name__ == "__main__":
    unittest.main()
