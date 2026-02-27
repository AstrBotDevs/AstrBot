"""Tests for AstrBotMessage and MessageMember classes."""

import time
from unittest.mock import patch

from astrbot.core.message.components import Image, Plain
from astrbot.core.platform.astrbot_message import AstrBotMessage, Group, MessageMember
from astrbot.core.platform.message_type import MessageType


class TestMessageMember:
    """Tests for MessageMember dataclass."""

    def test_message_member_creation_basic(self):
        """Test creating a MessageMember with required fields."""
        member = MessageMember(user_id="user123")

        assert member.user_id == "user123"
        assert member.nickname is None

    def test_message_member_creation_with_nickname(self):
        """Test creating a MessageMember with nickname."""
        member = MessageMember(user_id="user123", nickname="TestUser")

        assert member.user_id == "user123"
        assert member.nickname == "TestUser"

    def test_message_member_str_with_nickname(self):
        """Test __str__ method with nickname."""
        member = MessageMember(user_id="user123", nickname="TestUser")
        result = str(member)

        assert "User ID: user123" in result
        assert "Nickname: TestUser" in result

    def test_message_member_str_without_nickname(self):
        """Test __str__ method without nickname."""
        member = MessageMember(user_id="user123")
        result = str(member)

        assert "User ID: user123" in result
        assert "Nickname: N/A" in result


class TestGroup:
    """Tests for Group dataclass."""

    def test_group_creation_basic(self):
        """Test creating a Group with required fields."""
        group = Group(group_id="group123")

        assert group.group_id == "group123"
        assert group.group_name is None
        assert group.group_avatar is None
        assert group.group_owner is None
        assert group.group_admins is None
        assert group.members is None

    def test_group_creation_with_all_fields(self):
        """Test creating a Group with all fields."""
        members = [MessageMember(user_id="user1"), MessageMember(user_id="user2")]
        group = Group(
            group_id="group123",
            group_name="Test Group",
            group_avatar="http://example.com/avatar.jpg",
            group_owner="owner123",
            group_admins=["admin1", "admin2"],
            members=members,
        )

        assert group.group_id == "group123"
        assert group.group_name == "Test Group"
        assert group.group_avatar == "http://example.com/avatar.jpg"
        assert group.group_owner == "owner123"
        assert group.group_admins == ["admin1", "admin2"]
        assert group.members == members

    def test_group_str_with_all_fields(self):
        """Test __str__ method with all fields."""
        members = [MessageMember(user_id="user1", nickname="User One")]
        group = Group(
            group_id="group123",
            group_name="Test Group",
            group_avatar="http://example.com/avatar.jpg",
            group_owner="owner123",
            group_admins=["admin1"],
            members=members,
        )
        result = str(group)

        assert "Group ID: group123" in result
        assert "Name: Test Group" in result
        assert "Avatar: http://example.com/avatar.jpg" in result
        assert "Owner ID: owner123" in result
        assert "Admin IDs: ['admin1']" in result
        assert "Members Len: 1" in result

    def test_group_str_with_minimal_fields(self):
        """Test __str__ method with minimal fields."""
        group = Group(group_id="group123")
        result = str(group)

        assert "Group ID: group123" in result
        assert "Name: N/A" in result
        assert "Avatar: N/A" in result
        assert "Owner ID: N/A" in result
        assert "Admin IDs: N/A" in result
        assert "Members Len: 0" in result
        assert "First Member: N/A" in result


class TestAstrBotMessage:
    """Tests for AstrBotMessage class."""

    def test_astrbot_message_creation(self):
        """Test creating an AstrBotMessage."""
        message = AstrBotMessage()

        assert message.group is None
        assert message.timestamp is not None
        assert isinstance(message.timestamp, int)

    def test_astrbot_message_timestamp(self):
        """Test timestamp is set on creation."""
        with patch.object(time, "time", return_value=1234567890):
            message = AstrBotMessage()
            assert message.timestamp == 1234567890

    def test_astrbot_message_all_attributes(self):
        """Test setting all attributes on AstrBotMessage."""
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = "bot123"
        message.session_id = "session123"
        message.message_id = "msg123"
        message.sender = MessageMember(user_id="user123", nickname="TestUser")
        message.message = [Plain(text="Hello")]
        message.message_str = "Hello"
        message.raw_message = {"raw": "data"}

        assert message.type == MessageType.FRIEND_MESSAGE
        assert message.self_id == "bot123"
        assert message.session_id == "session123"
        assert message.message_id == "msg123"
        assert message.sender.user_id == "user123"
        assert len(message.message) == 1
        assert message.message_str == "Hello"
        assert message.raw_message == {"raw": "data"}

    def test_astrbot_message_str(self):
        """Test __str__ method."""
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = "bot123"

        result = str(message)
        assert "'type'" in result
        assert "'self_id'" in result


class TestAstrBotMessageGroupId:
    """Tests for AstrBotMessage group_id property."""

    def test_group_id_returns_empty_when_no_group(self):
        """Test group_id returns empty string when group is None."""
        message = AstrBotMessage()
        assert message.group_id == ""

    def test_group_id_returns_group_id_when_group_exists(self):
        """Test group_id returns the group's id when group exists."""
        message = AstrBotMessage()
        message.group = Group(group_id="group123")

        assert message.group_id == "group123"

    def test_group_id_setter_creates_new_group(self):
        """Test group_id setter creates a new group if none exists."""
        message = AstrBotMessage()
        message.group_id = "new_group123"

        assert message.group is not None
        assert message.group.group_id == "new_group123"

    def test_group_id_setter_updates_existing_group(self):
        """Test group_id setter updates existing group's id."""
        message = AstrBotMessage()
        message.group = Group(group_id="old_group")
        message.group_id = "new_group"

        assert message.group.group_id == "new_group"

    def test_group_id_setter_with_none_removes_group(self):
        """Test group_id setter with None removes the group."""
        message = AstrBotMessage()
        message.group = Group(group_id="group123")
        message.group_id = None

        assert message.group is None

    def test_group_id_setter_with_empty_string_removes_group(self):
        """Test group_id setter with empty string removes the group."""
        message = AstrBotMessage()
        message.group = Group(group_id="group123")
        message.group_id = ""

        assert message.group is None


class TestAstrBotMessageTypes:
    """Tests for AstrBotMessage with different message types."""

    def test_friend_message_type(self):
        """Test AstrBotMessage with FRIEND_MESSAGE type."""
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE

        assert message.type == MessageType.FRIEND_MESSAGE
        assert message.type.value == "FriendMessage"

    def test_group_message_type(self):
        """Test AstrBotMessage with GROUP_MESSAGE type."""
        message = AstrBotMessage()
        message.type = MessageType.GROUP_MESSAGE

        assert message.type == MessageType.GROUP_MESSAGE
        assert message.type.value == "GroupMessage"

    def test_other_message_type(self):
        """Test AstrBotMessage with OTHER_MESSAGE type."""
        message = AstrBotMessage()
        message.type = MessageType.OTHER_MESSAGE

        assert message.type == MessageType.OTHER_MESSAGE
        assert message.type.value == "OtherMessage"


class TestAstrBotMessageChain:
    """Tests for AstrBotMessage message chain."""

    def test_message_chain_with_plain_text(self):
        """Test message chain with plain text."""
        message = AstrBotMessage()
        message.message = [Plain(text="Hello world")]

        assert len(message.message) == 1
        assert isinstance(message.message[0], Plain)
        assert message.message[0].text == "Hello world"

    def test_message_chain_with_multiple_components(self):
        """Test message chain with multiple components."""
        message = AstrBotMessage()
        message.message = [
            Plain(text="Hello "),
            Plain(text="world"),
            Image(file="http://example.com/img.jpg"),
        ]

        assert len(message.message) == 3
        assert isinstance(message.message[0], Plain)
        assert isinstance(message.message[1], Plain)
        assert isinstance(message.message[2], Image)

    def test_message_chain_empty(self):
        """Test empty message chain."""
        message = AstrBotMessage()
        message.message = []

        assert len(message.message) == 0
