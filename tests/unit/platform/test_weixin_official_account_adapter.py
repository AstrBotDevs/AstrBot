from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from wechatpy.messages import VoiceMessage

from astrbot.core.platform.sources.weixin_official_account import weixin_offacc_adapter
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
    WeixinOfficialAccountPlatformAdapter,
)

pytestmark = pytest.mark.platform


def _adapter() -> WeixinOfficialAccountPlatformAdapter:
    adapter = WeixinOfficialAccountPlatformAdapter(
        {
            "id": "weixin-offacc-test",
            "appid": "appid",
            "secret": "secret",
            "token": "token",
            "encoding_aes_key": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "port": 10000,
        },
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    return adapter


@pytest.mark.asyncio
async def test_weixin_offacc_convert_message_voice_resolves_lazily(
    monkeypatch, tmp_path
):
    adapter = _adapter()
    adapter.client.media.download = MagicMock(
        return_value=SimpleNamespace(content=b"amr")
    )
    monkeypatch.setattr(
        weixin_offacc_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    msg = VoiceMessage(
        {
            "MsgType": "voice",
            "MediaId": "media-1",
            "ToUserName": "bot-1",
            "FromUserName": "user-1",
            "MsgId": 101,
            "CreateTime": 789,
        }
    )

    await adapter.convert_message(msg)

    abm = adapter.handle_msg.await_args.args[0]
    record = abm.message[0]
    assert record.file == ""
    adapter.client.media.download.assert_not_called()

    media_resolver = SimpleNamespace(
        to_path=AsyncMock(return_value="/tmp/weixin-offacc.wav")
    )
    with patch(
        "astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter.MediaResolver",
        return_value=media_resolver,
    ):
        await record._resolve_deferred_source()

    adapter.client.media.download.assert_called_once_with("media-1")
    assert record.file == "/tmp/weixin-offacc.wav"
    assert record.path == "/tmp/weixin-offacc.wav"
    assert (tmp_path / "weixin_offacc_media-1.amr").read_bytes() == b"amr"
    assert getattr(abm, "temporary_file_paths", []) == [
        str(tmp_path / "weixin_offacc_media-1.amr"),
        "/tmp/weixin-offacc.wav",
    ]


@pytest.mark.asyncio
async def test_weixin_offacc_convert_message_voice_keeps_raw_audio_when_conversion_fails(
    monkeypatch,
    tmp_path,
):
    adapter = _adapter()
    adapter.client.media.download = MagicMock(
        return_value=SimpleNamespace(content=b"amr")
    )
    monkeypatch.setattr(
        weixin_offacc_adapter,
        "get_astrbot_temp_path",
        lambda: str(tmp_path),
    )
    msg = VoiceMessage(
        {
            "MsgType": "voice",
            "MediaId": "media-2",
            "ToUserName": "bot-1",
            "FromUserName": "user-2",
            "MsgId": 102,
            "CreateTime": 790,
        }
    )

    await adapter.convert_message(msg)

    abm = adapter.handle_msg.await_args.args[0]
    record = abm.message[0]
    media_resolver = SimpleNamespace(
        to_path=AsyncMock(side_effect=RuntimeError("ffmpeg missing"))
    )
    with patch(
        "astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter.MediaResolver",
        return_value=media_resolver,
    ):
        await record._resolve_deferred_source()

    raw_path = str(tmp_path / "weixin_offacc_media-2.amr")
    assert record.file == raw_path
    assert record.path == raw_path
    assert getattr(abm, "temporary_file_paths", []) == [raw_path]
