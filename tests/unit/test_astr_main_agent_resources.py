from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.astr_main_agent_resources import SendMessageToUserTool
from astrbot.core.platform.message_session import MessageSession


@pytest.mark.asyncio
async def test_send_message_to_user_prefers_event_session():
    """Regression: cron events should send to the bound session, not stale unified_msg_origin."""
    tool = SendMessageToUserTool()
    expected_session = MessageSession.from_str("wuju:GroupMessage:203014918")

    wrapper = MagicMock()
    wrapper.context = MagicMock()
    wrapper.context.event = MagicMock()
    wrapper.context.event.session = expected_session
    wrapper.context.event.unified_msg_origin = "wuju:GroupMessage:1087184344"
    wrapper.context.context = MagicMock()
    wrapper.context.context.send_message = AsyncMock()

    result = await tool.call(
        wrapper,
        messages=[{"type": "plain", "text": "hello"}],
    )

    wrapper.context.context.send_message.assert_awaited_once()
    sent_session = wrapper.context.context.send_message.await_args.args[0]
    assert str(sent_session) == str(expected_session)
    assert result == f"Message sent to session {expected_session}"
