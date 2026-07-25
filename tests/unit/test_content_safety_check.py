from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.message.components import Plain, Reply
from astrbot.core.pipeline.content_safety_check.stage import ContentSafetyCheckStage


@pytest.mark.asyncio
async def test_content_safety_checks_inbound_reply_text_once() -> None:
    event = SimpleNamespace(
        is_at_or_wake_command=False,
        get_message_str=lambda: "current message",
        get_messages=lambda: [Reply(id="1", message_str="quoted message")],
        stop_event=Mock(),
    )
    stage = ContentSafetyCheckStage()
    stage.strategy_selector = SimpleNamespace(check=AsyncMock(return_value=(True, "")))

    async for _ in stage.process(event):
        pass

    stage.strategy_selector.check.assert_awaited_once_with(
        "current message\nquoted message"
    )


@pytest.mark.asyncio
async def test_content_safety_does_not_include_quotes_for_result_checks() -> None:
    event = SimpleNamespace(
        is_at_or_wake_command=False,
        get_message_str=lambda: "current message",
        get_messages=lambda: [Reply(id="1", chain=[Plain("quoted message")])],
        stop_event=Mock(),
    )
    stage = ContentSafetyCheckStage()
    stage.strategy_selector = SimpleNamespace(check=AsyncMock(return_value=(True, "")))

    async for _ in stage.process(event, check_text="model response"):
        pass

    stage.strategy_selector.check.assert_awaited_once_with("model response")
