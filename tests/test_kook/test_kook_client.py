import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import (
    At,
    AtAll,
    BaseMessageComponent,
    Plain,
    Record,
)
from astrbot.core.platform.sources.kook.kook_client import KookClient
from astrbot.core.platform.sources.kook.kook_config import KookConfig
from astrbot.core.platform.sources.kook.kook_types import (
    KookMessageEventData,
    KookWebsocketEvent,
)
from tests.test_kook.shared import (
    KookEventDataPath,
    mock_http_client,
    mock_kook_roles_record,
)

TEST_BOT_ID = 1234567891
TEST_BOT_USERNAME = "test_username"
TEST_BOT_NICKNAME = "test_nickname"


def mock_kook_client(config: KookConfig, event_callback):
    class MockKookClient:
        def __init__(self, config, callback):
            self.bot_id = TEST_BOT_ID
            self.bot_nickname = TEST_BOT_NICKNAME
            self.bot_username = TEST_BOT_USERNAME
            self.http_client = mock_http_client()
            self.connect = AsyncMock()
            self.close = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    return MockKookClient(config, event_callback)


def get_json_field(content: dict, json_field_path: list[str | int]) -> Any:
    expend_value = content
    for key in json_field_path:
        expend_value = expend_value[key]
    return expend_value


@dataclass
class JsonFieldPaths:
    message_str: list[int | str] = field(default_factory=list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expected_json_data_path, expected_message_str, expected_message_components",
    [
        (
            KookEventDataPath.GROUP_MESSAGE_WITH_MENTION,
            ["d", "extra", "kmarkdown", "raw_content"],
            [
                # 这里默认机器人一定属于某个角色id
                At(qq=TEST_BOT_ID, name="some_role"),
                Plain(text="/help"),
                At(qq=3351526782, name="some_username"),
                AtAll(qq="all", name=""),
            ],
        ),
        (
            KookEventDataPath.GROUP_MESSAGE,
            ["d", "extra", "kmarkdown", "raw_content"],
            [Plain(text="done!")],
        ),
        (
            KookEventDataPath.MESSAGE_WITH_CARD_1,
            "[audio]",
            [
                Plain(text="[audio]"),
                Record(
                    file="https://img.kookapp.cn/attachments/2026-03/03/69a6841c3125d.wav",
                    url="",
                    text=None,
                    path=None,
                ),
            ],
        ),
        (
            KookEventDataPath.MESSAGE_WITH_CARD_2,
            ["d", "extra", "kmarkdown", "raw_content"],
            [
                Plain(text="(met)"),
                Plain(text="all(met) #hello \\*\\*world\\*\\*  [audio]\n😆"),
                Record(
                    file="https://img.kookapp.cn/attachments/2026-03/03/69a6841c3125d.wav",
                    url="",
                    text=None,
                    path=None,
                ),
            ],
        ),
        (
            KookEventDataPath.PRIVATE_MESSAGE,
            ["d", "extra", "kmarkdown", "raw_content"],
            [Plain(text="/help")],
        ),
    ],
)
async def test_kook_event_warp_message(
    expected_json_data_path: Path,
    expected_message_str: list[int | str] | str,
    expected_message_components: list[BaseMessageComponent],
):
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "astrbot.core.platform.sources.kook.kook_adapter.KookClient", mock_kook_client
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.kook.kook_adapter.KookRolesRecord",
        mock_kook_roles_record,
    )

    from astrbot.core.platform.sources.kook.kook_adapter import KookPlatformAdapter

    adapter = KookPlatformAdapter({}, {}, asyncio.Queue())

    raw_event_str = expected_json_data_path.read_text(encoding="utf-8")
    raw_event = json.loads(raw_event_str)
    event = KookWebsocketEvent.from_json(
        raw_event_str,
    )
    assert isinstance(event.data, KookMessageEventData)

    astrbotMessage = await adapter.convert_message(event.data)
    assert astrbotMessage.self_id == TEST_BOT_ID
    assert astrbotMessage.sender.user_id == raw_event["d"]["author_id"]
    assert (
        astrbotMessage.sender.nickname == raw_event["d"]["extra"]["author"]["username"]
    )
    assert astrbotMessage.raw_message == raw_event["d"]
    assert astrbotMessage.message_id == raw_event["d"]["msg_id"]
    assert astrbotMessage.message == expected_message_components
    if isinstance(expected_message_str, str):
        assert astrbotMessage.message_str == expected_message_str
    else:
        assert get_json_field(raw_event, expected_message_str)
