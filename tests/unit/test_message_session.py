"""Tests for astrbot.core.platform.message_session — MessageSession."""

import pytest

from astrbot.core.platform.message_session import MessageSession, MessageSesion
from astrbot.core.platform.message_type import MessageType


# ===================================================================
# Construction
# ===================================================================

class TestConstruction:
    """MessageSession construction and post_init."""

    def test_basic_construction(self):
        session = MessageSession(
            platform_name="test_platform",
            message_type=MessageType.FRIEND_MESSAGE,
            session_id="session_123",
        )
        assert session.platform_name == "test_platform"
        assert session.message_type == MessageType.FRIEND_MESSAGE
        assert session.session_id == "session_123"

    def test_post_init_sets_platform_id_from_platform_name(self):
        """platform_id should be auto-set to platform_name in __post_init__."""
        session = MessageSession(
            platform_name="my_adapter",
            message_type=MessageType.GROUP_MESSAGE,
            session_id="g123",
        )
        assert session.platform_id == "my_adapter"

    def test_platform_id_equals_platform_name(self):
        """Confirm platform_id and platform_name hold the same value."""
        session = MessageSession(
            platform_name="pname",
            message_type=MessageType.OTHER_MESSAGE,
            session_id="sid",
        )
        assert session.platform_id == session.platform_name


# ===================================================================
# __str__
# ===================================================================

class TestStr:
    """MessageSession.__str__ produces the unified-msg-origin format."""

    def test_friend_message_format(self):
        session = MessageSession(
            platform_name="discord",
            message_type=MessageType.FRIEND_MESSAGE,
            session_id="user_42",
        )
        assert str(session) == "discord:FriendMessage:user_42"

    def test_group_message_format(self):
        session = MessageSession(
            platform_name="telegram",
            message_type=MessageType.GROUP_MESSAGE,
            session_id="group_99",
        )
        assert str(session) == "telegram:GroupMessage:group_99"

    def test_other_message_format(self):
        session = MessageSession(
            platform_name="system",
            message_type=MessageType.OTHER_MESSAGE,
            session_id="sys_1",
        )
        assert str(session) == "system:OtherMessage:sys_1"


# ===================================================================
# from_str
# ===================================================================

class TestFromStr:
    """MessageSession.from_str parses the unified-msg-origin string."""

    def test_parses_friend_message(self):
        session = MessageSession.from_str("qq:FriendMessage:user_007")
        assert session.platform_name == "qq"
        assert session.platform_id == "qq"
        assert session.message_type == MessageType.FRIEND_MESSAGE
        assert session.session_id == "user_007"

    def test_parses_group_message(self):
        session = MessageSession.from_str(
            "slack:GroupMessage:channel_C01"
        )
        assert session.platform_name == "slack"
        assert session.message_type == MessageType.GROUP_MESSAGE
        assert session.session_id == "channel_C01"

    @staticmethod
    def test_roundtrip():
        """str -> from_str -> str should be lossless."""
        original = "wechat:FriendMessage:wx_abc"
        session = MessageSession.from_str(original)
        assert str(session) == original

    @staticmethod
    def test_session_id_contains_colons():
        """If the session_id itself contains colons, only the first two split
        boundaries are consumed; the rest is part of session_id."""
        raw = "platform:GroupMessage:user:name:extra"
        session = MessageSession.from_str(raw)
        assert session.platform_name == "platform"
        assert session.message_type == MessageType.GROUP_MESSAGE
        assert session.session_id == "user:name:extra"
        assert str(session) == raw

    @staticmethod
    def test_preserves_explicit_platform_id_after_roundtrip():
        """from_str sets platform_name from the parsed platform_id segment,
        so platform_id == platform_name after a roundtrip."""
        session = MessageSession.from_str("my_id:FriendMessage:sid")
        assert session.platform_name == "my_id"
        assert session.platform_id == "my_id"


# ===================================================================
# Back-compat alias
# ===================================================================

class TestAlias:
    """MessageSesion (note the typo) should be an alias for MessageSession."""

    def test_alias_is_same_class(self):
        assert MessageSesion is MessageSession

    def test_alias_can_be_instantiated(self):
        session = MessageSesion(
            platform_name="alias_test",
            message_type=MessageType.GROUP_MESSAGE,
            session_id="alias_sid",
        )
        assert isinstance(session, MessageSession)
        assert session.platform_name == "alias_test"


# ===================================================================
# Dataclass equality
# ===================================================================

class TestEquality:
    """MessageSession is a dataclass so it inherits __eq__."""

    def test_equal_sessions(self):
        a = MessageSession(
            platform_name="p", message_type=MessageType.FRIEND_MESSAGE, session_id="s"
        )
        b = MessageSession(
            platform_name="p", message_type=MessageType.FRIEND_MESSAGE, session_id="s"
        )
        assert a == b

    def test_inequality_different_session_id(self):
        a = MessageSession(
            platform_name="p", message_type=MessageType.FRIEND_MESSAGE, session_id="s1"
        )
        b = MessageSession(
            platform_name="p", message_type=MessageType.FRIEND_MESSAGE, session_id="s2"
        )
        assert a != b
