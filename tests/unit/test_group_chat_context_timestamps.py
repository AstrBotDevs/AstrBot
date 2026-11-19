import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.api.message_components import Plain
from astrbot.builtin_stars.astrbot import group_chat_context
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext


@pytest.fixture
def frozen_processing_time(monkeypatch):
    class FrozenDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 29, 0, 5, 30, tzinfo=tz)

    monkeypatch.setattr(
        group_chat_context, "datetime", SimpleNamespace(datetime=FrozenDatetime)
    )


@pytest.mark.asyncio
async def test_group_context_uses_message_date_and_time(frozen_processing_time):
    context = GroupChatContext(MagicMock(), MagicMock())
    event = MagicMock()
    event.message_obj = SimpleNamespace(
        sender=SimpleNamespace(nickname="Alice"),
        timestamp=int(datetime.datetime(2026, 10, 28, 23, 59, 30).timestamp()),
    )
    event.get_messages.return_value = [Plain("Sent before midnight")]

    formatted = await context._format_message(event, {})

    assert formatted == "[Alice/2026-10-28 23:59:30]:  Sent before midnight"


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamp", [None, 0, -1, True, False, "invalid", 10**30])
async def test_group_context_falls_back_for_invalid_timestamp(
    frozen_processing_time, timestamp
):
    context = GroupChatContext(MagicMock(), MagicMock())
    event = MagicMock()
    event.message_obj = SimpleNamespace(
        sender=SimpleNamespace(nickname="Alice"), timestamp=timestamp
    )
    event.get_messages.return_value = [Plain("hello")]

    formatted = await context._format_message(event, {})

    assert formatted == "[Alice/2026-10-29 00:05:30]:  hello"


@pytest.mark.asyncio
async def test_group_context_falls_back_for_missing_timestamp(frozen_processing_time):
    context = GroupChatContext(MagicMock(), MagicMock())
    event = MagicMock()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [Plain("hello")]

    formatted = await context._format_message(event, {})

    assert formatted == "[Alice/2026-10-29 00:05:30]:  hello"
