"""
Tests for protocol/descriptors.py - Descriptor models.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from astrbot_sdk.protocol.descriptors import (
    BUILTIN_CAPABILITY_SCHEMAS,
    CapabilityDescriptor,
    CommandTrigger,
    DB_LIST_INPUT_SCHEMA,
    EventTrigger,
    HandlerDescriptor,
    LLM_CHAT_INPUT_SCHEMA,
    MessageTrigger,
    Permissions,
    RESERVED_CAPABILITY_PREFIXES,
    ScheduleTrigger,
)


class TestPermissions:
    """Tests for Permissions model."""

    def test_default_values(self):
        """Permissions should have default values."""
        perms = Permissions()
        assert perms.require_admin is False
        assert perms.level == 0

    def test_custom_values(self):
        """Permissions should accept custom values."""
        perms = Permissions(require_admin=True, level=5)
        assert perms.require_admin is True
        assert perms.level == 5

    def test_model_dump(self):
        """Permissions should serialize correctly."""
        perms = Permissions(require_admin=True, level=10)
        data = perms.model_dump()
        assert data == {"require_admin": True, "level": 10}

    def test_extra_fields_forbidden(self):
        """Permissions should forbid extra fields."""
        with pytest.raises(ValidationError):
            Permissions(require_admin=True, unknown_field="value")


class TestCommandTrigger:
    """Tests for CommandTrigger model."""

    def test_required_command(self):
        """CommandTrigger requires command field."""
        trigger = CommandTrigger(command="hello")
        assert trigger.type == "command"
        assert trigger.command == "hello"
        assert trigger.aliases == []
        assert trigger.description is None

    def test_with_aliases_and_description(self):
        """CommandTrigger should accept aliases and description."""
        trigger = CommandTrigger(
            command="hello",
            aliases=["hi", "hey"],
            description="Say hello",
        )
        assert trigger.command == "hello"
        assert trigger.aliases == ["hi", "hey"]
        assert trigger.description == "Say hello"

    def test_type_literal(self):
        """CommandTrigger type should always be 'command'."""
        trigger = CommandTrigger(command="test")
        assert trigger.type == "command"

    def test_extra_fields_forbidden(self):
        """CommandTrigger should forbid extra fields."""
        with pytest.raises(ValidationError):
            CommandTrigger(command="test", extra="field")


class TestMessageTrigger:
    """Tests for MessageTrigger model."""

    def test_default_values(self):
        """MessageTrigger should have default values."""
        trigger = MessageTrigger()
        assert trigger.type == "message"
        assert trigger.regex is None
        assert trigger.keywords == []
        assert trigger.platforms == []

    def test_with_regex(self):
        """MessageTrigger should accept regex pattern."""
        trigger = MessageTrigger(regex=r"^hello.*$")
        assert trigger.regex == r"^hello.*$"

    def test_with_keywords(self):
        """MessageTrigger should accept keywords."""
        trigger = MessageTrigger(keywords=["hello", "hi"])
        assert trigger.keywords == ["hello", "hi"]

    def test_with_platforms(self):
        """MessageTrigger should accept platforms."""
        trigger = MessageTrigger(platforms=["wechat", "qq"])
        assert trigger.platforms == ["wechat", "qq"]

    def test_with_all_fields(self):
        """MessageTrigger should accept all fields."""
        trigger = MessageTrigger(
            regex=r"test",
            keywords=["keyword"],
            platforms=["platform"],
        )
        assert trigger.regex == "test"
        assert trigger.keywords == ["keyword"]
        assert trigger.platforms == ["platform"]


class TestEventTrigger:
    """Tests for EventTrigger model."""

    def test_required_event_type(self):
        """EventTrigger requires event_type field."""
        trigger = EventTrigger(event_type="message")
        assert trigger.type == "event"
        assert trigger.event_type == "message"

    def test_numeric_event_type(self):
        """EventTrigger should accept numeric string event_type."""
        trigger = EventTrigger(event_type="3")
        assert trigger.event_type == "3"

    def test_type_literal(self):
        """EventTrigger type should always be 'event'."""
        trigger = EventTrigger(event_type="custom")
        assert trigger.type == "event"


class TestScheduleTrigger:
    """Tests for ScheduleTrigger model."""

    def test_with_cron(self):
        """ScheduleTrigger should accept cron expression."""
        trigger = ScheduleTrigger(cron="0 9 * * *")
        assert trigger.type == "schedule"
        assert trigger.cron == "0 9 * * *"
        assert trigger.interval_seconds is None

    def test_with_interval_seconds(self):
        """ScheduleTrigger should accept interval_seconds."""
        trigger = ScheduleTrigger(interval_seconds=60)
        assert trigger.interval_seconds == 60
        assert trigger.cron is None

    def test_accepts_schedule_alias(self):
        """ScheduleTrigger should accept legacy schedule alias for cron."""
        trigger = ScheduleTrigger(schedule="0 */5 * * * *")
        assert trigger.cron == "0 */5 * * * *"
        assert trigger.schedule == "0 */5 * * * *"

    def test_requires_exactly_one_strategy(self):
        """ScheduleTrigger must have exactly one of cron or interval_seconds."""
        # Neither provided should raise
        with pytest.raises(ValidationError) as exc_info:
            ScheduleTrigger()
        assert "必须且只能有一个非 null" in str(exc_info.value)

        # Both provided should raise
        with pytest.raises(ValidationError) as exc_info:
            ScheduleTrigger(cron="* * * * *", interval_seconds=10)
        assert "必须且只能有一个非 null" in str(exc_info.value)

    def test_valid_cron_expressions(self):
        """ScheduleTrigger should accept various cron expressions."""
        trigger1 = ScheduleTrigger(cron="*/5 * * * *")
        assert trigger1.cron == "*/5 * * * *"

        trigger2 = ScheduleTrigger(cron="0 0 1 1 *")
        assert trigger2.cron == "0 0 1 1 *"

    def test_valid_intervals(self):
        """ScheduleTrigger should accept various intervals."""
        trigger1 = ScheduleTrigger(interval_seconds=30)
        assert trigger1.interval_seconds == 30

        trigger2 = ScheduleTrigger(interval_seconds=3600)
        assert trigger2.interval_seconds == 3600


class TestHandlerDescriptor:
    """Tests for HandlerDescriptor model."""

    def test_required_id_and_trigger(self):
        """HandlerDescriptor requires id and trigger."""
        trigger = CommandTrigger(command="hello")
        handler = HandlerDescriptor(id="test.handler", trigger=trigger)
        assert handler.id == "test.handler"
        assert handler.trigger == trigger
        assert handler.priority == 0
        assert handler.permissions.require_admin is False

    def test_with_priority_and_permissions(self):
        """HandlerDescriptor should accept priority and permissions."""
        trigger = CommandTrigger(command="admin")
        perms = Permissions(require_admin=True, level=5)
        handler = HandlerDescriptor(
            id="admin.handler",
            trigger=trigger,
            priority=10,
            permissions=perms,
        )
        assert handler.priority == 10
        assert handler.permissions.require_admin is True
        assert handler.permissions.level == 5

    def test_with_event_trigger(self):
        """HandlerDescriptor should work with EventTrigger."""
        trigger = EventTrigger(event_type="message")
        handler = HandlerDescriptor(id="event.handler", trigger=trigger)
        assert handler.trigger.type == "event"
        assert handler.trigger.event_type == "message"

    def test_with_schedule_trigger(self):
        """HandlerDescriptor should work with ScheduleTrigger."""
        trigger = ScheduleTrigger(cron="0 9 * * *")
        handler = HandlerDescriptor(id="scheduled.handler", trigger=trigger)
        assert handler.trigger.type == "schedule"
        assert handler.trigger.cron == "0 9 * * *"

    def test_model_dump(self):
        """HandlerDescriptor should serialize correctly."""
        trigger = CommandTrigger(command="test", aliases=["t"])
        perms = Permissions(require_admin=True, level=5)
        handler = HandlerDescriptor(
            id="test.handler",
            trigger=trigger,
            priority=10,
            permissions=perms,
        )
        data = handler.model_dump()
        assert data["id"] == "test.handler"
        assert data["priority"] == 10
        assert data["trigger"]["type"] == "command"
        assert data["trigger"]["command"] == "test"
        assert data["permissions"]["require_admin"] is True

    def test_extra_fields_forbidden(self):
        """HandlerDescriptor should forbid extra fields."""
        trigger = CommandTrigger(command="test")
        with pytest.raises(ValidationError):
            HandlerDescriptor(id="test", trigger=trigger, extra="field")


class TestCapabilityDescriptor:
    """Tests for CapabilityDescriptor model."""

    def test_required_name_and_description(self):
        """CapabilityDescriptor requires name and description."""
        cap = CapabilityDescriptor(name="custom.chat", description="Chat with LLM")
        assert cap.name == "custom.chat"
        assert cap.description == "Chat with LLM"
        assert cap.input_schema is None
        assert cap.output_schema is None
        assert cap.supports_stream is False
        assert cap.cancelable is False

    def test_builtin_capability_requires_schemas(self):
        """Built-in capabilities should enforce schema governance."""
        with pytest.raises(ValidationError, match="必须同时提供"):
            CapabilityDescriptor(name="llm.chat", description="missing schemas")

    def test_builtin_capability_schema_registry_contains_required_entries(self):
        """Built-in schema registry should cover documented core capabilities."""
        assert "llm.chat" in BUILTIN_CAPABILITY_SCHEMAS
        assert "db.list" in BUILTIN_CAPABILITY_SCHEMAS
        assert LLM_CHAT_INPUT_SCHEMA["required"] == ["prompt"]
        assert (
            DB_LIST_INPUT_SCHEMA["properties"]["prefix"]["anyOf"][1]["type"] == "null"
        )

    def test_reserved_capability_prefixes_are_protocol_constants(self):
        """Reserved namespace prefixes should live in protocol descriptors."""
        assert RESERVED_CAPABILITY_PREFIXES == ("handler.", "system.", "internal.")

    def test_with_schemas(self):
        """CapabilityDescriptor should accept input/output schemas."""
        cap = CapabilityDescriptor(
            name="db.query",
            description="Query database",
            input_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
            output_schema={"type": "array"},
        )
        assert cap.input_schema["type"] == "object"
        assert cap.output_schema["type"] == "array"

    def test_with_stream_and_cancelable(self):
        """CapabilityDescriptor should accept stream and cancelable flags."""
        cap = CapabilityDescriptor(
            name="llm.stream",
            description="Stream chat",
            supports_stream=True,
            cancelable=True,
        )
        assert cap.supports_stream is True
        assert cap.cancelable is True

    def test_model_dump(self):
        """CapabilityDescriptor should serialize correctly."""
        cap = CapabilityDescriptor(
            name="test.cap",
            description="Test capability",
            supports_stream=True,
        )
        data = cap.model_dump()
        assert data["name"] == "test.cap"
        assert data["description"] == "Test capability"
        assert data["supports_stream"] is True

    def test_extra_fields_forbidden(self):
        """CapabilityDescriptor should forbid extra fields."""
        with pytest.raises(ValidationError):
            CapabilityDescriptor(
                name="test",
                description="Test",
                extra="field",
            )


class TestTriggerDiscriminator:
    """Tests for Trigger type discriminator."""

    def test_command_trigger_discrimination(self):
        """CommandTrigger should be correctly discriminated."""
        handler = HandlerDescriptor(
            id="cmd.handler",
            trigger={"type": "command", "command": "test"},
        )
        assert isinstance(handler.trigger, CommandTrigger)
        assert handler.trigger.command == "test"

    def test_message_trigger_discrimination(self):
        """MessageTrigger should be correctly discriminated."""
        handler = HandlerDescriptor(
            id="msg.handler",
            trigger={"type": "message", "keywords": ["hello"]},
        )
        assert isinstance(handler.trigger, MessageTrigger)
        assert handler.trigger.keywords == ["hello"]

    def test_event_trigger_discrimination(self):
        """EventTrigger should be correctly discriminated."""
        handler = HandlerDescriptor(
            id="evt.handler",
            trigger={"type": "event", "event_type": "message"},
        )
        assert isinstance(handler.trigger, EventTrigger)
        assert handler.trigger.event_type == "message"

    def test_schedule_trigger_discrimination(self):
        """ScheduleTrigger should be correctly discriminated."""
        handler = HandlerDescriptor(
            id="sched.handler",
            trigger={"type": "schedule", "cron": "0 9 * * *"},
        )
        assert isinstance(handler.trigger, ScheduleTrigger)
        assert handler.trigger.cron == "0 9 * * *"
