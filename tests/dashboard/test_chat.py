"""Import smoke tests for the dashboard chat route module.

Verifies that the main class and its key method signatures from
``chat.py`` can be imported without errors.
"""

import inspect

from astrbot.dashboard.routes.chat import (
    BotMessageAccumulator,
    ChatRoute,
    SSE_HEARTBEAT,
    _sanitize_upload_filename,
    collect_plain_text_from_message_parts,
    extract_reasoning_from_message_parts,
    track_conversation,
)


class TestChatRouteClass:
    def test_class_exists(self):
        assert ChatRoute is not None

    def test_has_sse_heartbeat(self):
        assert SSE_HEARTBEAT == ": heartbeat\n\n"

    def test_init_method_signature(self):
        sig = inspect.signature(ChatRoute.__init__)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "context" in params
        assert "db" in params
        assert "core_lifecycle" in params

    def test_chat_method_is_async(self):
        assert inspect.iscoroutinefunction(ChatRoute.chat)

    def test_chat_method_signature(self):
        sig = inspect.signature(ChatRoute.chat)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "post_data" in params

    def test_new_session_method_is_async(self):
        assert inspect.iscoroutinefunction(ChatRoute.new_session)

    def test_new_session_method_signature(self):
        sig = inspect.signature(ChatRoute.new_session)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_get_session_method_is_async(self):
        assert inspect.iscoroutinefunction(ChatRoute.get_session)

    def test_get_session_method_signature(self):
        sig = inspect.signature(ChatRoute.get_session)
        params = list(sig.parameters.keys())
        assert "self" in params


class TestBotMessageAccumulatorClass:
    def test_class_exists(self):
        assert BotMessageAccumulator is not None

    def test_has_content_method(self):
        assert callable(BotMessageAccumulator.has_content)

    def test_add_plain_method(self):
        sig = inspect.signature(BotMessageAccumulator.add_plain)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "result_text" in params
        assert "chain_type" in params
        assert "streaming" in params

    def test_build_message_parts_method(self):
        sig = inspect.signature(BotMessageAccumulator.build_message_parts)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "include_pending_tool_calls" in params


class TestStandaloneFunctions:
    def test_track_conversation_is_async_gen(self):
        assert inspect.isasyncgenfunction(track_conversation)

    def test_collect_plain_text_from_message_parts_is_callable(self):
        assert callable(collect_plain_text_from_message_parts)

    def test_extract_reasoning_from_message_parts_is_callable(self):
        assert callable(extract_reasoning_from_message_parts)

    def test_sanitize_upload_filename_is_callable(self):
        assert callable(_sanitize_upload_filename)
