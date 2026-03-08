"""Test QQ Official platform adapter deduplication."""
import asyncio

from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)


class MockClient:
    """Mock botpy client."""
    pass


def create_adapter() -> QQOfficialPlatformAdapter:
    """Create adapter instance for testing."""
    config = {
        "appid": "test_appid",
        "secret": "test_secret",
        "enable_group_c2c": True,
        "enable_guild_direct_message": True,
    }
    queue = asyncio.Queue()
    adapter = QQOfficialPlatformAdapter(config, {}, queue)
    return adapter


class MockRawMessage:
    def __init__(self, timestamp: str = "", **kwargs) -> None:
        self.timestamp = timestamp
        for key, value in kwargs.items():
            setattr(self, key, value)


def create_abm(
    *,
    session_id: str = "group_1",
    sender_id: str = "user_1",
    message_text: str = "/日报",
    raw_timestamp: str = "2026-03-08T01:12:49Z",
    message_id: str = "",
    raw_extra: dict | None = None,
) -> AstrBotMessage:
    abm = AstrBotMessage()
    abm.type = MessageType.GROUP_MESSAGE
    abm.session_id = session_id
    abm.sender = MessageMember(sender_id, "")
    abm.message_str = message_text
    abm.raw_message = MockRawMessage(raw_timestamp, **(raw_extra or {}))
    abm.message_id = message_id
    return abm


def test_is_duplicate_message():
    """Test message deduplication logic."""
    adapter = create_adapter()

    msg_id = "test_message_123"

    # First message should NOT be duplicate
    assert adapter._is_duplicate_message(msg_id) is False

    # Second call with same ID should be duplicate
    assert adapter._is_duplicate_message(msg_id) is True

    # Third call should still be duplicate
    assert adapter._is_duplicate_message(msg_id) is True


def test_different_messages_not_duplicates():
    """Test that different messages are not marked as duplicates."""
    adapter = create_adapter()

    msg_id_1 = "message_001"
    msg_id_2 = "message_002"
    msg_id_3 = "message_003"

    assert adapter._is_duplicate_message(msg_id_1) is False
    assert adapter._is_duplicate_message(msg_id_2) is False
    assert adapter._is_duplicate_message(msg_id_3) is False

    # Re-checking first message should be duplicate now
    assert adapter._is_duplicate_message(msg_id_1) is True


def test_expired_messages_cleanup():
    """Test that old message IDs are cleaned up."""
    import time

    adapter = create_adapter()

    msg_id = "old_message"

    # Add a message with old timestamp
    adapter.message_id_timestamps[msg_id] = time.time() - 1900  # 31+ minutes ago

    # Run cleanup
    adapter._clean_expired_messages()

    # Old message should be cleaned up, so not a duplicate anymore
    assert adapter._is_duplicate_message(msg_id) is False


def test_short_window_fingerprint_dedup():
    adapter = create_adapter()

    abm = create_abm()
    assert adapter._is_duplicate_fingerprint(abm) is False
    assert adapter._is_duplicate_fingerprint(abm) is True


def test_short_window_fingerprint_cleanup():
    import time

    adapter = create_adapter()
    abm = create_abm()
    fingerprint = adapter._build_short_window_fingerprint(abm)
    adapter.message_fingerprint_timestamps[fingerprint] = time.time() - 10
    adapter._fingerprint_ttl_seconds = 1.0

    adapter._clean_expired_fingerprints()

    assert fingerprint not in adapter.message_fingerprint_timestamps


def test_build_dedup_keys_with_message_id_and_seq_in_channel():
    adapter = create_adapter()
    abm = create_abm(
        message_id="msg_001",
        raw_extra={"id": "event_abc", "seq_in_channel": "42", "seq": "43"},
    )

    keys = adapter._build_dedup_keys(abm)

    assert "message_id:msg_001" in keys
    assert "event_id:event_abc" in keys
    assert "seq_in_channel:group_1:user_1:42" in keys
    assert "seq:group_1:user_1:43" in keys
