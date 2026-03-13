from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import yaml

from astrbot_sdk.protocol.messages import InitializeOutput, PeerInfo
from astrbot_sdk.runtime.bootstrap import SupervisorRuntime
from astrbot_sdk.runtime.loader import discover_plugins
from astrbot_sdk.runtime.peer import Peer

from tests_v4.helpers import FakeEnvManager, copy_sample_plugin, make_transport_pair


def prepare_sample_plugin(
    root: Path,
    folder_name: str,
    *,
    sample_name: str = "new",
    plugin_name: str | None = None,
    python_version: str | None = None,
    include_requirements: bool = True,
) -> Path:
    plugin_dir = copy_sample_plugin(sample_name, root / folder_name, ascii_only=True)
    manifest_path = plugin_dir / "plugin.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    manifest["name"] = plugin_name or folder_name
    manifest["display_name"] = folder_name
    if python_version == "__missing__":
        manifest.pop("runtime", None)
    elif python_version is not None:
        manifest["runtime"] = {"python": python_version}
    manifest_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    requirements_path = plugin_dir / "requirements.txt"
    if include_requirements:
        requirements_path.write_text(
            requirements_path.read_text(encoding="utf-8")
            if requirements_path.exists()
            else "",
            encoding="utf-8",
        )
    elif requirements_path.exists():
        requirements_path.unlink()
    return plugin_dir


class PluginDiscoveryMigrationTest(unittest.TestCase):
    def test_discover_plugins_keeps_old_supervisor_filtering_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            prepare_sample_plugin(root, "plugin_one", plugin_name="plugin_one")
            prepare_sample_plugin(
                root,
                "plugin_two",
                plugin_name="plugin_two",
                python_version="__missing__",
            )
            prepare_sample_plugin(
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
            prepare_sample_plugin(
                plugins_dir,
                "plugin_one",
                plugin_name="plugin_one",
            )
            prepare_sample_plugin(
                plugins_dir,
                "plugin_two",
                plugin_name="plugin_two",
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
                self.assertEqual(len(self.core.remote_handlers), 18)

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
                self.assertEqual(texts, ["Echo: /hello", "Echo: stream"])
            finally:
                await runtime.stop()


if __name__ == "__main__":
    unittest.main()
