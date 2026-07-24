from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from data.plugins.astrbot_plugin_angel_heart.roles.front_desk import FrontDesk


class FakeEvent:
    """Minimal explicit group request already admitted by the control plane."""

    def __init__(self) -> None:
        self.unified_msg_origin = "Astrbot:GroupMessage:1"
        self.message_str = "亚托莉，哈基米是什么梗"
        self.is_at_or_wake_command = True
        self.extras = {"agent_mailbox_class": "WORK"}

    def get_message_outline(self) -> str:
        """Return the visible request."""

        return self.message_str

    def get_extra(self, key, default=None):
        """Read an event extra.

        Args:
            key: Extra key.
            default: Fallback value.

        Returns:
            Stored value or the fallback.
        """

        return self.extras.get(key, default)

    def set_extra(self, key, value) -> None:
        """Store an event extra.

        Args:
            key: Extra key.
            value: Extra value.
        """

        self.extras[key] = value


@pytest.mark.asyncio
async def test_control_plane_work_bypasses_angelheart_second_queue() -> None:
    front_desk = FrontDesk.__new__(FrontDesk)
    front_desk.config_manager = SimpleNamespace(
        speak_words="",
        slap_words="",
        message_batch_window=0,
    )
    front_desk.context = SimpleNamespace(silenced_until={})
    front_desk._ensure_internal_event_id = lambda event: None
    front_desk._check_and_handle_timeout = AsyncMock()
    front_desk.cache_message = AsyncMock()
    front_desk._is_private_chat = lambda chat_id: False
    front_desk._is_group_chat = lambda chat_id: True
    front_desk._ensure_minimum_context = AsyncMock()
    front_desk._notify_secretary = AsyncMock()
    event = FakeEvent()

    await front_desk.handle_event(event)

    front_desk.cache_message.assert_awaited_once()
    front_desk._ensure_minimum_context.assert_not_awaited()
    front_desk._notify_secretary.assert_not_awaited()
    assert event.extras["angelheart_control_plane_bypass"] is True
