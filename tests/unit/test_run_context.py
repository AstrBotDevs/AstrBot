"""Unit tests for astrbot.core.agent.run_context: ContextWrapper."""

from __future__ import annotations

import pytest

from astrbot.core.agent.run_context import ContextWrapper, NoContext
from astrbot.core.agent.message import Message


class TestContextWrapper:
    """ContextWrapper construction and default values."""

    def test_default_messages_is_empty_list(self):
        """ContextWrapper starts with an empty messages list."""
        ctx = ContextWrapper(context="test")
        assert ctx.messages == []

    def test_default_tool_call_timeout(self):
        """Default tool_call_timeout is 120 seconds."""
        ctx = ContextWrapper(context="test")
        assert ctx.tool_call_timeout == 120

    def test_context_string(self):
        """context holds a string value."""
        ctx = ContextWrapper(context="hello_world")
        assert ctx.context == "hello_world"

    def test_context_integer(self):
        """context holds an integer value."""
        ctx = ContextWrapper(context=42)
        assert ctx.context == 42

    def test_context_dict(self):
        """context holds a dict value."""
        data = {"key": "value", "num": 1}
        ctx = ContextWrapper(context=data)
        assert ctx.context == data

    def test_context_none(self):
        """context holds None."""
        ctx = ContextWrapper(context=None)
        assert ctx.context is None

    def test_messages_can_be_appended(self):
        """messages list supports appending Message objects."""
        ctx = ContextWrapper(context="test")
        msg = Message(role="user", content="hi")
        ctx.messages.append(msg)
        assert len(ctx.messages) == 1
        assert ctx.messages[0].content == "hi"

    def test_messages_can_be_replaced(self):
        """messages field can be replaced with a new list."""
        msgs = [Message(role="user", content="a"), Message(role="assistant", content="b")]
        ctx = ContextWrapper(context="test", messages=msgs)
        assert len(ctx.messages) == 2

    def test_custom_tool_call_timeout(self):
        """tool_call_timeout can be customized."""
        ctx = ContextWrapper(context="test", tool_call_timeout=30)
        assert ctx.tool_call_timeout == 30

    def test_generic_type_parameter(self):
        """ContextWrapper is generic; it accepts a type parameter."""
        ctx: ContextWrapper[str] = ContextWrapper(context="typed")
        assert ctx.context == "typed"


class TestNoContext:
    """NoContext is a ContextWrapper[None] singleton-like pattern."""

    def test_no_context_is_contextwrapper(self):
        """NoContext is an instance of ContextWrapper."""
        nc = NoContext()
        assert isinstance(nc, ContextWrapper)

    def test_no_context_context_is_none(self):
        """NoContext always carries context=None."""
        nc = NoContext()
        assert nc.context is None

    def test_no_context_messages_empty(self):
        """NoContext starts with empty messages."""
        nc = NoContext()
        assert nc.messages == []

    def test_no_context_default_timeout(self):
        """NoContext has the default 120s timeout."""
        nc = NoContext()
        assert nc.tool_call_timeout == 120
