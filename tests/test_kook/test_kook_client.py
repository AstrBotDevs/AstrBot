import asyncio
import base64
import json
from dataclasses import dataclass, field
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
TEST_AUDIO_WAV_PATH = "/tmp/kook_audio.wav"


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


class FakeMediaResolver:
    def __init__(self, media_ref: str, **kwargs) -> None:
        self.media_ref = media_ref
        self.kwargs = kwargs

    async def to_path(self, **kwargs) -> str:
        assert self.media_ref.startswith("https://img.kookapp.cn/")
        assert self.kwargs["media_type"] == "audio"
        assert kwargs["target_format"] == "wav"
        return TEST_AUDIO_WAV_PATH


@pytest.mark.asyncio
async def test_kook_upload_asset_resolves_base64_scheme(monkeypatch):
    captured = {}

    class FakeFormData:
        def add_field(self, name: str, value: bytes, filename: str) -> None:
            captured["field_name"] = name
            captured["value"] = value
            captured["filename"] = filename

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def json(self):
            return {"code": 0, "data": {"url": "https://kook.example/asset.bin"}}

        async def text(self):
            return "{}"

    class FakeHttpClient:
        def post(self, url: str, data: FakeFormData):
            captured["url"] = url
            captured["data"] = data
            return FakeResponse()

    monkeypatch.setattr(
        "astrbot.core.platform.sources.kook.kook_client.aiohttp.FormData",
        FakeFormData,
    )

    client = KookClient.__new__(KookClient)
    client._http_client = FakeHttpClient()
    asset_ref = f"base64://{base64.b64encode(b'asset-bytes').decode('ascii')}"

    result = await client.upload_asset(asset_ref)

    assert result == "https://kook.example/asset.bin"
    assert captured["field_name"] == "file"
    assert captured["value"] == b"asset-bytes"
    assert captured["filename"].endswith(".bin")


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
                    file=TEST_AUDIO_WAV_PATH,
                    url=TEST_AUDIO_WAV_PATH,
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
                    file=TEST_AUDIO_WAV_PATH,
                    url=TEST_AUDIO_WAV_PATH,
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
    monkeypatch.setattr(
        "astrbot.core.platform.sources.kook.kook_adapter.MediaResolver",
        FakeMediaResolver,
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
