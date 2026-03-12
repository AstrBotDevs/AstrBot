from __future__ import annotations

import asyncio
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.bootstrap import SupervisorRuntime
from astrbot_sdk.runtime.loader import discover_plugins
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import FakeEnvManager, make_transport_pair


def write_plugin(
    root: Path,
    folder_name: str,
    *,
    plugin_name: str | None = None,
    python_version: str | None = None,
    include_requirements: bool = True,
    reply_text: str | None = None,
) -> Path:
    plugin_dir = root / folder_name
    commands_dir = plugin_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "__init__.py").write_text("", encoding="utf-8")

    if python_version is None:
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

    manifest_lines = [
        "_schema_version: 2",
        f"name: {plugin_name or folder_name}",
        f"display_name: {folder_name}",
        "desc: test plugin",
        "author: tester",
        "version: 0.1.0",
    ]
    if python_version != "__missing__":
        manifest_lines.extend(
            [
                "runtime:",
                f'  python: "{python_version}"',
            ]
        )
    manifest_lines.extend(
        [
            "components:",
            "  - class: commands.sample:SamplePlugin",
            "    type: command",
            "    name: hello",
            "    description: hello",
        ]
    )
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(manifest_lines) + "\n", encoding="utf-8"
    )
    if include_requirements:
        (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")

    text = reply_text or f"{plugin_name or folder_name} handled"
    (commands_dir / "sample.py").write_text(
        textwrap.dedent(
            f"""\
            from astrbot_sdk import Context, MessageEvent, Star, on_command


            class SamplePlugin(Star):
                @on_command("hello")
                async def hello(self, event: MessageEvent, ctx: Context):
                    await event.reply({text!r})
            """
        ),
        encoding="utf-8",
    )
    return plugin_dir


class PluginDiscoveryMigrationTest(unittest.TestCase):
    def test_discover_plugins_keeps_old_supervisor_filtering_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_plugin(root, "plugin_one", plugin_name="plugin_one")
            write_plugin(
                root,
                "plugin_two",
                plugin_name="plugin_two",
                python_version="__missing__",
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


class SupervisorMigrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.left, self.right = make_transport_pair()
        self.core = Peer(
            transport=self.left,
            peer_info=PeerInfo(name="test-core", role="core", version="v4"),
        )
        self.core.set_initialize_handler(
            lambda _message: asyncio.sleep(
                0,
                result=InitializeOutput(
                    peer=PeerInfo(name="test-core", role="core", version="v4"),
                    capabilities=[],
                    metadata={},
                ),
            )
        )
        await self.core.start()

    async def asyncTearDown(self) -> None:
        await self.core.stop()

    async def test_supervisor_aggregates_handlers_and_routes_target_plugin(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plugins_dir = Path(temp_dir) / "plugins"
            write_plugin(
                plugins_dir,
                "plugin_one",
                plugin_name="plugin_one",
                reply_text="plugin_one handled",
            )
            write_plugin(
                plugins_dir,
                "plugin_two",
                plugin_name="plugin_two",
                reply_text="plugin_two handled",
            )

            runtime = SupervisorRuntime(
                transport=self.right,
                plugins_dir=plugins_dir,
                env_manager=FakeEnvManager(),
            )
            try:
                await runtime.start()
                await self.core.wait_until_remote_initialized()

                self.assertEqual(
                    sorted(runtime.loaded_plugins), ["plugin_one", "plugin_two"]
                )
                self.assertEqual(
                    self.core.remote_metadata["plugins"], ["plugin_one", "plugin_two"]
                )
                self.assertEqual(len(self.core.remote_handlers), 2)

                handler_id = next(
                    item.id
                    for item in self.core.remote_handlers
                    if item.id.startswith("plugin_two:")
                )
                await self.core.invoke(
                    "handler.invoke",
                    {
                        "handler_id": handler_id,
                        "event": {
                            "text": "/hello",
                            "session_id": "session-1",
                            "user_id": "user-1",
                            "platform": "test",
                        },
                    },
                    request_id="call-route",
                )

                texts = [
                    item.get("text") for item in runtime.capability_router.sent_messages
                ]
                self.assertEqual(texts, ["plugin_two handled"])
            finally:
                await runtime.stop()


if __name__ == "__main__":
    unittest.main()
