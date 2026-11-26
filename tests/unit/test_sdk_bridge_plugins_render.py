from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.sdk_bridge.services.plugins import PluginInspectService
from astrbot.core.star.sdk_bridge.services.render import RenderImageService
from astrbot.core.star.sdk_bridge.services.assets import AssetStore
from astrbot.core.star.star import StarMetadata, star_registry
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot_sdk.context import RuntimeMode
from astrbot_sdk.errors import NotFound
from astrbot_sdk.render import RenderOptions, TextRenderOptions

from tests.unit.test_sdk_bridge import FakeCoreEvent, FakeKVStore


@pytest.mark.asyncio
async def test_plugin_inspect_lists_registry() -> None:
    legacy = StarMetadata(
        name="legacy_one",
        author="alice",
        desc="legacy plugin",
        version="1.2.3",
        module_path="data.plugins.legacy_one.main",
        activated=True,
    )
    sdk = StarMetadata(
        name="sdk_one",
        author="bob",
        desc="sdk plugin",
        version="0.1.0",
        module_path="sdk_bridge.sdk_one",
        activated=True,
    )
    star_registry.extend([legacy, sdk])
    try:
        service = PluginInspectService()
        result = await service.handle("list", {})
        by_id = {p.id: p for p in result["plugins"]}
        assert by_id["alice/legacy_one"].runtime_mode is RuntimeMode.IN_PROCESS
        assert by_id["bob/sdk_one"].runtime_mode is RuntimeMode.ISOLATED
        assert by_id["alice/legacy_one"].version == "1.2.3"

        result = await service.handle("get", {"plugin_id": "alice/legacy_one"})
        assert result["plugin"].desc == "legacy plugin"
        result = await service.handle("get", {"plugin_id": "nobody/none"})
        assert result["plugin"] is None

        with pytest.raises(NotFound):
            await service.handle("delete", {})
    finally:
        star_registry.remove(legacy)
        star_registry.remove(sdk)


@pytest.mark.asyncio
async def test_render_service_stores_rendered_image(tmp_path: Path) -> None:
    image = tmp_path / "render.png"
    image.write_bytes(b"png-bytes")

    context = MagicMock()
    context.html_renderer.render_custom_template = AsyncMock(
        return_value=str(image),
    )
    context.html_renderer.render_t2i = AsyncMock(return_value=str(image))
    store = AssetStore(tmp_path / "assets", "author/plugin")
    service = RenderImageService(context, store)

    result = await service.handle(
        "html",
        {
            "template": "<h1>{{ title }}</h1>",
            "data": {"title": "hi"},
            "options": RenderOptions(width=800),
        },
    )
    asset = result["asset"]
    assert asset.media_type == "image/png"
    assert store.read(asset.id, 0, 9) == b"png-bytes"
    context.html_renderer.render_custom_template.assert_awaited_once()

    result = await service.handle(
        "text",
        {"text": "hello", "options": TextRenderOptions(template_name="default")},
    )
    assert store.read(result["asset"].id, 0, 9) == b"png-bytes"

    with pytest.raises(NotFound):
        await service.handle("gif", {})


def write_render_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "name": f"plugin_{plugin_root.name}",
                "desc": "plugins+render bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {
                    "api": "sdk",
                    "entrypoint": "main:TestPlugin",
                    "sdk_version": ">=0.1,<0.2",
                },
                "capabilities": {
                    "required": [
                        {"id": "plugin.inspect"},
                        {"id": "render.image"},
                    ],
                },
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(
        """
from astrbot_sdk import MessageEvent, Plugin, on

class TestPlugin(Plugin):
    @on.command("who")
    async def who(self, event: MessageEvent):
        me = await self.ctx.plugins.get("astrbot/" + self.ctx.plugin.name)
        plugins = await self.ctx.plugins.list()
        yield event.reply(f"me={me.version}; total={len(plugins)}")

    @on.command("draw")
    async def draw(self, event: MessageEvent):
        asset = await self.ctx.render.text("hello render")
        yield event.reply(f"asset={asset.id}")
""",
        "utf-8",
    )


@pytest.mark.asyncio
async def test_bridge_plugins_render_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "plugins_render_e2e"
    write_render_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    image = tmp_path / "r.png"
    image.write_bytes(b"png")
    context = MagicMock()
    context.html_renderer.render_t2i = AsyncMock(return_value=str(image))

    bridge = SDKPluginBridge(plugin_root, context)
    try:
        await bridge.start()
        handlers = star_handlers_registry.star_handlers_map

        event = FakeCoreEvent("who")
        who = handlers[f"sdk_bridge.{plugin_root.name}_who"]
        assert who.event_filters[0].filter(event, None)
        replies = []
        async for _ in who.handler(event):
            if event.get_result():
                replies.append(event.get_result().chain[0].text)
            event.clear_result()
        assert replies[0].startswith("me=1.0.0; total=")
        assert int(replies[0].rsplit("=", 1)[1]) >= 1

        event = FakeCoreEvent("draw")
        draw = handlers[f"sdk_bridge.{plugin_root.name}_draw"]
        assert draw.event_filters[0].filter(event, None)
        replies = []
        async for _ in draw.handler(event):
            if event.get_result():
                replies.append(event.get_result().chain[0].text)
            event.clear_result()
        assert replies[0].startswith("asset=ast_")
    finally:
        await bridge.stop()
