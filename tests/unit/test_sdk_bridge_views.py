from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from astrbot.core.star.sdk_bridge import SDKPluginBridge
from astrbot.core.star.star import star_map
from astrbot.dashboard.services.plugin_page_service import PluginPageService
from tests.unit.test_sdk_bridge import FakeKVStore


async def _empty_snapshot(_context):
    """Stub out the legacy host-state snapshot for MagicMock contexts."""
    return {}


PLUGIN_SOURCE = """
from astrbot.api.star import Context, Star


class ViewsBridgePlugin(Star):
    pass
"""


def write_legacy_views_plugin(plugin_root: Path) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "views_bridge_test",
                "desc": "views bridge test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
                "runtime": {"isolated": True},
                "views": [{"name": "demo", "title": "Demo Page"}],
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(PLUGIN_SOURCE, "utf-8")
    demo = plugin_root / "pages" / "demo"
    demo.mkdir(parents=True)
    (demo / "index.html").write_text(
        '<html><body><img src="./logo.png"></body></html>',
        "utf-8",
    )
    (demo / "logo.png").write_bytes(b"png-bytes")
    (demo / "app.js").write_text(
        'import { helper } from "./lib/helper.js";\nhelper();\n',
        "utf-8",
    )
    lib = demo / "lib"
    lib.mkdir()
    (lib / "helper.js").write_text("export const helper = () => {};\n", "utf-8")
    i18n_dir = plugin_root / ".astrbot-plugin" / "i18n"
    i18n_dir.mkdir(parents=True)
    (i18n_dir / "zh-CN.json").write_text(
        '{"views": {"demo": {"title": "演示页"}}}',
        "utf-8",
    )


@pytest.mark.asyncio
async def test_bridge_views_served_via_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = tmp_path / "views_bridge_test"
    write_legacy_views_plugin(plugin_root)
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.services.storage.sp",
        FakeKVStore(),
    )
    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge._asset_root",
        lambda: tmp_path / "assets",
    )

    monkeypatch.setattr(
        "astrbot.core.star.sdk_bridge.bridge.build_legacy_snapshot",
        _empty_snapshot,
    )
    context = MagicMock()
    context.registered_web_apis = []
    bridge = SDKPluginBridge(plugin_root, context, legacy=True)
    manager = MagicMock()
    manager._sdk_plugin_manager = MagicMock()
    manager._sdk_plugin_manager.bridges = {plugin_root.name: bridge}
    manager.context.get_all_stars = lambda: [
        star_map[bridge.module_path],
    ]
    try:
        await bridge.start()
        metadata = star_map[bridge.module_path]
        # metadata.yaml's views declaration and the manifest's i18n both
        # reached the registry entry.
        assert metadata.views == [{"name": "demo", "title": "Demo Page"}]
        assert metadata.i18n == {"zh-CN": {"views": {"demo": {"title": "演示页"}}}}
        assert bridge._views_manifest["pages"][0]["name"] == "demo"

        service = PluginPageService(manager)
        pages = await service.discover_plugin_pages(metadata)
        assert [page.name for page in pages] == ["demo"]

        # The entry HTML comes through the pipeline and gets its asset
        # URLs rewritten like any other plugin page.
        payload = await service.serve_page_content(
            plugin_name=metadata.name,
            view_name="demo",
            asset_path="",
            asset_token="",
            username="admin",
            locale="zh-CN",
            theme=None,
        )
        assert payload.content_type.startswith("text/html")
        assert "logo.png" in payload.content
        assert "/api/plugin/page/" in payload.content

        # Binary assets also stream through the pipeline.
        payload = await service.serve_page_content(
            plugin_name=metadata.name,
            view_name="demo",
            asset_path="logo.png",
            asset_token="",
            username="admin",
            locale="zh-CN",
            theme=None,
        )
        assert payload.content == b"png-bytes"
        assert payload.content_type == "image/png"

        # JS modules are served as-is, mirroring the disk-served path:
        # path-token URLs make relative imports resolve correctly on their
        # own, so no rewriting is needed.
        payload = await service.serve_page_content(
            plugin_name=metadata.name,
            view_name="demo",
            asset_path="app.js",
            asset_token="",
            username="admin",
            locale="zh-CN",
            theme=None,
        )
        assert "javascript" in payload.content_type
        assert "./lib/helper.js" in payload.content
    finally:
        await bridge.stop()
