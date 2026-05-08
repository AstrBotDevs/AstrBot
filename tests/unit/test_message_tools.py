"""Tests for send_message_to_user session handling."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.tools.message_tools import SendMessageToUserTool


def _make_context(
    current_session="feishu:GroupMessage:oc_xxx",
    role="admin",
    require_admin=True,
):
    """Build a minimal ContextWrapper for SendMessageToUserTool."""
    cfg = {"provider_settings": {"computer_use_require_admin": require_admin}}
    return SimpleNamespace(
        context=SimpleNamespace(
            event=SimpleNamespace(
                unified_msg_origin=current_session,
                role=role,
                get_sender_id=lambda: "user-1",
            ),
            context=SimpleNamespace(
                get_config=lambda umo: cfg,
                send_message=AsyncMock(),
            ),
        )
    )


@pytest.mark.asyncio
async def test_send_message_with_full_three_part_session():
    """LLM passes a complete three-part session string."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="feishu:GroupMessage:oc_aaa")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "hello"}],
        session="feishu:GroupMessage:oc_aaa",
    )
    assert "Message sent to session" in result


@pytest.mark.asyncio
async def test_send_message_with_partial_session_id_fallback():
    """LLM passes only session_id (no colons) — fallback to current_session's prefix."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="feishu:GroupMessage:oc_abc")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "hello"}],
        session="oc_abc",
    )
    assert "Message sent to session" in result
    # Verify the target session was reconstructed with current_session's platform/msg_type
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
    assert target_session.platform_id == "feishu"
    assert target_session.message_type.value == "GroupMessage"
    assert target_session.session_id == "oc_abc"


@pytest.mark.asyncio
async def test_send_message_defaults_to_current_session():
    """LLM does not pass session — uses current_session directly."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="feishu:GroupMessage:oc_xxx")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "hello"}],
    )
    assert "Message sent to session" in result
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
    assert str(target_session) == "feishu:GroupMessage:oc_xxx"


@pytest.mark.asyncio
async def test_send_message_partial_session_falls_back_to_current():
    """LLM passes session_id matching current_session's id — same session, just incomplete format."""
    tool = SendMessageToUserTool()
    ctx = _make_context(current_session="qq_official:GroupMessage:g123")
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "world"}],
        session="g123",
    )
    assert "Message sent to session" in result
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
    assert target_session.platform_id == "qq_official"
    assert target_session.message_type.value == "GroupMessage"
    assert target_session.session_id == "g123"


@pytest.mark.asyncio
async def test_cron_context_current_session_is_target_session():
    """在 cron 场景中，current_session 就是 cron 任务的目标 session。

    cron 是主动唤醒，没有用户消息触发，因此没有"正在聊天的 session"。
    event.unified_msg_origin 来自 CronMessageEvent.session，
    而 CronMessageEvent.session 来自 cron job payload.session，
    即用户在 cron 配置中填写的目标会话。
    """
    tool = SendMessageToUserTool()
    # cron 任务的目标 session（用户配置的完整三段式）
    cron_target_session = "feishu:GroupMessage:oc_cron_target"
    ctx = _make_context(current_session=cron_target_session)

    # LLM 在 cron 上下文中只传了 session_id 部分
    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "cron message"}],
        session="oc_cron_target",
    )
    assert "Message sent to session" in result
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
    # 补全后的 session 应与 cron 目标 session 完全一致
    assert str(target_session) == cron_target_session
    assert target_session.platform_id == "feishu"
    assert target_session.message_type.value == "GroupMessage"
    assert target_session.session_id == "oc_cron_target"


@pytest.mark.asyncio
async def test_send_message_empty_messages_returns_error():
    """Empty or missing messages returns error before session resolution."""
    tool = SendMessageToUserTool()
    ctx = _make_context()
    result = await tool.call(ctx, messages=[], session="oc_xxx")
    assert "error:" in result
    assert "messages" in result.lower()
