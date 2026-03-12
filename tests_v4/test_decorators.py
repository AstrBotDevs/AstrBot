"""
Tests for decorators.py - Handler decorator infrastructure.
"""

from __future__ import annotations

import pytest

from astrbot_sdk.decorators import (
    get_capability_meta,
    HANDLER_META_ATTR,
    HandlerMeta,
    get_handler_meta,
    on_command,
    on_event,
    on_message,
    on_schedule,
    provide_capability,
    require_admin,
)
from astrbot_sdk.protocol.descriptors import (
    CommandTrigger,
    EventTrigger,
    MessageTrigger,
    Permissions,
    ScheduleTrigger,
)


class TestHandlerMeta:
    """Tests for HandlerMeta dataclass."""

    def test_default_values(self):
        """HandlerMeta should have default values."""
        meta = HandlerMeta()
        assert meta.trigger is None
        assert meta.priority == 0
        assert isinstance(meta.permissions, Permissions)

    def test_trigger_assignment(self):
        """HandlerMeta should accept trigger assignment."""
        trigger = CommandTrigger(command="test")
        meta = HandlerMeta(trigger=trigger)
        assert meta.trigger is trigger

    def test_priority_assignment(self):
        """HandlerMeta should accept priority assignment."""
        meta = HandlerMeta(priority=10)
        assert meta.priority == 10

    def test_permissions_assignment(self):
        """HandlerMeta should accept permissions assignment."""
        permissions = Permissions(require_admin=True)
        meta = HandlerMeta(permissions=permissions)
        assert meta.permissions.require_admin is True


class TestGetHandlerMeta:
    """Tests for get_handler_meta function."""

    def test_returns_none_for_undecorated_function(self):
        """get_handler_meta should return None for undecorated functions."""

        async def plain_function():
            pass

        assert get_handler_meta(plain_function) is None

    def test_returns_meta_for_decorated_function(self):
        """get_handler_meta should return meta for decorated functions."""

        @on_command("test")
        async def decorated():
            pass

        meta = get_handler_meta(decorated)
        assert meta is not None
        assert isinstance(meta, HandlerMeta)


class TestOnCommandDecorator:
    """Tests for @on_command decorator."""

    def test_sets_handler_meta_attribute(self):
        """@on_command should set __astrbot_handler_meta__ attribute."""

        @on_command("hello")
        async def handler():
            pass

        assert hasattr(handler, HANDLER_META_ATTR)

    def test_creates_command_trigger(self):
        """@on_command should create CommandTrigger."""

        @on_command("hello")
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert isinstance(meta.trigger, CommandTrigger)
        assert meta.trigger.command == "hello"

    def test_supports_aliases(self):
        """@on_command should store aliases."""

        @on_command("hello", aliases=["hi", "hey"])
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.trigger.aliases == ["hi", "hey"]

    def test_supports_description(self):
        """@on_command should store description."""

        @on_command("hello", description="Say hello")
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.trigger.description == "Say hello"

    def test_default_empty_aliases(self):
        """@on_command should default to empty aliases."""

        @on_command("test")
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.trigger.aliases == []

    def test_preserves_function(self):
        """@on_command should preserve the original function."""

        @on_command("test")
        async def handler():
            return "result"

        assert handler.__name__ == "handler"


class TestOnMessageDecorator:
    """Tests for @on_message decorator."""

    def test_creates_message_trigger(self):
        """@on_message should create MessageTrigger."""

        @on_message()
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert isinstance(meta.trigger, MessageTrigger)

    def test_supports_regex(self):
        """@on_message should store regex pattern."""

        @on_message(regex=r"\d+")
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.trigger.regex == r"\d+"

    def test_supports_keywords(self):
        """@on_message should store keywords."""

        @on_message(keywords=["hello", "hi"])
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.trigger.keywords == ["hello", "hi"]

    def test_supports_platforms(self):
        """@on_message should store platforms."""

        @on_message(platforms=["telegram", "discord"])
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.trigger.platforms == ["telegram", "discord"]

    def test_defaults_empty_lists(self):
        """@on_message should default to empty lists."""

        @on_message()
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.trigger.keywords == []
        assert meta.trigger.platforms == []


class TestOnEventDecorator:
    """Tests for @on_event decorator."""

    def test_creates_event_trigger(self):
        """@on_event should create EventTrigger."""

        @on_event("message_received")
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert isinstance(meta.trigger, EventTrigger)
        assert meta.trigger.event_type == "message_received"

    def test_various_event_types(self):
        """@on_event should handle various event types."""

        event_types = ["message_received", "user_joined", "custom_event"]

        for event_type in event_types:

            @on_event(event_type)
            async def handler():
                pass

            meta = get_handler_meta(handler)
            assert meta.trigger.event_type == event_type


class TestOnScheduleDecorator:
    """Tests for @on_schedule decorator."""

    def test_creates_cron_trigger(self):
        """@on_schedule with cron should create ScheduleTrigger."""

        @on_schedule(cron="* * * * *")
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert isinstance(meta.trigger, ScheduleTrigger)
        assert meta.trigger.cron == "* * * * *"

    def test_creates_interval_trigger(self):
        """@on_schedule with interval should create ScheduleTrigger."""

        @on_schedule(interval_seconds=60)
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.trigger.interval_seconds == 60


class TestRequireAdminDecorator:
    """Tests for @require_admin decorator."""

    def test_sets_require_admin_permission(self):
        """@require_admin should set require_admin in permissions."""

        @require_admin
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.permissions.require_admin is True


class TestProvideCapabilityDecorator:
    """Tests for @provide_capability decorator."""

    def test_sets_capability_meta(self):
        """@provide_capability should attach capability descriptor metadata."""

        @provide_capability(
            "demo.echo",
            description="Echo text",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )
        async def echo(payload):
            return payload

        meta = get_capability_meta(echo)
        assert meta is not None
        assert meta.descriptor.name == "demo.echo"

    def test_rejects_reserved_namespaces(self):
        """@provide_capability should reject framework-reserved prefixes."""
        for name in ("handler.echo", "system.echo", "internal.echo"):
            with pytest.raises(ValueError, match=name):

                @provide_capability(
                    name,
                    description="reserved",
                )
                async def reserved(payload):
                    return payload

    def test_can_combine_with_other_decorators(self):
        """@require_admin can be combined with other decorators."""

        @on_command("admin")
        @require_admin
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert isinstance(meta.trigger, CommandTrigger)
        assert meta.trigger.command == "admin"
        assert meta.permissions.require_admin is True

    def test_order_does_not_matter_for_permissions(self):
        """Decorator order should not affect permissions."""

        @require_admin
        @on_command("admin")
        async def handler1():
            pass

        @on_command("admin")
        @require_admin
        async def handler2():
            pass

        meta1 = get_handler_meta(handler1)
        meta2 = get_handler_meta(handler2)

        assert meta1.permissions.require_admin is True
        assert meta2.permissions.require_admin is True


class TestDecoratorChaining:
    """Tests for chaining multiple decorators."""

    def test_multiple_decorators_share_meta(self):
        """Multiple decorators should share the same meta object."""

        @on_command("test")
        @require_admin
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert isinstance(meta.trigger, CommandTrigger)
        assert meta.permissions.require_admin is True

    def test_last_trigger_wins(self):
        """Last trigger decorator should override previous ones."""

        # Decorators are applied bottom-up, so on_message wins
        @on_message()
        @on_command("override")
        async def handler():
            pass

        meta = get_handler_meta(handler)
        # on_message is applied last (outermost), so it wins
        assert isinstance(meta.trigger, MessageTrigger)

    def test_permissions_accumulate(self):
        """Permissions should accumulate across decorators."""

        @require_admin
        @on_command("test")
        async def handler():
            pass

        meta = get_handler_meta(handler)
        assert meta.permissions.require_admin is True
