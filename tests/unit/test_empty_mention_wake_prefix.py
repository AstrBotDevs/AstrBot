from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.builtin_stars.astrbot.main as main_module
from astrbot.api.message_components import At, Plain


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_wake_prefix", "messages", "should_request_llm"),
    [
        ("chat", [At(qq="bot")], False),
        ("/chat", [At(qq="bot")], False),
        ("chat", [Plain(text="/")], False),
        ("", [At(qq="bot")], True),
        ("/", [At(qq="bot")], True),
    ],
)
async def test_empty_mention_reply_respects_provider_wake_prefix(
    monkeypatch,
    provider_wake_prefix,
    messages,
    should_request_llm,
):
    """Only request an immediate LLM reply when no extra prefix is required."""

    def skip_waiting(_timeout):
        def decorator(_callback):
            async def wait(*_args, **_kwargs):
                raise TimeoutError

            return wait

        return decorator

    monkeypatch.setattr(main_module, "session_waiter", skip_waiting)

    conversation_manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="conversation-id"),
        get_conversation=AsyncMock(return_value=None),
    )
    main = main_module.Main.__new__(main_module.Main)
    main.context = MagicMock()
    main.context.conversation_manager = conversation_manager
    main.context.get_config.return_value = {
        "wake_prefix": ["/"],
        "provider_settings": {"wake_prefix": provider_wake_prefix},
        "platform_settings": {
            "empty_mention_waiting": True,
            "empty_mention_waiting_need_reply": True,
        },
    }

    event = MagicMock()
    event.unified_msg_origin = "aiocqhttp:GroupMessage:group"
    event.get_messages.return_value = messages
    event.get_self_id.return_value = "bot"
    event.get_platform_id.return_value = "aiocqhttp"
    llm_request = object()
    event.request_llm.return_value = llm_request

    results = [item async for item in main.handle_empty_mention(event)]

    assert results == ([llm_request] if should_request_llm else [])
    if should_request_llm:
        event.request_llm.assert_called_once()
        conversation_manager.get_curr_conversation_id.assert_awaited_once()
    else:
        event.request_llm.assert_not_called()
        conversation_manager.get_curr_conversation_id.assert_not_awaited()
