from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from astrbot.core.message.components import File, Plain, Video
from tests.fixtures.helpers import create_mock_file, create_mock_update
from tests.fixtures.mocks.telegram import MockTelegramBuilder

pytest_plugins = ("tests.fixtures.mocks.telegram",)


def _build_adapter():
    sys.modules["telegram.ext"].ContextTypes.DEFAULT_TYPE = object
    from astrbot.core.platform.sources.telegram.tg_adapter import (
        TelegramPlatformAdapter,
    )

    return TelegramPlatformAdapter(
        {"telegram_token": "test-token", "id": "telegram-test"},
        {},
        asyncio.Queue(),
    )


def _build_context():
    return SimpleNamespace(bot=MockTelegramBuilder.create_bot())


@pytest.mark.unit
def test_telegram_document_caption_populates_message_text_and_plain(
    mock_telegram_modules,  # noqa: ARG001
) -> None:
    adapter = _build_adapter()
    context = _build_context()

    document = create_mock_file("https://api.telegram.org/file/test.pdf")
    document.file_name = "test.pdf"
    update = create_mock_update(
        message_text=None,
        document=document,
        caption="document caption",
    )

    message = asyncio.run(adapter.convert_message(update, context))

    assert message is not None
    assert message.message_str == "document caption"
    assert any(isinstance(component, File) for component in message.message)
    assert any(
        isinstance(component, Plain) and component.text == "document caption"
        for component in message.message
    )


@pytest.mark.unit
def test_telegram_video_caption_populates_message_text_and_plain(
    mock_telegram_modules,  # noqa: ARG001
) -> None:
    adapter = _build_adapter()
    context = _build_context()

    video = create_mock_file("https://api.telegram.org/file/test.mp4")
    video.file_name = "test.mp4"
    update = create_mock_update(
        message_text=None,
        video=video,
        caption="video caption",
    )

    message = asyncio.run(adapter.convert_message(update, context))

    assert message is not None
    assert message.message_str == "video caption"
    assert any(isinstance(component, Video) for component in message.message)
    assert any(
        isinstance(component, Plain) and component.text == "video caption"
        for component in message.message
    )
