"""Import smoke tests for chat and conversation route modules.

Verifies that all public classes and key standalone functions from
``chat.py`` and ``conversation.py`` can be imported without errors.
"""

# ---------------------------------------------------------------------------
# chat.py — ChatRoute, helper classes and standalone functions
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.chat import (
    BotMessageAccumulator,      # noqa: F401
    ChatRoute,                  # noqa: F401
    SSE_HEARTBEAT,              # noqa: F401
    _poll_webchat_stream_result,  # noqa: F401
    collect_plain_text_from_message_parts,  # noqa: F401
    extract_reasoning_from_message_parts,  # noqa: F401
    track_conversation,         # noqa: F401
)


def test_chat_route_class():
    assert ChatRoute is not None


def test_bot_message_accumulator_class():
    assert BotMessageAccumulator is not None


def test_sse_heartbeat_constant():
    assert SSE_HEARTBEAT == ": heartbeat\n\n"


def test_poll_webchat_stream_result_is_coroutine_function():
    import asyncio

    assert asyncio.iscoroutinefunction(_poll_webchat_stream_result)


def test_collect_plain_text_from_message_parts_is_callable():
    assert callable(collect_plain_text_from_message_parts)


def test_extract_reasoning_from_message_parts_is_callable():
    assert callable(extract_reasoning_from_message_parts)


def test_track_conversation_is_async_context_manager():
    import inspect

    assert inspect.isasyncgenfunction(track_conversation)


# ---------------------------------------------------------------------------
# conversation.py — ConversationRoute
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.conversation import (  # noqa: F401
    ConversationRoute,
)


def test_conversation_route_class():
    assert ConversationRoute is not None
