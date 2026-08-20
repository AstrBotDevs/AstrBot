from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.streaming_override import (
    RESOLVED_STREAMING_EXTRA,
    resolve_streaming_response,
)


class Event:
    def __init__(self) -> None:
        self.unified_msg_origin = "webchat:FriendMessage:stream"
        self._extra: dict[str, object] = {}

    def get_extra(self, key, default=None):
        return self._extra.get(key, default)

    def set_extra(self, key, value):
        self._extra[key] = value


@pytest.mark.asyncio
async def test_resolve_streaming_pins_the_first_decision():
    event = Event()
    preferences = SimpleNamespace(session_get=AsyncMock(return_value=True))
    config = {"provider_settings": {"streaming_response": False}}

    first = await resolve_streaming_response(event, config, preferences)
    preferences.session_get = AsyncMock(return_value=False)
    second = await resolve_streaming_response(event, config, preferences)

    assert first is True
    assert second is True
    assert event.get_extra(RESOLVED_STREAMING_EXTRA) is True


@pytest.mark.asyncio
async def test_event_enable_streaming_wins_over_session_override():
    event = Event()
    event.set_extra("enable_streaming", False)
    preferences = SimpleNamespace(session_get=AsyncMock(return_value=True))

    assert (
        await resolve_streaming_response(
            event, {"provider_settings": {"streaming_response": True}}, preferences
        )
        is False
    )
    assert preferences.session_get.await_count == 0
