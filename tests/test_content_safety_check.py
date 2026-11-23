from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.message.components import Plain, Reply
from astrbot.core.pipeline.content_safety_check.stage import ContentSafetyCheckStage
from astrbot.core.pipeline.content_safety_check.strategies.strategy import (
    StrategySelector,
)


@pytest.mark.asyncio
async def test_content_safety_checks_combined_message_text_once():
    event = SimpleNamespace(
        is_at_or_wake_command=False,
        get_message_str=lambda: "current message",
        get_messages=lambda: [Reply(id="1", message_str="quoted message")],
        stop_event=Mock(),
        send=AsyncMock(),
    )
    stage = ContentSafetyCheckStage()
    stage.strategy_selector = SimpleNamespace(check=Mock(return_value=(True, "")))

    assert await stage.process(event) is None

    stage.strategy_selector.check.assert_called_once_with(
        "current message\nquoted message"
    )
    event.stop_event.assert_not_called()
    event.send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "keyword", "check_text", "expected_stopped"),
    [
        (
            Reply(id="1", message_str="引用中包含淀粉砖"),
            "淀粉砖",
            None,
            True,
        ),
        (
            Reply(id="1", message_str="", chain=[Plain("引用中包含淀粉砖")]),
            "淀粉砖",
            None,
            True,
        ),
        (
            Reply(id="1", message_str="引用中包含淀粉砖"),
            "^你说呢\n引用中包含淀粉砖$",
            None,
            True,
        ),
        (
            Reply(id="1", message_str="引用中包含淀粉砖"),
            "淀粉砖",
            "",
            False,
        ),
    ],
)
async def test_content_safety_checks_quoted_text_only_for_inbound_messages(
    reply: Reply,
    keyword: str,
    check_text: str | None,
    expected_stopped: bool,
):
    stopped = False

    def stop_event() -> None:
        nonlocal stopped
        stopped = True

    event = SimpleNamespace(
        is_at_or_wake_command=False,
        get_message_str=lambda: "你说呢",
        get_messages=lambda: [reply],
        stop_event=stop_event,
        send=AsyncMock(),
    )
    stage = ContentSafetyCheckStage()
    stage.strategy_selector = StrategySelector(
        {
            "internal_keywords": {
                "enable": True,
                "extra_keywords": [keyword],
            },
            "baidu_aip": {"enable": False},
        }
    )

    assert await stage.process(event, check_text=check_text) is None

    assert stopped is expected_stopped
    event.send.assert_not_awaited()
