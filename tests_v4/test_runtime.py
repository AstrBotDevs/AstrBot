from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.bootstrap import SupervisorRuntime
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import FakeEnvManager, make_transport_pair


def write_new_plugin(plugin_root: Path) -> None:
    (plugin_root / "commands").mkdir(parents=True, exist_ok=True)
    (plugin_root / "commands" / "__init__.py").write_text("", encoding="utf-8")
    (plugin_root / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_root / "plugin.yaml").write_text(
        textwrap.dedent(
            f"""\
            _schema_version: 2
            name: v4_plugin
            display_name: V4 Plugin
            desc: test
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
                    reply = await ctx.llm.chat(event.text)
                    await event.reply(reply)
                    chunks = []
                    async for chunk in ctx.llm.stream_chat("stream"):
                        chunks.append(chunk)
                    await event.reply("".join(chunks))
            """
        ),
        encoding="utf-8",
    )


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
            write_new_plugin(plugin_root)

            runtime = SupervisorRuntime(
                transport=self.right,
                plugins_dir=plugins_root,
                env_manager=FakeEnvManager(),
            )
            try:
                await runtime.start()
                await self.core.wait_until_remote_initialized()
                handler_id = self.core.remote_handlers[0].id

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

    async def test_supervisor_runs_compat_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_root = Path(temp_dir) / "plugins"
            plugin_root = plugins_root / "compat_plugin"
            shutil.copytree(Path.cwd() / "test_plugin", plugin_root)

            runtime = SupervisorRuntime(
                transport=self.right,
                plugins_dir=plugins_root,
                env_manager=FakeEnvManager(),
            )
            try:
                await runtime.start()
                await self.core.wait_until_remote_initialized()
                handler_id = self.core.remote_handlers[0].id

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
                self.assertEqual(len(texts), 4)
                self.assertIn("Created conversation ID", texts[0])
            finally:
                await runtime.stop()
