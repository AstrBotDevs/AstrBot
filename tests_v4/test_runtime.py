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

    def _find_handler_id(self, command_name: str) -> str:
        return next(
            handler.id
            for handler in self.core.remote_handlers
            if getattr(handler.trigger, "command", None) == command_name
        )

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
                handler_id = self._find_handler_id("hello")

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

    async def test_supervisor_runs_v4_plugin_client_commands(self) -> None:
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

                for request_id, command_name in (
                    ("call-v4-raw", "raw"),
                    ("call-v4-remember", "remember"),
                    ("call-v4-platforms", "platforms"),
                ):
                    await self.core.invoke(
                        "handler.invoke",
                        {
                            "handler_id": self._find_handler_id(command_name),
                            "event": {
                                "text": command_name,
                                "session_id": "session-v4-clients",
                                "user_id": "user-1",
                                "platform": "test",
                            },
                        },
                        request_id=request_id,
                    )

                texts = [
                    item.get("text")
                    for item in runtime.capability_router.sent_messages
                    if "text" in item
                ]
                self.assertTrue(
                    any(text.startswith("raw=Echo: raw|finish=stop|") for text in texts)
                )
                self.assertTrue(
                    any(
                        text.startswith(
                            "remembered=user-1|searched=1|session=session-v4-clients|keys=1"
                        )
                        for text in texts
                    )
                )
                image_message = next(
                    item
                    for item in runtime.capability_router.sent_messages
                    if item.get("image_url") == "https://example.com/demo.png"
                )
                self.assertEqual(image_message["session"], "session-v4-clients")
                self.assertEqual(
                    image_message["target"]["conversation_id"],
                    "session-v4-clients",
                )
                self.assertTrue(
                    any(
                        item.get("text", "").startswith(
                            "members=2 first=session-v4-clients:member-1"
                        )
                        for item in runtime.capability_router.sent_messages
                    )
                )
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
                self.assertIn("demo.stream", capability_names)

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
                handler_id = self._find_handler_id("announce")

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

    async def test_supervisor_exposes_real_v4_stream_capability(self) -> None:
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

                stream = await self.core.invoke_stream(
                    "demo.stream",
                    {"text": "abc"},
                    request_id="call-v4-stream-capability",
                )
                chunks = [event.data["text"] async for event in stream]
                self.assertEqual(chunks, ["a", "b", "c"])
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
                handler_id = self._find_handler_id("hello")

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

    async def test_supervisor_runs_compat_plugin_extended_api_commands(self) -> None:
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

                for request_id, command_name in (
                    ("call-compat-ai", "ai"),
                    ("call-compat-conversation", "conversation"),
                    ("call-compat-sendmsg", "sendmsg"),
                    ("call-compat-chain", "chain"),
                    ("call-compat-components", "components"),
                ):
                    await self.core.invoke(
                        "handler.invoke",
                        {
                            "handler_id": self._find_handler_id(command_name),
                            "event": {
                                "text": command_name,
                                "session_id": "session-compat-extended",
                                "user_id": "user-1",
                                "platform": "test",
                            },
                        },
                        request_id=request_id,
                    )

                texts = [
                    item.get("text")
                    for item in runtime.capability_router.sent_messages
                    if "text" in item
                ]
                self.assertTrue(
                    any(
                        text.startswith(
                            "LLM:Echo: legacy hello|AGENT:Echo: legacy hello"
                        )
                        for text in texts
                    )
                )
                self.assertTrue(
                    any(
                        text.startswith("conversation=") and "|helper=COMPAT" in text
                        for text in texts
                    )
                )
                self.assertTrue(any(text == "send_message invoked" for text in texts))
                chain_messages = [
                    item
                    for item in runtime.capability_router.sent_messages
                    if "chain" in item
                ]
                self.assertTrue(
                    any(
                        any(
                            component.get("type") == "At"
                            and component.get("user_id") == "all"
                            for component in item["chain"]
                        )
                        for item in chain_messages
                    )
                )
                self.assertTrue(
                    any(
                        any(
                            component.get("type") == "Node"
                            for component in item["chain"]
                        )
                        for item in chain_messages
                    )
                )
            finally:
                await runtime.stop()

    async def test_supervisor_exposes_compat_plugin_capability(self) -> None:
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

                capability_names = {
                    descriptor.name
                    for descriptor in self.core.remote_provided_capabilities
                }
                self.assertIn("compat.echo", capability_names)

                result = await self.core.invoke(
                    "compat.echo",
                    {"text": "legacy-capability"},
                    request_id="call-compat-capability",
                )
                self.assertEqual(
                    result,
                    {
                        "echo": "legacy-capability",
                        "plugin_id": "astrbot_plugin_helloworld",
                    },
                )
            finally:
                await runtime.stop()
