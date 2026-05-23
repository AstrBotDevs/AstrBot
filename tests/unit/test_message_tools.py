"""Tests for send_message_to_user session handling."""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


sys.modules.setdefault(
    "python_ripgrep",
    SimpleNamespace(search=lambda *args, **kwargs: []),
)

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.platform.message_session import MessageSession
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
    """在 cron 场景中，current_session 就是 cron 任务的目标 session。"""
    tool = SendMessageToUserTool()
    cron_target_session = "feishu:GroupMessage:oc_cron_target"
    ctx = _make_context(current_session=cron_target_session)

    result = await tool.call(
        ctx,
        messages=[{"type": "plain", "text": "cron message"}],
        session="oc_cron_target",
    )
    assert "Message sent to session" in result
    call_args = ctx.context.context.send_message.call_args
    target_session = call_args[0][0]
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


@pytest.mark.asyncio
async def test_send_message_to_user_returns_error_for_missing_local_image_path():
    ctx = _make_context(current_session="aiocqhttp:FriendMessage:123456")

    async def _send_message(_session, _message_chain):
        raise AssertionError("send_message should not be called for a missing file")

    ctx.context.context.send_message = _send_message
    tool = SendMessageToUserTool()

    result = await tool.call(
        ctx,
        messages=[
            {
                "type": "image",
                "path": "/data/asset/images/record_store_vinyl.jpg",
            }
        ],
    )

    assert result.startswith("error: failed to build messages[0] component:")
    assert "No such file or directory" in result
    assert "/data/asset/images/record_store_vinyl.jpg" in result


@pytest.mark.asyncio
async def test_send_message_to_user_returns_error_when_send_message_raises():
    ctx = _make_context(current_session="aiocqhttp:FriendMessage:123456")

    async def _send_message(_session, _message_chain):
        raise FileNotFoundError(
            2,
            "No such file or directory",
            "/data/asset/images/record_store_vinyl.jpg",
        )

    ctx.context.context.send_message = _send_message
    tool = SendMessageToUserTool()

    result = await tool.call(
        ctx,
        session=MessageSession.from_str("aiocqhttp:FriendMessage:123456"),
        messages=[{"type": "plain", "text": "fallback please"}],
    )

    assert result.startswith("error:")
    assert "No such file or directory" in result
    assert "/data/asset/images/record_store_vinyl.jpg" in result
