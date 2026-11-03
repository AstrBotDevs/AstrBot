from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
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
@pytest.mark.parametrize("segmented", [False, True])
@pytest.mark.parametrize(
    ("configured", "override", "expected"),
    [
        (False, None, False),
        (True, None, True),
        (False, True, True),
        (True, False, False),
    ],
)
async def test_nonstream_reasoning_keeps_its_type(
    segmented, configured, override, expected
):
    event = _event("reasoning-request")
    queue = webchat_queue_mgr.get_or_create_back_queue("reasoning-request")
    config = deepcopy(DEFAULT_CONFIG)
    config["provider_settings"]["display_reasoning_text"] = configured
    config["platform_settings"]["segmented_reply"].update(
        enable=segmented, split_mode="regex", regex=r"[^。]+。", content_cleanup_rule=""
    )
    config["t2i"] = False
    config["provider_tts_settings"]["enable"] = False
    stage = ResultDecorateStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=config,
            plugin_manager=SimpleNamespace(
                context=SimpleNamespace(
                    get_using_tts_provider_async=AsyncMock(return_value=None)
                )
            ),
        )
    )
    reasoning = "A complete thought. Another sentence."
    event.set_extra("_llm_reasoning_content", reasoning)
    if override is not None:
        event.set_extra("enable_reasoning", override)
    result = MessageEventResult(
        chain=[Plain("First。Second。")],
        result_content_type=ResultContentType.LLM_RESULT,
    )
    event.set_result(result)
    try:
        async for _ in stage.process(event):
            pass
        assert "".join(comp.text for comp in result.chain) == "First。Second。"
        if segmented:
            for component in result.chain:
                await event.send(result.derive([component]))
        else:
            await event.send(result)
        await event.send(None)
        payloads = []
        while not queue.empty():
            payloads.append(queue.get_nowait())
        thoughts = [p for p in payloads if p.get("chain_type") == "reasoning"]
        assert len(thoughts) == int(expected)
        if expected:
            assert payloads[0] == {
                "type": "plain",
                "data": reasoning,
                "streaming": False,
                "chain_type": "reasoning",
                "message_id": "reasoning-request",
            }
        body = [
            p["data"]
            for p in payloads
            if p["type"] == "plain" and p.get("chain_type") != "reasoning"
        ]
        assert body == (["First。", "Second。"] if segmented else ["First。Second。"])
        assert payloads[-1]["type"] == "end"
    finally:
        webchat_queue_mgr.remove_back_queue("reasoning-request")
