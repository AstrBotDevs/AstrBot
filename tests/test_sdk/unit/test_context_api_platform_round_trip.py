# ruff: noqa: E402
"""Platform 客户端 Core Bridge 集成测试。

测试覆盖 01_context_api.md 中 ctx.platform 的所有方法：
- send(): 发送文本消息
- send_image(): 发送图片消息
- send_chain(): 发送富消息链
- send_by_id(): 通过 ID 主动发送消息
- get_members(): 获取群组成员列表
"""
from __future__ import annotations

import pytest

from astrbot_sdk.message_components import Plain

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_platform_send_text(tmp_path, monkeypatch):
    """platform.send 发送文本消息。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 注册一个带有群组会话的请求上下文
    request_id = "plugin-a:req-1"
    runtime.register_group_request(
        request_id=request_id,
        session="qq:group:123456",
    )

    # 发送文本消息
    result = await ctx.platform.send("qq:group:123456", "Hello World")

    assert result is not None
    # 验证消息被发送
    assert len(runtime.star_context.sent_messages) == 1
    assert runtime.star_context.sent_messages[0]["text"] == "Hello World"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_platform_send_image(tmp_path, monkeypatch):
    """platform.send_image 发送图片消息。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    request_id = "plugin-a:req-2"
    runtime.register_group_request(
        request_id=request_id,
        session="qq:private:user-789",
    )

    result = await ctx.platform.send_image(
        "qq:private:user-789",
        "https://example.com/image.png"
    )

    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_platform_send_chain(tmp_path, monkeypatch):
    """platform.send_chain 发送富消息链。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    request_id = "plugin-a:req-3"
    runtime.register_group_request(
        request_id=request_id,
        session="qq:group:111222",
    )

    # 构建消息链
    chain = [Plain("Hello "), Plain("World")]

    result = await ctx.platform.send_chain("qq:group:111222", chain)

    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_platform_send_by_id(tmp_path, monkeypatch):
    """platform.send_by_id 主动向指定平台会话发送消息。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    result = await ctx.platform.send_by_id(
        platform_id="qq",
        session_id="user-456",
        content="主动发送的消息",
        message_type="private"
    )

    assert result is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_platform_get_members(tmp_path, monkeypatch):
    """platform.get_members 获取群组成员列表。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    request_id = "plugin-a:req-4"
    runtime.register_group_request(
        request_id=request_id,
        session="qq:group:999888",
        members=[
            {"user_id": "owner-1", "nickname": "Owner", "role": "owner"},
            {"user_id": "admin-1", "nickname": "Admin", "role": "admin"},
            {"user_id": "member-1", "nickname": "Member", "role": "member"},
        ]
    )

    members = await ctx.platform.get_members("qq:group:999888")

    assert len(members) == 3
    user_ids = {m["user_id"] for m in members}
    assert user_ids == {"owner-1", "admin-1", "member-1"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_platform_get_members_returns_empty_for_non_group(
    tmp_path, monkeypatch
):
    """非群组会话的 get_members 返回空列表。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 私聊会话没有成员
    members = await ctx.platform.get_members("qq:private:user-123")

    assert members == []
