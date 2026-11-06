"""Regression: empty streams must not fall through to after-sent cleanup.

Covers the streaming branch exit of ``RespondStage.process()``: when the
platform adapter reports a failed (empty) delivery, ``OnAfterMessageSentEvent``
must not be dispatched and the original result must be preserved. A successful
single-chunk stream serves as the control case.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.respond import stage as respond_module
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.utils.metrics import Metric


@pytest.mark.asyncio
@pytest.mark.parametrize("has_content", [False, True], ids=["empty", "delivered"])
async def test_after_sent_only_for_delivered_stream(monkeypatch, has_content):
    hook = AsyncMock(return_value=False)
    monkeypatch.setattr(respond_module, "call_event_hook", hook)
    monkeypatch.setattr(Metric, "upload", AsyncMock())

    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember(user_id="12345", nickname="Review")
    message.self_id = "review-bot"
    message.session_id = "review-session"
    message.message_id = "review-message"
    message.message = []
    message.message_str = ""
    message.raw_message = None
    bot = SimpleNamespace(send_private_msg=AsyncMock())
    event = AiocqhttpMessageEvent(
        "", message, PlatformMetadata("aiocqhttp", "Review", "review"),
        "review-session", bot,
    )

    async def stream():
        if has_content:
            yield MessageChain().message("Delivered control")

    result = MessageEventResult(
        result_content_type=ResultContentType.STREAMING_RESULT,
        async_stream=stream(),
    )
    event.set_result(result)
    config = {
        "platform_settings": {
            "reply_with_mention": False,
            "reply_with_quote": False,
            "segmented_reply": {
                "enable": False, "only_llm_result": False,
                "interval_method": "random", "log_base": 2,
            },
        },
        "provider_settings": {"unsupported_streaming_strategy": "buffered"},
    }
    stage = respond_module.RespondStage()
    await stage.initialize(PipelineContext(config, None, "review"))
    await stage.process(event)

    observed = {
        "bot_sends": bot.send_private_msg.await_count,
        "after_sent_calls": hook.await_count,
        "result_preserved": event.get_result() is result,
    }
    assert observed == {
        "bot_sends": int(has_content),
        "after_sent_calls": int(has_content),
        "result_preserved": not has_content,
    }
