from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from astrbot_sdk.assets import AssetRef
from astrbot_sdk.errors import CapabilityDenied, InvalidRequest, RateLimited

from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.sdk_bridge.services.assets import AssetStore
from astrbot.core.star.star_handler import star_handlers_registry
from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


def test_store_put_stat_read_resolve(tmp_path: Path) -> None:
    store = AssetStore(tmp_path, "author/plugin")
    asset = store.put(b"hello world", filename="a.txt", media_type="text/plain")

    assert asset.size == 11
    assert store.stat(asset.id)["filename"] == "a.txt"
    assert store.read(asset.id, 6, 5) == b"world"
    assert store.resolve(asset).read_bytes() == b"hello world"


def test_store_rejects_foreign_or_unknown_assets(tmp_path: Path) -> None:
    store = AssetStore(tmp_path, "author/plugin")
    with pytest.raises(CapabilityDenied):
        store.resolve(AssetRef(id="ast_missing"))
    evil = AssetRef(id="../escape")
    with pytest.raises((CapabilityDenied, InvalidRequest)):
        store.resolve(evil)


def test_store_quota_single_file(tmp_path: Path) -> None:
    store = AssetStore(tmp_path, "author/plugin")
    with pytest.raises(RateLimited):
        store.put(b"x" * (51 * 1024 * 1024), filename=None, media_type=None)


def test_store_chunked_upload_lifecycle(tmp_path: Path) -> None:
    store = AssetStore(tmp_path, "author/plugin")
    upload_id = store.begin_pending({"filename": "big.bin", "size": 11})
    store.append_pending(upload_id, 0, b"hello ")
    store.append_pending(upload_id, 1, b"world")
    asset = store.commit_pending(upload_id)
    assert asset.size == 11
    assert store.read(asset.id, 0, 11) == b"hello world"

    with pytest.raises(InvalidRequest):
        bad = store.begin_pending({"size": 100})
        store.append_pending(bad, 0, b"short")
        store.commit_pending(bad)

    orphan = store.begin_pending({"size": 1})
    store.abort_pending(orphan)
    assert not list((tmp_path / "author_plugin" / "pending").glob("*"))


def write_asset_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "asset bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {
                    "required": [{"id": "message.send"}],
                },
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on
from astrbot_sdk.message_components import File, Image

class TestPlugin(Plugin):
    @on.command("roundtrip")
    async def roundtrip(self, event: MessageEvent):
        # Outbound: local bytes auto-upload before the reply crosses over.
        yield event.reply(Image.from_bytes(b"fake-png-data", media_type="image/png"))

        # Upload explicitly, then download it back to a local file.
        asset = await self.ctx.assets.upload(b"report-body", filename="r.txt")
        path = await self.ctx.assets.download(asset)
        body = path.read_bytes()

        # Proactive send resolves the asset to a real file for the platform.
        await self.ctx.messages.send(
            event.umo,
            File.from_bytes(body, media_type="text/plain", filename="r.txt"),
        )
        yield event.reply(f"roundtrip:{len(body)}")
""",
        "utf-8",
    )


@pytest.mark.asyncio
async def test_bridge_assets_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "asset_bridge_e2e"
    write_asset_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    context = MagicMock()
    context.send_message = AsyncMock(return_value=True)

    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        handler = star_handlers_registry.star_handlers_map[
            f"sdk_bridge.{plugin_root.name}_roundtrip"
        ]

        event = FakeCoreEvent("roundtrip")
        assert handler.event_filters[0].filter(event, None)

        replies = []
        async for _ in handler.handler(event):
            result = event.get_result()
            if result:
                replies.append(result)
            event.clear_result()

        # First reply: the uploaded image resolved back to a real local file.
        image = replies[0].chain[0]
        assert image.file.startswith("file://")
        assert Path(image.path).read_bytes() == b"fake-png-data"

        assert replies[1].chain[0].text == "roundtrip:11"

        # Proactive File send also resolved to a real file path.
        sent_chain = context.send_message.await_args.args[1]
        assert Path(sent_chain.chain[0].file).read_bytes() == b"report-body"

        # Assets live below the plugin namespace.
        namespace = bridge.plugin_id.replace("/", "_")
        stored = list((tmp_path / "assets" / namespace).glob("*.bin"))
        assert len(stored) == 3
    finally:
        await bridge.stop()
