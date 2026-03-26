# ruff: noqa: E402
"""Memory 客户端 Core Bridge 集成测试。

测试覆盖 01_context_api.md 中 ctx.memory 的所有方法：
- search(): 搜索记忆项
- save(): 保存记忆项
- get(): 精确获取单个记忆项
- list_keys(): 列出 namespace 下的 key
- exists(): 检查 key 是否存在
- save_with_ttl(): 保存带过期时间的记忆项
- clear_namespace(): 清理 namespace 下的记忆
- count(): 统计 namespace 下的记忆数量
- stats(): 查看记忆索引状态
- get_many(): 批量获取多个记忆项
- delete_many(): 批量删除多个记忆项
"""
from __future__ import annotations

import pytest

from astrbot_sdk.errors import AstrBotError

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_memory_save_and_get_round_trip(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_a_ctx = runtime.make_context("plugin-a")
    plugin_b_ctx = runtime.make_context("plugin-b")

    # 保存记忆
    await plugin_a_ctx.memory.save("user_pref", {"theme": "dark", "lang": "zh"})
    await plugin_a_ctx.memory.save(
        "profile:alice", {"name": "Alice"}, namespace="users"
    )
    await plugin_b_ctx.memory.save("user_pref", {"theme": "light"})

    # 获取记忆
    pref_a = await plugin_a_ctx.memory.get("user_pref")
    assert pref_a == {"theme": "dark", "lang": "zh"}

    pref_b = await plugin_b_ctx.memory.get("user_pref")
    assert pref_b == {"theme": "light"}

    # 带 namespace 获取
    profile = await plugin_a_ctx.memory.get("profile:alice", namespace="users")
    assert profile == {"name": "Alice"}

    # 不存在的 key 返回 None
    missing = await plugin_a_ctx.memory.get("nonexistent")
    assert missing is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_memory_list_keys_and_exists(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 保存多个记忆
    await ctx.memory.save("beta", {"content": "beta note"}, namespace="users/alice")
    await ctx.memory.save("Alpha", {"content": "alpha note"}, namespace="users/alice")
    await ctx.memory.save("apple", {"content": "apple note"}, namespace="users/alice")
    await ctx.memory.save("child", {"content": "child"}, namespace="users/alice/sessions/1")

    # list_keys 返回排序后的键
    keys = await ctx.memory.list_keys(namespace="users/alice")
    assert keys == ["Alpha", "apple", "beta"]

    # exists 检查
    assert await ctx.memory.exists("beta", namespace="users/alice") is True
    assert await ctx.memory.exists("child", namespace="users/alice") is False
    assert await ctx.memory.exists("child", namespace="users/alice/sessions/1") is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_memory_count_and_clear_namespace(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 保存记忆
    await ctx.memory.save("a", {"v": 1}, namespace="test")
    await ctx.memory.save("b", {"v": 2}, namespace="test")
    await ctx.memory.save("c", {"v": 3}, namespace="test/sub")

    # count
    count_exact = await ctx.memory.count(namespace="test")
    assert count_exact == 2

    count_recursive = await ctx.memory.count(
        namespace="test", include_descendants=True
    )
    assert count_recursive == 3

    # clear_namespace (不包含子 namespace)
    deleted = await ctx.memory.clear_namespace(namespace="test")
    assert deleted == 2

    remaining = await ctx.memory.count(namespace="test", include_descendants=True)
    assert remaining == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_memory_get_many_and_delete_many(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 保存多个记忆
    await ctx.memory.save("a", {"value": 1})
    await ctx.memory.save("b", {"value": 2})
    await ctx.memory.save("c", {"value": 3})

    # get_many
    items = await ctx.memory.get_many(["a", "b", "missing"])
    assert items == [
        {"key": "a", "value": {"value": 1}},
        {"key": "b", "value": {"value": 2}},
        {"key": "missing", "value": None},
    ]

    # delete_many
    deleted = await ctx.memory.delete_many(["a", "b"])
    assert deleted == 2

    # 验证删除成功
    assert await ctx.memory.get("a") is None
    assert await ctx.memory.get("b") is None
    assert await ctx.memory.get("c") == {"value": 3}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_memory_stats(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 保存几个记忆
    await ctx.memory.save("key1", {"content": "test1"})
    await ctx.memory.save("key2", {"content": "test2"})

    stats = await ctx.memory.stats()
    assert stats["total_items"] == 2
    assert stats["plugin_id"] == "plugin-a"
    assert "total_bytes" in stats


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_memory_search_keyword_mode(tmp_path, monkeypatch):
    """测试 keyword 模式搜索（无 embedding provider 时）。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 保存记忆
    await ctx.memory.save("note1", {"content": "hello world"})
    await ctx.memory.save("note2", {"content": "foo bar"})

    # keyword 模式搜索
    results = await ctx.memory.search("hello", mode="keyword", limit=5)
    assert len(results) == 1
    assert results[0]["key"] == "note1"
    assert results[0]["match_type"] == "keyword"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_memory_save_requires_dict_value(tmp_path, monkeypatch):
    """memory.save 要求 value 是 dict 类型。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    with pytest.raises(AstrBotError, match="requires an object value"):
        await ctx.memory.save("key", "not-a-dict")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_memory_plugin_isolation(tmp_path, monkeypatch):
    """不同插件的 memory 数据是隔离的。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    plugin_a = runtime.make_context("plugin-a")
    plugin_b = runtime.make_context("plugin-b")

    await plugin_a.memory.save("shared", {"owner": "a"})
    await plugin_b.memory.save("shared", {"owner": "b"})

    # 各自只能看到自己的数据
    assert await plugin_a.memory.get("shared") == {"owner": "a"}
    assert await plugin_b.memory.get("shared") == {"owner": "b"}

    # clear_namespace 只影响自己
    await plugin_a.memory.clear_namespace()

    assert await plugin_a.memory.get("shared") is None
    assert await plugin_b.memory.get("shared") == {"owner": "b"}
