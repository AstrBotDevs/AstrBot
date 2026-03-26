# ruff: noqa: E402
"""Provider 客户端 Core Bridge 集成测试。

测试覆盖 01_context_api.md 中 ctx.providers 的所有方法：
- list_all(): 列出所有 Provider
- get_using_chat(): 获取当前使用的聊天 Provider
"""
from __future__ import annotations

import pytest

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_providers_list_all(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    providers = await ctx.providers.list_all()

    # 默认有一个 chat-provider-a
    assert len(providers) == 1
    assert providers[0].id == "chat-provider-a"
    assert providers[0].model == "gpt-roundtrip"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_providers_get_using_chat(tmp_path, monkeypatch):
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    provider = await ctx.providers.get_using_chat()

    assert provider is not None
    assert provider.id == "chat-provider-a"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_providers_get_using_chat_with_umo_override(
    tmp_path, monkeypatch
):
    """当设置了 UMO 级别的 provider 时，get_using_chat 返回对应的 provider。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    # 创建第二个 provider
    await runtime.provider_manager.create_provider(
        {
            "id": "chat-provider-b",
            "type": "mock",
            "provider_type": "chat_completion",
            "model": "gpt-override",
        }
    )

    # 设置特定 UMO 的 provider
    await runtime.provider_manager.set_provider(
        provider_id="chat-provider-b",
        provider_type="chat_completion",
        umo="qq:private:user-123",
    )

    ctx = runtime.make_context("plugin-a")

    # 不带 UMO 时返回默认 provider
    default_provider = await ctx.providers.get_using_chat()
    assert default_provider.id == "chat-provider-a"

    # 带 UMO 时返回覆盖的 provider
    override_provider = await ctx.providers.get_using_chat(
        umo="qq:private:user-123"
    )
    assert override_provider.id == "chat-provider-b"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_providers_list_all_empty_when_no_providers(
    tmp_path, monkeypatch
):
    """当没有 provider 时返回空列表。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    # 删除所有 provider
    await runtime.provider_manager.delete_provider(provider_id="chat-provider-a")

    ctx = runtime.make_context("plugin-a")
    providers = await ctx.providers.list_all()

    assert len(providers) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_providers_get_using_chat_returns_none_when_no_provider(
    tmp_path, monkeypatch
):
    """当没有活跃 provider 时返回 None。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)

    # 删除所有 provider
    await runtime.provider_manager.delete_provider(provider_id="chat-provider-a")

    ctx = runtime.make_context("plugin-a")
    provider = await ctx.providers.get_using_chat()

    assert provider is None
