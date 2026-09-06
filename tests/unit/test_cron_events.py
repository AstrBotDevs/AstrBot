"""Tests for CronMessageEvent."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.send_message = AsyncMock()
    return ctx


@pytest.fixture
def mock_session():
    session = MagicMock(spec=MessageSession)
    session.session_id = "test-session-id"
    session.platform_id = "test-platform"
    return session


class TestCronMessageEventInit:
    """Tests for CronMessageEvent construction."""

    def test_init_default_params(self, mock_context, mock_session):
        """Default params produce a synthetic event with correct attributes."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Hello from cron",
        )
        assert event.message_str == "Hello from cron"
        assert event.is_at_or_wake_command is True
        assert event.is_wake is True
        assert event.session == mock_session
        assert event.context_obj == mock_context

    def test_init_sender_defaults(self, mock_context, mock_session):
        """Default sender_id and sender_name are 'astrbot' and 'Scheduler'."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )
        assert event.message_obj.self_id == "astrbot"
        assert event.message_obj.sender.nickname == "Scheduler"
        assert event.message_obj.sender.user_id == "test-session-id"

    def test_init_custom_sender(self, mock_context, mock_session):
        """Custom sender_id and sender_name are reflected on the message object."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
            sender_id="custom-bot",
            sender_name="CustomName",
        )
        assert event.message_obj.self_id == "custom-bot"
        assert event.message_obj.sender.nickname == "CustomName"

    def test_init_with_extras(self, mock_context, mock_session):
        """Extras dict is merged into _extras."""
        extras = {"origin": "api", "cron_payload": {"key": "value"}}
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
            extras=extras,
        )
        assert event._extras.get("origin") == "api"
        assert event._extras["cron_payload"] == {"key": "value"}

    def test_init_group_message_type(self, mock_context, mock_session):
        """MessageType.GROUP_MESSAGE is preserved in the message object."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
            message_type=MessageType.GROUP_MESSAGE,
        )
        assert event.message_obj.type == MessageType.GROUP_MESSAGE

    def test_init_platform_meta(self, mock_context, mock_session):
        """Platform metadata is set to cron / CronJob / platform_id."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )
        assert event.platform_meta.name == "cron"
        assert event.platform_meta.description == "CronJob"
        assert event.platform_meta.id == "test-platform"

    def test_init_message_components(self, mock_context, mock_session):
        """The message is wrapped in a Plain component."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Cron message text",
        )
        assert len(event.message_obj.message) == 1
        assert isinstance(event.message_obj.message[0], Plain)
        assert event.message_obj.message[0].text == "Cron message text"
        assert event.message_obj.message_str == "Cron message text"
        assert event.message_obj.raw_message == "Cron message text"

    def test_init_timestamp_within_range(self, mock_context, mock_session):
        """Timestamp is set to the current time."""
        before = int(time.time())
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )
        after = int(time.time())
        assert before <= event.message_obj.timestamp <= after

    def test_init_message_id_is_uuid_hex(self, mock_context, mock_session):
        """Message ID is a 32-char hex string (uuid4 hex)."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )
        mid = event.message_obj.message_id
        assert isinstance(mid, str)
        assert len(mid) == 32
        # All characters should be valid hex digits
        int(mid, 16)

    def test_init_none_extras_does_not_raise(self, mock_context, mock_session):
        """Passing extras=None does not raise."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
            extras=None,
        )
        # Should not raise; _extras remains default
        assert isinstance(event._extras, dict)

    def test_init_uses_session_session_id(self, mock_context, mock_session):
        """Session ID is taken from session.session_id."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )
        assert event.session_id == "test-session-id"


class TestCronMessageEventSend:
    """Tests for CronMessageEvent.send."""

    @pytest.mark.asyncio
    async def test_send_calls_context(self, mock_context, mock_session):
        """send delegates to context.send_message on the original session."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )
        chain = MessageChain([Plain("response")])

        with patch.object(AstrMessageEvent, "send", new_callable=AsyncMock):
            await event.send(chain)

        mock_context.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_none_is_noop(self, mock_context, mock_session):
        """send(None) returns immediately without calling context."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )
        with patch.object(AstrMessageEvent, "send", new_callable=AsyncMock) as mock_super:
            await event.send(None)

        mock_context.send_message.assert_not_called()
        mock_super.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_calls_super(self, mock_context, mock_session):
        """send also delegates to super().send()."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )
        chain = MessageChain([Plain("response")])

        with patch.object(AstrMessageEvent, "send", new_callable=AsyncMock) as mock_super:
            await event.send(chain)

        mock_super.assert_awaited_once_with(chain)

    @pytest.mark.asyncio
    async def test_send_streaming_iterates_generator(self, mock_context, mock_session):
        """send_streaming calls send for each yielded chain."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )

        async def gen():
            yield MessageChain([Plain("part1")])
            yield MessageChain([Plain("part2")])

        with patch.object(event, "send", new_callable=AsyncMock) as mock_send:
            await event.send_streaming(gen())

        assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_send_streaming_empty_generator(self, mock_context, mock_session):
        """send_streaming does not call send when the generator is empty."""
        event = CronMessageEvent(
            context=mock_context,
            session=mock_session,
            message="Test",
        )

        async def empty_gen():
            if False:
                yield  # pragma: no cover

        with patch.object(event, "send", new_callable=AsyncMock) as mock_send:
            await event.send_streaming(empty_gen())

        mock_send.assert_not_called()
