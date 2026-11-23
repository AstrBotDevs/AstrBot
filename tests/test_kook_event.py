"""Exercise KOOK message wrapping without replacing its SDK modules."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import At, AtAll, Image, Json, Plain, Reply
from astrbot.core.platform.sources.kook.kook_event import KookEvent
from astrbot.core.platform.sources.kook.kook_types import KookMessageType


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "component,expected",
    [
        (Plain("hello"), "hello"),
        (At(qq="42"), "(met)42(met)"),
        (AtAll(), "(met)all(met)"),
    ],
)
async def test_wrap_text_preserves_order_and_avoids_upload(component, expected):
    event = KookEvent.__new__(KookEvent)
    upload = AsyncMock()
    event.client = SimpleNamespace(upload_asset=upload)

    wrapped = await event._wrap_message(3, component)

    assert wrapped.index == 3
    assert wrapped.type == KookMessageType.KMARKDOWN
    assert wrapped.text == expected
    upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_reply_reference_is_kept_out_of_message_text():
    event = KookEvent.__new__(KookEvent)

    wrapped = await event._wrap_message(0, Reply(id="message-1"))

    assert wrapped.reply_id == "message-1"
    assert wrapped.text == ""
    assert wrapped.index == 0


@pytest.mark.asyncio
async def test_json_card_uses_list_envelope_without_mutating_input():
    event = KookEvent.__new__(KookEvent)
    card = {"type": "card", "modules": []}

    wrapped = await event._wrap_message(2, Json(data=card))

    assert wrapped.type == KookMessageType.CARD
    assert json.loads(wrapped.text) == [card]
    assert card == {"type": "card", "modules": []}


@pytest.mark.asyncio
async def test_image_upload_retains_original_media_reference():
    event = KookEvent.__new__(KookEvent)
    upload = AsyncMock(return_value="https://cdn.example.test/image.gif")
    event.client = SimpleNamespace(upload_asset=upload)
    event._file_message_counter = 0
    image = Image.fromURL("https://origin.example.test/image.gif")

    wrapped = await event._wrap_message(1, image)

    upload.assert_awaited_once_with(image.file)
    assert wrapped.index == 1
    assert wrapped.type == KookMessageType.IMAGE
    assert wrapped.text == "https://cdn.example.test/image.gif"
    assert event._file_message_counter == 1
