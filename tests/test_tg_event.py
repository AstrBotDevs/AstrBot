"""Verify Telegram chunking, keyboard placement, fallback and cancellation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from astrbot.core.platform.sources.telegram import tg_event as module


@pytest.mark.parametrize("length", [0, 1, 4096, 4097, 8195])
def test_split_message_preserves_text_and_respects_limit(length):
    text = "x" * length
    chunks = module.TelegramPlatformEvent._split_message(text)

    assert "".join(chunks) == text
    assert all(
        len(chunk) <= module.TelegramPlatformEvent.MAX_MESSAGE_LENGTH
        for chunk in chunks
    )
    assert len(chunks) == max(
        1,
        (length + module.TelegramPlatformEvent.MAX_MESSAGE_LENGTH - 1)
        // module.TelegramPlatformEvent.MAX_MESSAGE_LENGTH,
    )


@pytest.mark.asyncio
async def test_only_last_chunk_has_keyboard_and_payload_is_not_mutated(monkeypatch):
    monkeypatch.setattr(module.TelegramPlatformEvent, "MAX_MESSAGE_LENGTH", 4)
    monkeypatch.setattr(module.telegramify_markdown, "markdownify", lambda text: text)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Next", callback_data="next")]]
    )
    payload = {"chat_id": "42", "message_thread_id": 9, "reply_markup": keyboard}
    original = payload.copy()
    client = SimpleNamespace(send_message=AsyncMock())

    await module.TelegramPlatformEvent._send_text_chunks(client, "abcdefghij", payload)

    calls = client.send_message.await_args_list
    assert [call.kwargs["text"] for call in calls] == ["abcd", "efgh", "ij"]
    assert all(call.kwargs["parse_mode"] == "MarkdownV2" for call in calls)
    assert all(call.kwargs["chat_id"] == "42" for call in calls)
    assert all(call.kwargs["message_thread_id"] == 9 for call in calls)
    assert all("reply_markup" not in call.kwargs for call in calls[:-1])
    assert calls[-1].kwargs["reply_markup"] is keyboard
    assert payload == original


@pytest.mark.asyncio
async def test_bad_markdown_retries_once_with_original_text(monkeypatch):
    monkeypatch.setattr(
        module.telegramify_markdown, "markdownify", lambda text: "escaped"
    )
    client = SimpleNamespace(
        send_message=AsyncMock(side_effect=[BadRequest("invalid markdown"), None])
    )
    payload = {"chat_id": "42"}

    await module.TelegramPlatformEvent._send_text_chunks(client, "original", payload)

    assert [call.kwargs for call in client.send_message.await_args_list] == [
        {"text": "escaped", "parse_mode": "MarkdownV2", "chat_id": "42"},
        {"text": "original", "chat_id": "42"},
    ]
    assert payload == {"chat_id": "42"}


@pytest.mark.asyncio
async def test_cancelled_send_does_not_trigger_plain_text_retry(monkeypatch):
    monkeypatch.setattr(module.telegramify_markdown, "markdownify", lambda text: text)
    client = SimpleNamespace(send_message=AsyncMock(side_effect=asyncio.CancelledError))

    with pytest.raises(asyncio.CancelledError):
        await module.TelegramPlatformEvent._send_text_chunks(
            client, "cancel me", {"chat_id": "42"}
        )

    client.send_message.assert_awaited_once()
