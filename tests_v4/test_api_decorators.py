"""
Unit tests for API decorators and Star class.
"""

from __future__ import annotations

import asyncio

import pytest

from astrbot_sdk import Context, MessageEvent, Star
from astrbot_sdk.decorators import (
    get_handler_meta,
    on_command,
    on_event,
    on_message,
    on_schedule,
    require_admin,
)
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    MessageTrigger,
    ScheduleTrigger,
)


class TestOnCommandDecorator:
    """Tests for @on_command decorator."""

    def test_decorator_sets_handler_meta(self):
        """@on_command should set __astrbot_handler_meta__."""

        @on_command("hello")
        async def hello_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(hello_handler)
        assert meta is not None
        assert isinstance(meta.trigger, CommandTrigger)
        assert meta.trigger.command == "hello"

    def test_decorator_supports_aliases(self):
        """@on_command should support command aliases."""

        @on_command("hello", aliases=["hi", "hey"])
        async def hello_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(hello_handler)
        assert meta.trigger.aliases == ["hi", "hey"]

    def test_decorator_supports_description(self):
        """@on_command should support description."""

        @on_command("hello", description="Say hello")
        async def hello_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(hello_handler)
        assert meta.trigger.description == "Say hello"


class TestOnMessageDecorator:
    """Tests for @on_message decorator."""

    def test_decorator_sets_handler_meta(self):
        """@on_message should set __astrbot_handler_meta__."""

        @on_message()
        async def message_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(message_handler)
        assert meta is not None
        assert isinstance(meta.trigger, MessageTrigger)

    def test_decorator_supports_keywords(self):
        """@on_message should support keyword filtering."""

        @on_message(keywords=["hello", "hi"])
        async def keyword_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(keyword_handler)
        assert meta.trigger.keywords == ["hello", "hi"]

    def test_decorator_supports_regex(self):
        """@on_message should support regex filtering."""

        @on_message(regex=r"\d+")
        async def regex_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(regex_handler)
        assert meta.trigger.regex == r"\d+"


class TestOnEventDecorator:
    """Tests for @on_event decorator."""

    def test_decorator_sets_handler_meta(self):
        """@on_event should set __astrbot_handler_meta__."""

        @on_event("message_received")
        async def event_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(event_handler)
        assert meta is not None
        assert isinstance(meta.trigger, EventTrigger)
        assert meta.trigger.event_type == "message_received"


class TestOnScheduleDecorator:
    """Tests for @on_schedule decorator."""

    def test_decorator_sets_cron_trigger(self):
        """@on_schedule should create ScheduleTrigger with cron."""

        @on_schedule(cron="* * * * *")
        async def scheduled_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(scheduled_handler)
        assert meta is not None
        assert isinstance(meta.trigger, ScheduleTrigger)
        assert meta.trigger.cron == "* * * * *"

    def test_decorator_sets_interval_trigger(self):
        """@on_schedule should create ScheduleTrigger with interval."""

        @on_schedule(interval_seconds=60)
        async def interval_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(interval_handler)
        assert meta.trigger.interval_seconds == 60


class TestRequireAdminDecorator:
    """Tests for @require_admin decorator."""

    def test_decorator_sets_admin_permission(self):
        """@require_admin should set require_admin permission."""

        @require_admin
        async def admin_handler(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(admin_handler)
        assert meta.permissions.require_admin is True

    def test_can_combine_with_on_command(self):
        """@require_admin can be combined with @on_command."""

        @on_command("admin")
        @require_admin
        async def admin_cmd(event: MessageEvent, ctx: Context):
            pass

        meta = get_handler_meta(admin_cmd)
        assert isinstance(meta.trigger, CommandTrigger)
        assert meta.trigger.command == "admin"
        assert meta.permissions.require_admin is True


class TestStarClass:
    """Tests for Star base class."""

    def test_star_is_new_star_by_default(self):
        """Star subclasses should be recognized as new-style."""

        class MyPlugin(Star):
            pass

        assert MyPlugin.__astrbot_is_new_star__() is True

    def test_star_collects_handler_names_from_decorators(self):
        """Star should collect decorated method names in __handlers__."""

        class MyPlugin(Star):
            @on_command("hello")
            async def hello(self, event: MessageEvent, ctx: Context):
                pass

            @on_message()
            async def on_msg(self, event: MessageEvent, ctx: Context):
                pass

        assert "hello" in MyPlugin.__handlers__
        assert "on_msg" in MyPlugin.__handlers__

    @pytest.mark.asyncio
    async def test_star_on_error_calls_reply(self):
        """Star.on_error should call event.reply with error message."""
        replies = []

        class MyPlugin(Star):
            pass

        plugin = MyPlugin()

        # Create event with mock reply handler
        event = MessageEvent(text="test", session_id="s1")
        event.bind_reply_handler(lambda text: replies.append(text) or asyncio.sleep(0))

        # Create context (not used in default impl)
        ctx = None

        # on_error should call reply
        await plugin.on_error(RuntimeError("test error"), event, ctx)

        assert len(replies) == 1
        assert "问题" in replies[0]


class TestTriggerModels:
    """Tests for trigger model validation."""

    def test_command_trigger_validation(self):
        """CommandTrigger should validate command name."""
        trigger = CommandTrigger(command="hello")
        assert trigger.command == "hello"

    def test_message_trigger_optional_keywords(self):
        """MessageTrigger should have optional keywords."""
        trigger = MessageTrigger()
        assert trigger.keywords == []

        trigger_with_keywords = MessageTrigger(keywords=["a", "b"])
        assert trigger_with_keywords.keywords == ["a", "b"]

    def test_event_trigger_validation(self):
        """EventTrigger should store event type."""
        trigger = EventTrigger(event_type="custom_event")
        assert trigger.event_type == "custom_event"

    def test_schedule_trigger_requires_one_strategy(self):
        """ScheduleTrigger should require exactly one strategy."""
        with pytest.raises(ValueError):
            ScheduleTrigger()

        with pytest.raises(ValueError):
            ScheduleTrigger(cron="* * * * *", interval_seconds=10)

        trigger = ScheduleTrigger(interval_seconds=30)
        assert trigger.interval_seconds == 30
