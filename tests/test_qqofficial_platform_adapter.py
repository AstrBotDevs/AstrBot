from __future__ import annotations

import pytest

from astrbot.api.message_components import Plain
from astrbot.api.platform import MessageType
from astrbot.core.platform.sources.qqofficial import qqofficial_platform_adapter
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)


class FakeAuthor:
    member_openid = "member-openid"
    user_openid = "user-openid"
    id = "author-id"
    username = "author-name"


class FakeMention:
    id = "bot-id"


class FakeGroupMessage:
    def __init__(self, content: str | None) -> None:
        self.id = "message-id"
        self.content = content
        self.author = FakeAuthor()
        self.group_openid = "group-openid"
        self.attachments = []


class FakeChannelMessage:
    def __init__(self, content: str | None) -> None:
        self.id = "guild-message-id"
        self.content = content
        self.author = FakeAuthor()
        self.mentions = [FakeMention()]
        self.attachments = []
        self.channel_id = "channel-id"


class FakeDirectMessage:
    def __init__(self, content: str | None) -> None:
        self.id = "direct-message-id"
        self.content = content
        self.author = FakeAuthor()
        self.mentions = []
        self.attachments = []


def _plain_texts(message_components: list[object]) -> list[str]:
    return [
        component.text
        for component in message_components
        if isinstance(component, Plain)
    ]


def test_sanitize_command_interaction_tags_keeps_plain_text() -> None:
    assert (
        QQOfficialPlatformAdapter._sanitize_command_interaction_tags("hello world")
        == "hello world"
    )


def test_sanitize_command_interaction_tags_extracts_double_quoted_text() -> None:
    content = (
        'hello <qqbot-cmd-input text="/quick-map" show="quick map" '
        'reference="false" /> now'
    )

    assert (
        QQOfficialPlatformAdapter._sanitize_command_interaction_tags(content)
        == "hello /quick-map now"
    )


def test_sanitize_command_interaction_tags_extracts_single_quoted_text() -> None:
    content = "run <QQBOT-CMD-ENTER show='go' TEXT='/start' />"

    assert (
        QQOfficialPlatformAdapter._sanitize_command_interaction_tags(content)
        == "run /start"
    )


def test_sanitize_command_interaction_tags_removes_tag_without_text() -> None:
    content = 'hello <qqbot-cmd-enter show="enter" /> world'

    assert (
        QQOfficialPlatformAdapter._sanitize_command_interaction_tags(content)
        == "hello  world"
    )


def test_sanitize_command_interaction_tags_leaves_non_target_tag_unchanged() -> None:
    content = '<custom-tag text="/keep" />'

    assert (
        QQOfficialPlatformAdapter._sanitize_command_interaction_tags(content) == content
    )


def test_normalize_message_content_handles_none() -> None:
    assert QQOfficialPlatformAdapter._normalize_message_content(None) == ""


def test_normalize_message_content_removes_bot_mention_and_sanitizes_tags() -> None:
    content = '<@!bot-id> <qqbot-cmd-input text="/quick-map" show="quick map" />'

    assert (
        QQOfficialPlatformAdapter._normalize_message_content(
            content,
            mention_id="bot-id",
        )
        == "/quick-map"
    )


@pytest.mark.asyncio
async def test_parse_from_qqofficial_sanitizes_message_str_and_plain_component(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "GroupMessage",
        FakeGroupMessage,
    )
    raw_message = FakeGroupMessage(
        'hello <qqbot-cmd-input text="/quick-map" show="quick map" />'
    )

    message = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        raw_message,
        MessageType.GROUP_MESSAGE,
    )

    assert message.message_str == "hello /quick-map"
    assert _plain_texts(message.message) == ["hello /quick-map"]


@pytest.mark.asyncio
async def test_parse_from_qqofficial_handles_none_group_content(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "GroupMessage",
        FakeGroupMessage,
    )
    raw_message = FakeGroupMessage(None)

    message = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        raw_message,
        MessageType.GROUP_MESSAGE,
    )

    assert message.message_str == ""
    assert _plain_texts(message.message) == [""]


@pytest.mark.asyncio
async def test_parse_from_qqofficial_handles_none_channel_content(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "Message",
        FakeChannelMessage,
    )
    raw_message = FakeChannelMessage(None)

    message = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        raw_message,
        MessageType.GROUP_MESSAGE,
    )

    assert message.message_str == ""
    assert _plain_texts(message.message) == [""]


@pytest.mark.asyncio
async def test_parse_from_qqofficial_sanitizes_channel_plain_component(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "Message",
        FakeChannelMessage,
    )
    raw_message = FakeChannelMessage(
        '<@!bot-id> hello <qqbot-cmd-input text="/quick-map" show="quick map" />'
    )

    message = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        raw_message,
        MessageType.GROUP_MESSAGE,
    )

    assert message.message_str == "hello /quick-map"
    assert _plain_texts(message.message) == ["hello /quick-map"]


@pytest.mark.asyncio
async def test_parse_from_qqofficial_handles_none_direct_content(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "DirectMessage",
        FakeDirectMessage,
    )
    raw_message = FakeDirectMessage(None)

    message = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        raw_message,
        MessageType.FRIEND_MESSAGE,
    )

    assert message.message_str == ""
    assert _plain_texts(message.message) == [""]
