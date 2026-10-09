import pytest

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
@pytest.mark.parametrize(
    ("provider_id", "provider", "error_code", "error_params"),
    [
        (None, None, "noProvider", {}),
        ("missing", None, "providerNotFound", {"provider": "missing"}),
        ("invalid", "not a provider", "invalidProviderType", {"provider_type": "str"}),
    ],
)
async def test_llm_errors_preserve_localization_in_stream_and_history(
    provider_id, provider, error_code, error_params
):
    """Verify provider failures retain translation metadata through WebChat storage."""
    from unittest.mock import AsyncMock, MagicMock

    from astrbot.core.astr_main_agent import MainAgentBuildConfig, build_main_agent
    from astrbot.core.message.message_event_result import MessageChain
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
        InternalAgentSubStage,
    )
    from astrbot.dashboard.services.chat_service import (
        BotMessageAccumulator,
        build_bot_history_content,
    )

    event = _event("localized-error-request")
    if provider_id:
        event.set_extra("selected_provider", provider_id)
    context = MagicMock()
    context.get_provider_by_id.return_value = provider
    context.get_using_provider_async = AsyncMock(return_value=None)
    queue = webchat_queue_mgr.get_or_create_back_queue("localized-error-request")
    try:
        result = await build_main_agent(
            event=event,
            plugin_context=context,
            config=MainAgentBuildConfig(tool_call_timeout=60),
        )
        assert result is None
        fallback = event.get_extra("_llm_error_message")
        await InternalAgentSubStage._send_llm_error_message(None, event, fallback)
        payload = queue.get_nowait()
        assert payload["type"] == "error"
        assert payload["data"] == fallback
        assert payload["error_code"] == error_code
        assert payload["error_params"] == error_params

        accumulator = BotMessageAccumulator()
        accumulator.add_plain("Earlier output", chain_type=None, streaming=True)
        accumulator.add_plain(
            payload["data"],
            chain_type=None,
            streaming=False,
            error_code=payload["error_code"],
            error_params=payload["error_params"],
        )
        history = build_bot_history_content(accumulator.build_message_parts())
        assert history["message"] == [
            {"type": "plain", "text": "Earlier output"},
            {
                "type": "plain",
                "text": fallback,
                "error_code": error_code,
                "error_params": error_params,
            },
        ]
        await event.send(MessageChain().message("Custom error reply"))
        custom_reply = queue.get_nowait()
        assert custom_reply["type"] == "plain"
        assert "error_code" not in custom_reply
    finally:
        webchat_queue_mgr.remove_back_queue("localized-error-request")
