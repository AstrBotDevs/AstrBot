from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import webchat_queue_mgr


def _event(message_id: str) -> WebChatMessageEvent:
    """Create an isolated WebChat event for stream-status tests.

    Args:
        message_id: Request identifier used by the response queue.

    Returns:
        Configured WebChat event.
    """
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "webchat"
    message.session_id = "session-1"
    message.message_id = message_id
    message.sender = MessageMember("alice", "Alice")
    message.message = []
    message.message_str = "hello"
    return WebChatMessageEvent(
        "hello",
        message,
        PlatformMetadata(name="webchat", description="webchat", id="webchat"),
        "webchat!alice!session-1",
    )


@pytest.mark.asyncio
async def test_webchat_run_started_is_emitted_by_default():
    event = _event("default-request")
    queue = webchat_queue_mgr.get_or_create_back_queue("default-request")

    try:
        await event.send_typing()
        await event.send(None)

        assert await queue.get() == {
            "type": "run_started",
            "data": {"run_id": "default-request"},
            "streaming": False,
            "message_id": "default-request",
        }
        assert await queue.get() == {
            "type": "end",
            "data": "",
            "streaming": False,
            "message_id": "default-request",
        }
        assert queue.empty()
    finally:
        webchat_queue_mgr.remove_back_queue("default-request")


@pytest.mark.asyncio
async def test_webchat_follow_up_captured_is_emitted_by_default():
    event = _event("follow-up-request")
    queue = webchat_queue_mgr.get_or_create_back_queue("follow-up-request")

    try:
        event.set_extra(
            "_follow_up_captured",
            {"target_run_id": "original-run"},
        )
        await event.send(None)
        assert await queue.get() == {
            "type": "follow_up_captured",
            "data": {"target_run_id": "original-run"},
            "streaming": False,
            "message_id": "follow-up-request",
        }
        assert (await queue.get())["type"] == "end"
    finally:
        webchat_queue_mgr.remove_back_queue("follow-up-request")


@pytest.mark.asyncio
async def test_nonstream_reasoning_is_delivered_once_before_the_reply():
    event = _event("reasoning-request")
    config = deepcopy(DEFAULT_CONFIG)
    config["platform_settings"]["segmented_reply"].update(enable=True, interval="0,0")
    event.set_extra("enable_reasoning", True)
    event.set_extra("_llm_reasoning_content", "Thinking")
    event.set_result(
        MessageEventResult()
        .message("First。Second。")
        .set_result_content_type(ResultContentType.LLM_RESULT)
    )
    context = SimpleNamespace(
        astrbot_config=config,
        plugin_manager=SimpleNamespace(
            context=SimpleNamespace(
                get_using_tts_provider_async=AsyncMock(return_value=None),
                get_config=lambda **_: config,
            )
        ),
    )
    decorate = ResultDecorateStage()
    respond = RespondStage()
    await decorate.initialize(context)
    await respond.initialize(context)
    queue = webchat_queue_mgr.get_or_create_back_queue("reasoning-request")
    try:
        async for _ in decorate.process(event):
            pass
        await respond.process(event)
        frames = []
        while not queue.empty():
            frame = queue.get_nowait()
            frames.append((frame["chain_type"], frame["data"]))
        assert frames == [
            ("reasoning", "Thinking"),
            (None, "First。"),
            (None, "Second。"),
        ]
    finally:
        webchat_queue_mgr.remove_back_queue("reasoning-request")
