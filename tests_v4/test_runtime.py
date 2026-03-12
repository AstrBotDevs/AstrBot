from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.bootstrap import SupervisorRuntime
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import FakeEnvManager, make_transport_pair


def sample_plugin_dir(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "test_plugin" / name


class RuntimeIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.left, self.right = make_transport_pair()
        self.core = Peer(
            transport=self.left,
            peer_info=PeerInfo(name="outer-core", role="core", version="v4"),
        )
        self.core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="outer-core", role="core", version="v4"),
                    capabilities=[],
                    metadata={},
                ),
            )
        )
        await self.core.start()

    async def asyncTearDown(self) -> None:
        await self.core.stop()

    async def test_supervisor_runs_v4_plugin_over_stdio_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_root = Path(temp_dir) / "plugins"
            plugin_root = plugins_root / "v4_plugin"
            shutil.copytree(sample_plugin_dir("new"), plugin_root)

            runtime = SupervisorRuntime(
                transport=self.right,
                plugins_dir=plugins_root,
                env_manager=FakeEnvManager(),
            )
            try:
                await runtime.start()
                await self.core.wait_until_remote_initialized()
                handler_id = next(
                    handler.id
                    for handler in self.core.remote_handlers
                    if getattr(handler.trigger, "command", None) == "hello"
                )

                await self.core.invoke(
                    "handler.invoke",
                    {
                        "handler_id": handler_id,
                        "event": {
                            "text": "hello",
                            "session_id": "session-1",
                            "user_id": "user-1",
                            "platform": "test",
                        },
                    },
                    request_id="call-v4",
                )
                texts = [
                    item.get("text") for item in runtime.capability_router.sent_messages
                ]
                self.assertEqual(texts, ["Echo: hello", "Echo: stream"])
            finally:
                await runtime.stop()

    async def test_supervisor_exposes_real_v4_plugin_capability(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_root = Path(temp_dir) / "plugins"
            plugin_root = plugins_root / "v4_plugin"
            shutil.copytree(sample_plugin_dir("new"), plugin_root)

            runtime = SupervisorRuntime(
                transport=self.right,
                plugins_dir=plugins_root,
                env_manager=FakeEnvManager(),
            )
            try:
                await runtime.start()
                await self.core.wait_until_remote_initialized()

                capability_names = {
                    descriptor.name
                    for descriptor in self.core.remote_provided_capabilities
                }
                self.assertIn("demo.echo", capability_names)

                result = await self.core.invoke(
                    "demo.echo",
                    {"text": "capability"},
                    request_id="call-v4-capability",
                )
                self.assertEqual(
                    result,
                    {
                        "echo": "capability",
                        "plugin_id": "astrbot_plugin_v4demo",
                    },
                )
            finally:
                await runtime.stop()

    async def test_supervisor_runs_v4_plugin_chain_send(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_root = Path(temp_dir) / "plugins"
            plugin_root = plugins_root / "v4_plugin"
            shutil.copytree(sample_plugin_dir("new"), plugin_root)

            runtime = SupervisorRuntime(
                transport=self.right,
                plugins_dir=plugins_root,
                env_manager=FakeEnvManager(),
            )
            try:
                await runtime.start()
                await self.core.wait_until_remote_initialized()
                handler_id = next(
                    handler.id
                    for handler in self.core.remote_handlers
                    if getattr(handler.trigger, "command", None) == "announce"
                )

                await self.core.invoke(
                    "handler.invoke",
                    {
                        "handler_id": handler_id,
                        "event": {
                            "text": "announce",
                            "session_id": "session-chain",
                            "user_id": "user-1",
                            "platform": "test",
                        },
                    },
                    request_id="call-v4-chain",
                )
                chain_message = runtime.capability_router.sent_messages[-1]
                self.assertEqual(chain_message["session"], "session-chain")
                self.assertEqual(
                    chain_message["target"]["conversation_id"],
                    "session-chain",
                )
                self.assertEqual(chain_message["chain"][0]["text"], "Demo ")
                self.assertEqual(
                    chain_message["chain"][1]["file"],
                    "https://example.com/demo.png",
                )
            finally:
                await runtime.stop()

    async def test_supervisor_runs_compat_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_root = Path(temp_dir) / "plugins"
            plugin_root = plugins_root / "compat_plugin"
            shutil.copytree(Path.cwd() / "test_plugin" / "old", plugin_root)

            runtime = SupervisorRuntime(
                transport=self.right,
                plugins_dir=plugins_root,
                env_manager=FakeEnvManager(),
            )
            try:
                await runtime.start()
                await self.core.wait_until_remote_initialized()
                handler_id = next(
                    handler.id
                    for handler in self.core.remote_handlers
                    if getattr(handler.trigger, "command", None) == "hello"
                )

                await self.core.invoke(
                    "handler.invoke",
                    {
                        "handler_id": handler_id,
                        "event": {
                            "text": "/hello",
                            "session_id": "session-compat",
                            "user_id": "user-1",
                            "platform": "test",
                        },
                    },
                    request_id="call-compat",
                )
                texts = [
                    item.get("text") for item in runtime.capability_router.sent_messages
                ]
                self.assertEqual(len(texts), 1)
                self.assertIn("Created conversation ID", texts[0])
            finally:
                await runtime.stop()
