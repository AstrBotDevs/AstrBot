from unittest.mock import MagicMock

from astrbot.core.utils.session_waiter import DefaultSessionFilter


def _event(umo: str, sender_id: str) -> MagicMock:
    event = MagicMock()
    event.unified_msg_origin = umo
    event.get_sender_id.return_value = sender_id
    return event


def test_default_filter_isolates_group_members() -> None:
    session_filter = DefaultSessionFilter()
    umo = "qq:GroupMessage:123"

    first_member = session_filter.filter(_event(umo, "user-1"))
    second_member = session_filter.filter(_event(umo, "user-2"))

    assert first_member != second_member


def test_default_filter_keeps_same_sender_in_same_chat() -> None:
    session_filter = DefaultSessionFilter()
    umo = "qq:GroupMessage:123"

    first_message = session_filter.filter(_event(umo, "user-1"))
    next_message = session_filter.filter(_event(umo, "user-1"))

    assert first_message == next_message


def test_default_filter_isolates_same_sender_across_chats() -> None:
    session_filter = DefaultSessionFilter()

    first_chat = session_filter.filter(_event("qq:GroupMessage:123", "user-1"))
    second_chat = session_filter.filter(_event("qq:GroupMessage:456", "user-1"))

    assert first_chat != second_chat
