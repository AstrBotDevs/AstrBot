"""Exercise nullable and platform-specific contracts with current Telegram objects."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import (
    Audio,
    CallbackQuery,
    Chat,
    ForumTopicCreated,
    InaccessibleMessage,
    Message,
    TextQuote,
    Update,
    User,
    Voice,
)
from telegram import File as TelegramFile

from astrbot.api.message_components import Reply
from astrbot.core.platform.button_interaction import encode_button_callback
from astrbot.core.platform.sources.telegram import tg_adapter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def adapter() -> tg_adapter.TelegramPlatformAdapter:
    """Exercise conversion without opening a polling connection or scheduler."""
    instance = object.__new__(tg_adapter.TelegramPlatformAdapter)
    instance._forum_topic_names = {}
    instance.handle_msg = AsyncMock()
    return instance


@pytest.fixture
def context() -> SimpleNamespace:
    return SimpleNamespace(
        bot=User(id=123456, first_name="Bot", is_bot=True, username="test_bot")
    )


def sender() -> User:
    return User(id=1001, first_name="Tester", is_bot=False, username="alice")


@pytest.mark.parametrize("media_type", [Voice, Audio])
@pytest.mark.parametrize("file_path", [None, ""])
async def test_unavailable_audio_file_does_not_dispatch_download_or_conversion(
    adapter: tg_adapter.TelegramPlatformAdapter,
    context: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    media_type: type[Voice] | type[Audio],
    file_path: str | None,
) -> None:
    media = media_type(file_id="media", file_unique_id="unique-media", duration=1)
    file = TelegramFile(
        file_id="media", file_unique_id="unique-media", file_path=file_path
    )
    get_file = AsyncMock(return_value=file)
    download = AsyncMock()
    convert = AsyncMock()
    monkeypatch.setattr(media_type, "get_file", get_file)
    monkeypatch.setattr(tg_adapter, "download_file", download)
    monkeypatch.setattr(tg_adapter.MediaResolver, "to_path", convert)
    message = Message(
        message_id=1,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        chat=Chat(id=1001, type="private"),
        from_user=sender(),
        voice=media if isinstance(media, Voice) else None,
        audio=media if isinstance(media, Audio) else None,
    )

    result = await adapter.convert_message(
        Update(update_id=1, message=message), context
    )

    assert result is not None
    assert result.message == []
    assert result.message_str == ""
    get_file.assert_awaited_once()
    download.assert_not_awaited()
    convert.assert_not_awaited()


@pytest.mark.parametrize("accessible", [False, True])
async def test_callback_topic_only_uses_available_thread_metadata(
    adapter: tg_adapter.TelegramPlatformAdapter,
    context: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    accessible: bool,
) -> None:
    chat = Chat(id=-100123, type="supergroup", is_forum=True)
    source = (
        Message(
            message_id=77,
            date=datetime(2026, 1, 1, tzinfo=UTC),
            chat=chat,
            message_thread_id=42,
            is_topic_message=True,
        )
        if accessible
        else InaccessibleMessage(chat=chat, message_id=77)
    )
    query = CallbackQuery(
        id="callback-1",
        from_user=sender(),
        chat_instance="group",
        message=source,
        data=encode_button_callback("approve"),
    )
    answer = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)

    await adapter.callback_query_handler(
        Update(update_id=1, callback_query=query), context
    )

    answer.assert_awaited_once_with()
    adapter.handle_msg.assert_awaited_once()
    delivered = adapter.handle_msg.await_args.args[0]
    assert delivered.group_id == ("-100123#42" if accessible else "-100123")
    assert delivered.session_id == delivered.group_id
    assert delivered.message[0].source_message_id == "77"


async def test_topic_metadata_survives_conversion_on_platform_message(
    adapter: tg_adapter.TelegramPlatformAdapter, context: SimpleNamespace
) -> None:
    message = Message(
        message_id=77,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        chat=Chat(id=-100123, type="supergroup", is_forum=True, title="Engineering"),
        from_user=sender(),
        text="question",
        message_thread_id=42,
        is_topic_message=True,
        forum_topic_created=ForumTopicCreated(name="Backend", icon_color=0),
    )

    result = await adapter.convert_message(
        Update(update_id=1, message=message), context
    )

    assert isinstance(result, tg_adapter.TelegramMessage)
    assert result._telegram_topic_name == "Backend"
    assert result.group is not None
    assert result.group.group_id == "-100123#42"
    assert result.group.group_name == "Engineering-Backend"


@pytest.mark.parametrize("quoted", [False, True])
async def test_optional_quote_keeps_reply_text_and_exact_selected_span(
    adapter: tg_adapter.TelegramPlatformAdapter,
    context: SimpleNamespace,
    quoted: bool,
) -> None:
    chat = Chat(id=1001, type="private")
    original = Message(
        message_id=11,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        chat=chat,
        from_user=sender(),
        text="first quoted last",
    )
    message = Message(
        message_id=12,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        chat=chat,
        from_user=sender(),
        text="follow up",
        reply_to_message=original,
        quote=TextQuote(text="quoted", position=6) if quoted else None,
    )

    result = await adapter.convert_message(
        Update(update_id=2, message=message), context
    )

    assert result is not None
    reply = result.message[0]
    assert isinstance(reply, Reply)
    assert reply.id == "11"
    assert reply.message_str == ("quoted" if quoted else "first quoted last")
