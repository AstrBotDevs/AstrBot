import asyncio
import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from tests.fixtures.helpers import (
    create_mock_file,
    create_mock_update,
    make_platform_config,
)
from tests.fixtures.mocks.telegram import create_mock_telegram_modules

_TELEGRAM_PLATFORM_ADAPTER = None


def _load_telegram_adapter():
    global _TELEGRAM_PLATFORM_ADAPTER
    if _TELEGRAM_PLATFORM_ADAPTER is not None:
        return _TELEGRAM_PLATFORM_ADAPTER

    mocks = create_mock_telegram_modules()
    patched_modules = {
        "telegram": mocks["telegram"],
        "telegram.constants": mocks["telegram"].constants,
        "telegram.error": mocks["telegram"].error,
        "telegram.ext": mocks["telegram.ext"],
        "telegramify_markdown": mocks["telegramify_markdown"],
        "apscheduler": mocks["apscheduler"],
        "apscheduler.schedulers": mocks["apscheduler"].schedulers,
        "apscheduler.schedulers.asyncio": mocks["apscheduler"].schedulers.asyncio,
        "apscheduler.schedulers.background": mocks["apscheduler"].schedulers.background,
    }
    with patch.dict(sys.modules, patched_modules):
        sys.modules.pop("astrbot.core.platform.sources.telegram.tg_adapter", None)
        module = importlib.import_module("astrbot.core.platform.sources.telegram.tg_adapter")
        _TELEGRAM_PLATFORM_ADAPTER = module.TelegramPlatformAdapter
        return _TELEGRAM_PLATFORM_ADAPTER


def _build_context() -> MagicMock:
    context = MagicMock()
    context.bot.username = "test_bot"
    context.bot.id = 12345678
    return context


@pytest.mark.asyncio
async def test_telegram_document_caption_populates_message_text_and_plain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    document = create_mock_file("https://api.telegram.org/file/test/report.md")
    document.file_name = "report.md"
    mention = MagicMock(type="mention", offset=0, length=6)
    update = create_mock_update(
        message_text=None,
        document=document,
        caption="@alice 请总结这份文档",
        caption_entities=[mention],
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.message_str == "@alice 请总结这份文档"
    assert any(isinstance(component, Comp.File) for component in result.message)
    assert any(
        isinstance(component, Comp.Plain)
        and component.text == "@alice 请总结这份文档"
        for component in result.message
    )
    assert any(
        isinstance(component, Comp.At) and component.qq == "alice"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_video_caption_populates_message_text_and_plain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    video = create_mock_file("https://api.telegram.org/file/test/lesson.mp4")
    video.file_name = "lesson.mp4"
    update = create_mock_update(
        message_text=None,
        video=video,
        caption="这段视频讲了什么",
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.message_str == "这段视频讲了什么"
    assert any(isinstance(component, Comp.Video) for component in result.message)
    assert any(
        isinstance(component, Comp.Plain) and component.text == "这段视频讲了什么"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_voice_message_creates_record_component(tmp_path):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    voice = create_mock_file("https://api.telegram.org/file/test/voice.oga")
    update = create_mock_update(
        message_text=None,
        voice=voice,
    )
    wav_path = tmp_path / "voice.oga.wav"
    convert_message_globals = adapter.convert_message.__func__.__globals__

    with patch.dict(
        convert_message_globals,
        {
            "get_astrbot_temp_path": MagicMock(return_value=str(tmp_path)),
            "download_file": AsyncMock(),
            "convert_audio_to_wav": AsyncMock(return_value=str(wav_path)),
        },
    ):
        result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Record)
    assert result.message[0].file == str(wav_path)
    assert result.message[0].path == str(wav_path)
    assert result.message[0].url == str(wav_path)
