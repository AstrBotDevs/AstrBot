from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.api.message_components import At
from astrbot.api.platform import AstrBotMessage, MessageType
from astrbot.core.platform.sources.qqofficial import qqofficial_platform_adapter
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)
from astrbot.core.platform.sources.qqofficial_webhook import qo_webhook_adapter

APPID = "1024"


class _FakeGroupMessage:
    def __init__(self, content: str = "hello") -> None:
        self.id = "group-msg"
        self.content = content
        self.group_openid = "group-openid"
        self.author = SimpleNamespace(member_openid="member-openid")
        self.attachments = []


class _FakeChannelMessage:
    def __init__(self, content: str = f"<@!{APPID}> channel hello") -> None:
        self.id = "channel-msg"
        self.content = content
        self.channel_id = "channel-id"
        self.author = SimpleNamespace(id="author-id", username="alice")
        self.attachments = []


class _FakeDirectMessage:
    def __init__(self, content: str = "direct hello") -> None:
        self.id = "direct-msg"
        self.content = content
        self.author = SimpleNamespace(id="author-id", username="alice")
        self.sender = SimpleNamespace(user_id="direct-user")
        self.attachments = []


class _FakeC2CMessage:
    def __init__(self, content: str = "c2c hello") -> None:
        self.id = "c2c-msg"
        self.content = content
        self.author = SimpleNamespace(user_openid="user-openid")
        self.sender = SimpleNamespace(user_id="c2c-user")
        self.attachments = []


@pytest.fixture
def fake_qqofficial_message_types(monkeypatch):
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "GroupMessage",
        _FakeGroupMessage,
    )
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "Message",
        _FakeChannelMessage,
    )
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "DirectMessage",
        _FakeDirectMessage,
    )
    monkeypatch.setattr(
        qqofficial_platform_adapter.botpy.message,
        "C2CMessage",
        _FakeC2CMessage,
    )


def _at_targets(message: AstrBotMessage) -> list[str]:
    return [
        str(component.qq) for component in message.message if isinstance(component, At)
    ]


@pytest.mark.asyncio
async def test_qqofficial_group_message_uses_appid_self_id_and_at(
    fake_qqofficial_message_types,
):
    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        _FakeGroupMessage(),
        MessageType.GROUP_MESSAGE,
        APPID,
    )

    assert abm.self_id == APPID
    assert abm.group_id == "group-openid"
    assert _at_targets(abm) == [APPID]


@pytest.mark.asyncio
async def test_qqofficial_channel_message_uses_appid_self_id_and_at(
    fake_qqofficial_message_types,
):
    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        _FakeChannelMessage(),
        MessageType.GROUP_MESSAGE,
        APPID,
    )

    assert abm.self_id == APPID
    assert abm.group_id == "channel-id"
    assert abm.message_str == "channel hello"
    assert _at_targets(abm) == [APPID]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_sender_id"),
    [
        (_FakeDirectMessage(), "author-id"),
        (_FakeC2CMessage(), "user-openid"),
    ],
)
async def test_qqofficial_private_messages_use_appid_self_id_without_at(
    fake_qqofficial_message_types,
    message,
    expected_sender_id: str,
):
    abm = await QQOfficialPlatformAdapter._parse_from_qqofficial(
        message,
        MessageType.FRIEND_MESSAGE,
        APPID,
    )

    assert abm.self_id == APPID
    assert abm.sender.user_id == expected_sender_id
    assert _at_targets(abm) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_cls", "handler_name", "message", "message_type"),
    [
        (
            qqofficial_platform_adapter.botClient,
            "on_group_at_message_create",
            _FakeGroupMessage(),
            MessageType.GROUP_MESSAGE,
        ),
        (
            qqofficial_platform_adapter.botClient,
            "on_at_message_create",
            _FakeChannelMessage(),
            MessageType.GROUP_MESSAGE,
        ),
        (
            qqofficial_platform_adapter.botClient,
            "on_direct_message_create",
            _FakeDirectMessage(),
            MessageType.FRIEND_MESSAGE,
        ),
        (
            qqofficial_platform_adapter.botClient,
            "on_c2c_message_create",
            _FakeC2CMessage(),
            MessageType.FRIEND_MESSAGE,
        ),
        (
            qo_webhook_adapter.botClient,
            "on_group_at_message_create",
            _FakeGroupMessage(),
            MessageType.GROUP_MESSAGE,
        ),
        (
            qo_webhook_adapter.botClient,
            "on_at_message_create",
            _FakeChannelMessage(),
            MessageType.GROUP_MESSAGE,
        ),
        (
            qo_webhook_adapter.botClient,
            "on_direct_message_create",
            _FakeDirectMessage(),
            MessageType.FRIEND_MESSAGE,
        ),
        (
            qo_webhook_adapter.botClient,
            "on_c2c_message_create",
            _FakeC2CMessage(),
            MessageType.FRIEND_MESSAGE,
        ),
    ],
)
async def test_qqofficial_handlers_pass_platform_appid_to_parser(
    client_cls,
    handler_name: str,
    message,
    message_type: MessageType,
):
    client = client_cls.__new__(client_cls)
    client.platform = SimpleNamespace(
        appid=APPID,
        remember_session_scene=MagicMock(),
    )
    client._commit = MagicMock()

    parsed_message = AstrBotMessage()
    parsed_message.sender = SimpleNamespace(user_id="sender-id")
    parse_mock = AsyncMock(return_value=parsed_message)

    with patch.object(
        QQOfficialPlatformAdapter,
        "_parse_from_qqofficial",
        parse_mock,
    ):
        await getattr(client, handler_name)(message)

    parse_mock.assert_awaited_once_with(message, message_type, APPID)
