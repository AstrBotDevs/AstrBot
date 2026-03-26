# ruff: noqa: E402
"""Metadata 客户端 Core Bridge 集成测试。

测试覆盖 01_context_api.md 中 ctx.metadata 的所有方法：
- get_plugin(): 获取指定插件信息
- list_plugins(): 获取所有插件列表
- get_current_plugin(): 获取当前插件信息
- get_plugin_config(): 获取插件配置
- save_plugin_config(): 保存插件配置
"""
from __future__ import annotations

import pytest

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_metadata_list_plugins(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    # 注册几个插件
    runtime.plugin_bridge.upsert_plugin(
        metadata={"name": "plugin-a", "display_name": "Plugin A", "version": "1.0.0"}
    )
    runtime.plugin_bridge.upsert_plugin(
        metadata={"name": "plugin-b", "display_name": "Plugin B", "version": "2.0.0"}
    )

    ctx = runtime.make_context("plugin-a")
    plugins = await ctx.metadata.list_plugins()

    assert len(plugins) == 2
    names = {p.name for p in plugins}
    assert names == {"plugin-a", "plugin-b"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_metadata_get_plugin(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    runtime.plugin_bridge.upsert_plugin(
        metadata={
            "name": "demo-plugin",
            "display_name": "Demo Plugin",
            "version": "3.0.0",
            "author": "Test Author",
            "description": "A demo plugin",
        }
    )

    ctx = runtime.make_context("plugin-a")
    plugin = await ctx.metadata.get_plugin("demo-plugin")

    assert plugin is not None
    assert plugin.name == "demo-plugin"
    assert plugin.display_name == "Demo Plugin"
    assert plugin.version == "3.0.0"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_metadata_get_plugin_returns_none_for_missing(
    tmp_path, monkeypatch
):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    plugin = await ctx.metadata.get_plugin("nonexistent-plugin")
    assert plugin is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_metadata_get_current_plugin(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    runtime.plugin_bridge.upsert_plugin(
        metadata={
            "name": "current-plugin",
            "display_name": "Current Plugin",
            "version": "1.5.0",
        }
    )

    ctx = runtime.make_context("current-plugin")
    current = await ctx.metadata.get_current_plugin()

    assert current is not None
    assert current.name == "current-plugin"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_metadata_get_plugin_config(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    runtime.plugin_bridge.upsert_plugin(
        metadata={"name": "configurable-plugin"},
        config={"api_key": "test-key", "timeout": 30},
    )

    ctx = runtime.make_context("configurable-plugin")
    config = await ctx.metadata.get_plugin_config()

    assert config == {"api_key": "test-key", "timeout": 30}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_metadata_save_plugin_config(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    runtime.plugin_bridge.upsert_plugin(
        metadata={"name": "configurable-plugin"},
        config={"old_key": "old_value"},
    )

    ctx = runtime.make_context("configurable-plugin")

    # 保存新配置
    await ctx.metadata.save_plugin_config({"new_key": "new_value"})

    # 验证配置已更新
    config = await ctx.metadata.get_plugin_config()
    assert config == {"new_key": "new_value"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_metadata_cannot_read_other_plugin_config(
    tmp_path, monkeypatch
):
    """插件不能读取其他插件的配置。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    runtime.plugin_bridge.upsert_plugin(
        metadata={"name": "plugin-a"},
        config={"secret": "a-secret"},
    )
    runtime.plugin_bridge.upsert_plugin(
        metadata={"name": "plugin-b"},
        config={"secret": "b-secret"},
    )

    ctx_a = runtime.make_context("plugin-a")
    ctx_b = runtime.make_context("plugin-b")

    # 每个插件只能读取自己的配置
    config_a = await ctx_a.metadata.get_plugin_config()
    config_b = await ctx_b.metadata.get_plugin_config()

    assert config_a == {"secret": "a-secret"}
    assert config_b == {"secret": "b-secret"}
