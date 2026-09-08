import asyncio
import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.platform import Group
from astrbot.core.platform.register import unregister_platform_adapters_by_module
from tests.fixtures.helpers import (
    NoopAwaitable,
    create_mock_file,
    create_mock_update,
    make_platform_config,
)
from tests.fixtures.mocks.telegram import (
    MockTelegramBuilder,
    MockTelegramNetworkError,
    create_mock_telegram_modules,
)

_TELEGRAM_PLATFORM_ADAPTER = None
_TELEGRAM_PLATFORM_EVENT = None
_TELEGRAM_MODULES: dict[str, object] = {}


def _build_telegram_patched_modules():
    mocks = create_mock_telegram_modules()
    return {
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


def _load_telegram_module(module_name: str):
    module = _TELEGRAM_MODULES.get(module_name)
    if module is not None:
        return module

    with patch.dict(sys.modules, _build_telegram_patched_modules()):
        if module_name == "astrbot.core.platform.sources.telegram.tg_adapter":
            unregister_platform_adapters_by_module(module_name)
        sys.modules.pop(module_name, None)
        module = importlib.import_module(module_name)

    sys.modules[module_name] = module
    _TELEGRAM_MODULES[module_name] = module
    return module


def _load_telegram_adapter():
    global _TELEGRAM_PLATFORM_ADAPTER
    if _TELEGRAM_PLATFORM_ADAPTER is not None:
        return _TELEGRAM_PLATFORM_ADAPTER

    module = _load_telegram_module("astrbot.core.platform.sources.telegram.tg_adapter")
    _TELEGRAM_PLATFORM_ADAPTER = module.TelegramPlatformAdapter
    return _TELEGRAM_PLATFORM_ADAPTER


def _load_telegram_platform_event():
    global _TELEGRAM_PLATFORM_EVENT
    if _TELEGRAM_PLATFORM_EVENT is not None:
        return _TELEGRAM_PLATFORM_EVENT

    module = _load_telegram_module("astrbot.core.platform.sources.telegram.tg_event")
    _TELEGRAM_PLATFORM_EVENT = module.TelegramPlatformEvent
    return _TELEGRAM_PLATFORM_EVENT


def _build_context() -> MagicMock:
    context = MagicMock()
    context.bot.username = "test_bot"
    context.bot.id = 12345678
    return context


@pytest.mark.asyncio
async def test_telegram_topic_with_missing_name_falls_back_to_group_name():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    update.message.chat.title = "Engineering"

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group is not None
    assert result.group.group_id == "-100123#42"
    assert result.group.group_name == "Engineering"


@pytest.mark.asyncio
async def test_telegram_regular_supergroup_message_uses_group_name():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(chat_type="supergroup", chat_id=-100123)
    update.message.chat.title = "Engineering"
    update.message.chat.is_forum = False

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group is not None
    assert result.group.group_id == "-100123"
    assert result.group.group_name == "Engineering"


@pytest.mark.asyncio
async def test_telegram_forum_topic_name_is_learned_and_updated_from_events():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    created_update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    created_update.message.chat.title = "Engineering"
    created_update.message.chat.is_forum = True
    created_update.message.forum_topic_created = SimpleNamespace(name="Backend")

    created = await adapter.convert_message(created_update, _build_context())

    assert created is not None
    assert created.group is not None
    assert created.group.group_name == "Engineering-Backend"

    regular_update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    regular_update.message.chat.title = "Engineering"
    regular_update.message.chat.is_forum = True

    regular = await adapter.convert_message(regular_update, _build_context())

    assert regular is not None
    assert regular.group is not None
    assert regular.group.group_name == "Engineering-Backend"

    empty_edit_update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    empty_edit_update.message.chat.title = "Engineering"
    empty_edit_update.message.chat.is_forum = True
    empty_edit_update.message.forum_topic_edited = SimpleNamespace(name="   ")

    empty_edit = await adapter.convert_message(empty_edit_update, _build_context())

    assert empty_edit is not None
    assert empty_edit.group is not None
    assert empty_edit.group.group_name == "Engineering-Backend"

    edited_update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    edited_update.message.chat.title = "Engineering"
    edited_update.message.chat.is_forum = True
    edited_update.message.forum_topic_edited = SimpleNamespace(name="Platform")

    edited = await adapter.convert_message(edited_update, _build_context())

    assert edited is not None
    assert edited.group is not None
    assert edited.group.group_name == "Engineering-Platform"


@pytest.mark.asyncio
async def test_telegram_forum_topic_cache_evicts_oldest_entry():
    TelegramPlatformAdapter = _load_telegram_adapter()
    assert TelegramPlatformAdapter._FORUM_TOPIC_NAME_CACHE_MAX_SIZE == 1000
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter._FORUM_TOPIC_NAME_CACHE_MAX_SIZE = 2

    for thread_id, topic_name in [(41, "One"), (42, "Two"), (43, "Three")]:
        update = create_mock_update(
            chat_type="supergroup",
            chat_id=-100123,
            message_thread_id=thread_id,
            is_topic_message=True,
        )
        update.message.chat.title = "Engineering"
        update.message.chat.is_forum = True
        update.message.forum_topic_created = SimpleNamespace(name=topic_name)
        await adapter.convert_message(update, _build_context())

    assert list(adapter._forum_topic_names) == [("-100123", 42), ("-100123", 43)]


@pytest.mark.asyncio
async def test_telegram_forum_topic_name_is_read_from_topic_root_reply():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    topic_root = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_id=42,
    ).message
    topic_root.forum_topic_created = SimpleNamespace(name="Backend")
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
        reply_to_message=topic_root,
    )
    update.message.chat.title = "Engineering"
    update.message.chat.is_forum = True

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group is not None
    assert result.group.group_name == "Engineering-Backend"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_thread_id", "is_topic_message"),
    [(None, False), (1, True)],
)
async def test_telegram_general_forum_topic_without_known_name_uses_group_name(
    message_thread_id, is_topic_message
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=message_thread_id,
        is_topic_message=is_topic_message,
    )
    update.message.chat.title = "Engineering"
    update.message.chat.is_forum = True

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group is not None
    assert result.group.group_id == "-100123"
    assert result.group.group_name == "Engineering"


@pytest.mark.asyncio
async def test_telegram_general_forum_topic_uses_observed_custom_name():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    edited_update = create_mock_update(chat_type="supergroup", chat_id=-100123)
    edited_update.message.chat.title = "Engineering"
    edited_update.message.chat.is_forum = True
    edited_update.message.forum_topic_edited = SimpleNamespace(name="Lobby")

    edited = await adapter.convert_message(edited_update, _build_context())

    assert edited is not None
    assert edited.group is not None
    assert edited.group.group_name == "Engineering-Lobby"

    regular_update = create_mock_update(chat_type="supergroup", chat_id=-100123)
    regular_update.message.chat.title = "Engineering"
    regular_update.message.chat.is_forum = True

    regular = await adapter.convert_message(regular_update, _build_context())

    assert regular is not None
    assert regular.group is not None
    assert regular.group.group_name == "Engineering-Lobby"


@pytest.mark.asyncio
async def test_telegram_get_group_keeps_forum_topic_name():
    TelegramPlatformAdapter = _load_telegram_adapter()
    TelegramPlatformEvent = _load_telegram_platform_event()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-100123,
        message_thread_id=42,
        is_topic_message=True,
    )
    update.message.chat.title = "Engineering"
    update.message.chat.is_forum = True
    update.message.forum_topic_created = SimpleNamespace(name="Backend")
    message = await adapter.convert_message(update, _build_context())
    assert message is not None

    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = message
    event.client = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(title="Engineering 2", photo=None)
        ),
        get_chat_member_count=AsyncMock(return_value=24),
        get_chat_administrators=AsyncMock(return_value=[]),
    )

    group = await event.get_group()

    assert group is not None
    assert group.group_name == "Engineering 2-Backend"


@pytest.mark.asyncio
async def test_telegram_get_group_enriches_available_metadata():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                title="Engineering",
                photo=SimpleNamespace(big_file_id="photo-1"),
            )
        ),
        get_file=AsyncMock(
            return_value=SimpleNamespace(
                file_path="https://api.telegram.org/file/group.jpg"
            )
        ),
        get_chat_member_count=AsyncMock(return_value=24),
        get_chat_administrators=AsyncMock(
            return_value=[
                SimpleNamespace(status="creator", user=SimpleNamespace(id=1)),
                SimpleNamespace(status="administrator", user=SimpleNamespace(id=2)),
            ]
        ),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123#42", group_name="Cached title"),
        group_id="-100123#42",
    )
    event.client = client

    group = await event.get_group()

    assert group is not None
    assert group.group_id == "-100123#42"
    assert group.group_name == "Engineering"
    assert group.group_avatar == "https://api.telegram.org/file/group.jpg"
    assert group.member_count == 24
    assert group.group_owner == "1"
    assert group.group_admins == ["2"]
    assert group.members is None
    client.get_chat.assert_awaited_once_with(chat_id=-100123)
    client.get_chat_member_count.assert_awaited_once_with(chat_id=-100123)
    client.get_chat_administrators.assert_awaited_once_with(chat_id=-100123)


@pytest.mark.asyncio
async def test_telegram_get_group_keeps_basic_metadata_when_apis_fail():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        get_chat=AsyncMock(side_effect=RuntimeError("chat unavailable")),
        get_chat_member_count=AsyncMock(side_effect=RuntimeError("count unavailable")),
        get_chat_administrators=AsyncMock(
            side_effect=RuntimeError("administrators unavailable")
        ),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123#42", group_name="Cached title"),
        group_id="-100123#42",
    )
    event.client = client

    group = await event.get_group()

    assert group == Group(group_id="-100123#42", group_name="Cached title")


@pytest.mark.asyncio
async def test_telegram_partial_quote_uses_exact_quote_text():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    original_text = "😀 prefix target suffix"
    quoted_text = "target"
    reply_update = create_mock_update(
        message_text=original_text,
        message_id=42,
        user_id=1001,
        username="original_sender",
    )
    quote = MagicMock(text=quoted_text, position=10)
    update = create_mock_update(
        message_text="What does this mean?",
        reply_to_message=reply_update.message,
        quote=quote,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    reply = result.message[0]
    assert isinstance(reply, Comp.Reply)
    assert reply.id == "42"
    assert reply.message_str == quoted_text
    assert reply.text == quoted_text
    assert reply.chain is not None
    assert len(reply.chain) == 1
    assert isinstance(reply.chain[0], Comp.Plain)
    assert reply.chain[0].text == quoted_text


@pytest.mark.asyncio
@pytest.mark.parametrize("quote_text", [None, ""])
async def test_telegram_reply_without_quote_text_uses_full_message(quote_text):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    original_text = "Use the complete replied message"
    reply_update = create_mock_update(
        message_text=original_text,
        message_id=43,
        user_id=1002,
        username="original_sender",
    )
    quote = MagicMock(text=quote_text) if quote_text is not None else None
    update = create_mock_update(
        message_text="Follow-up question",
        reply_to_message=reply_update.message,
        quote=quote,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    reply = result.message[0]
    assert isinstance(reply, Comp.Reply)
    assert reply.message_str == original_text
    assert reply.text == original_text
    assert reply.chain is not None
    assert len(reply.chain) == 1
    assert isinstance(reply.chain[0], Comp.Plain)
    assert reply.chain[0].text == original_text


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
        isinstance(component, Comp.Plain) and component.text == "@alice 请总结这份文档"
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


_STICKER_URL = "https://api.telegram.org/file/test/sticker_1.webp"
_ANIMATED_URL = "https://api.telegram.org/file/test/sticker_1.tgs"
_VIDEO_URL = "https://api.telegram.org/file/test/sticker_1.webm"
_THUMBNAIL_URL = "https://api.telegram.org/file/test/thumb_1.webp"


def _make_sticker(
    file_path: str,
    *,
    is_animated: bool = False,
    is_video: bool = False,
    thumbnail_path: str | None = None,
):
    sticker = create_mock_file(file_path)
    sticker.emoji = "🙄"
    sticker.is_animated = is_animated
    sticker.is_video = is_video
    sticker.thumbnail = (
        create_mock_file(thumbnail_path) if thumbnail_path is not None else None
    )
    return sticker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_path", "flags", "expected_url"),
    [
        (_STICKER_URL, {}, _STICKER_URL),
        (_ANIMATED_URL, {"is_animated": True}, _THUMBNAIL_URL),
        (_VIDEO_URL, {"is_video": True}, _THUMBNAIL_URL),
    ],
    ids=["static", "animated", "video"],
)
async def test_telegram_sticker_uses_thumbnail_only_when_animated(
    file_path, flags, expected_url
):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    sticker = _make_sticker(file_path, thumbnail_path=_THUMBNAIL_URL, **flags)
    update = create_mock_update(message_text=None, sticker=sticker)

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    images = [c for c in result.message if isinstance(c, Comp.Image)]
    assert len(images) == 1
    assert images[0].url == expected_url
    assert result.message_str == "Sticker: 🙄"


@pytest.mark.asyncio
async def test_telegram_animated_sticker_without_thumbnail_skips_image():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    sticker = _make_sticker(_ANIMATED_URL, is_animated=True, thumbnail_path=None)
    update = create_mock_update(message_text=None, sticker=sticker)

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert not any(isinstance(c, Comp.Image) for c in result.message)
    assert result.message_str == "Sticker: 🙄"


@pytest.mark.asyncio
async def test_telegram_video_note_becomes_video_component():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    file_path = "https://api.telegram.org/file/test/note.mp4"
    update = create_mock_update(
        message_text=None,
        video_note=create_mock_file(file_path),
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Video)
    assert result.message[0].file == file_path
    assert result.message[0].path == file_path


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

    with (
        patch.dict(
            convert_message_globals,
            {
                "get_astrbot_temp_path": MagicMock(return_value=str(tmp_path)),
                "download_file": AsyncMock(),
            },
        ),
        patch(
            "astrbot.core.utils.media_utils.ensure_wav",
            AsyncMock(return_value=str(wav_path)),
        ),
    ):
        result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Record)
    assert result.message[0].file == str(wav_path)
    assert result.message[0].path == str(wav_path)
    assert result.message[0].url == str(wav_path)


@pytest.mark.asyncio
async def test_telegram_audio_caption_populates_message_text_and_plain(tmp_path):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    audio = create_mock_file("https://api.telegram.org/file/test/song.mp3")
    update = create_mock_update(
        message_text=None,
        audio=audio,
        caption="这首歌是什么",
    )
    wav_path = tmp_path / "song.mp3.wav"
    convert_message_globals = adapter.convert_message.__func__.__globals__

    with (
        patch.dict(
            convert_message_globals,
            {
                "get_astrbot_temp_path": MagicMock(return_value=str(tmp_path)),
                "download_file": AsyncMock(),
            },
        ),
        patch(
            "astrbot.core.utils.media_utils.ensure_wav",
            AsyncMock(return_value=str(wav_path)),
        ),
    ):
        result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.message_str == "这首歌是什么"
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.Record)
    assert result.message[0].file == str(wav_path)
    assert result.message[0].path == str(wav_path)
    assert result.message[0].url == str(wav_path)
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message[1].text == "这首歌是什么"


@pytest.mark.asyncio
async def test_telegram_final_segment_splits_long_markdown_messages():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MagicMock()
    client.send_message = AsyncMock()
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)

    delta = "A" * (TelegramPlatformEvent.MAX_MESSAGE_LENGTH + 32)
    payload = {"chat_id": "123456"}

    await event._send_final_segment(delta, payload)

    assert client.send_message.await_count == 2
    first_call = client.send_message.await_args_list[0].kwargs
    second_call = client.send_message.await_args_list[1].kwargs
    assert len(first_call["text"]) == TelegramPlatformEvent.MAX_MESSAGE_LENGTH
    assert len(second_call["text"]) == 32
    assert first_call["parse_mode"] == "MarkdownV2"
    assert second_call["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_telegram_final_segment_splits_long_plaintext_when_markdown_fails():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MagicMock()
    client.send_message = AsyncMock()
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)

    delta = "B" * (TelegramPlatformEvent.MAX_MESSAGE_LENGTH + 18)
    payload = {"chat_id": "123456"}

    with patch(
        "astrbot.core.platform.sources.telegram.tg_event.telegramify_markdown.markdownify",
        side_effect=Exception("boom"),
    ):
        await event._send_final_segment(delta, payload)

    assert client.send_message.await_count == 2
    first_call = client.send_message.await_args_list[0].kwargs
    second_call = client.send_message.await_args_list[1].kwargs
    assert len(first_call["text"]) == TelegramPlatformEvent.MAX_MESSAGE_LENGTH
    assert len(second_call["text"]) == 18
    assert "parse_mode" not in first_call
    assert "parse_mode" not in second_call


@pytest.mark.asyncio
async def test_telegram_polling_error_requests_rebuild_after_threshold():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter._loop = asyncio.get_running_loop()

    assert not adapter._polling_recovery_requested.is_set()

    for _ in range(adapter._polling_recovery_threshold):
        adapter._on_polling_error(MockTelegramNetworkError("proxy disconnected"))

    await asyncio.sleep(0)

    assert adapter._polling_recovery_requested.is_set()


@pytest.mark.asyncio
async def test_telegram_run_rebuilds_application_after_repeated_polling_errors():
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__
    app_one = MockTelegramBuilder.create_application()
    app_one.updater.running = True
    app_two = MockTelegramBuilder.create_application()
    app_two.updater.running = True
    created_apps = [app_one, app_two]

    builder = MagicMock()
    builder.token.return_value = builder
    builder.base_url.return_value = builder
    builder.base_file_url.return_value = builder
    builder.build.side_effect = created_apps

    adapter = None

    def start_polling_side_effect(*args, **kwargs):
        nonlocal adapter
        error_callback = kwargs["error_callback"]
        assert adapter is not None

        async def _emit_errors():
            await asyncio.sleep(0)
            for _ in range(adapter._polling_recovery_threshold):
                error_callback(MockTelegramNetworkError("proxy disconnected"))

        asyncio.create_task(_emit_errors())
        return NoopAwaitable()

    app_one.updater.start_polling.side_effect = start_polling_side_effect

    async def second_start_polling(*args, **kwargs):
        assert adapter is not None
        adapter._terminating = True

    app_two.updater.start_polling.side_effect = second_start_polling

    with patch.dict(
        module_globals,
        {
            "ApplicationBuilder": MagicMock(return_value=builder),
            "AsyncIOScheduler": MagicMock(
                return_value=MockTelegramBuilder.create_scheduler()
            ),
        },
    ):
        adapter = TelegramPlatformAdapter(
            make_platform_config("telegram"),
            {},
            asyncio.Queue(),
        )
        await adapter.run()

    assert builder.build.call_count == 2
    app_one.updater.stop.assert_awaited()
    app_one.bot.delete_my_commands.assert_not_awaited()
    app_one.stop.assert_awaited()
    app_one.shutdown.assert_awaited()
    app_two.initialize.assert_awaited()
    app_two.start.assert_awaited()


@pytest.mark.asyncio
async def test_telegram_recreate_application_is_skipped_during_termination():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter._terminating = True
    adapter._polling_recovery_requested.set()

    await adapter._recreate_application()

    assert not adapter._polling_recovery_requested.is_set()


@pytest.mark.asyncio
async def test_telegram_run_rebuilds_fresh_application_after_recreate_init_failure():
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__
    app_one = MockTelegramBuilder.create_application()
    app_one.updater.running = True
    app_two = MockTelegramBuilder.create_application()
    app_three = MockTelegramBuilder.create_application()
    app_three.updater.running = True
    created_apps = [app_one, app_two, app_three]

    builder = MagicMock()
    builder.token.return_value = builder
    builder.base_url.return_value = builder
    builder.base_file_url.return_value = builder
    builder.build.side_effect = created_apps

    adapter = None

    def first_start_polling(*args, **kwargs):
        nonlocal adapter
        error_callback = kwargs["error_callback"]
        assert adapter is not None

        async def _emit_errors():
            await asyncio.sleep(0)
            for _ in range(adapter._polling_recovery_threshold):
                error_callback(MockTelegramNetworkError("proxy disconnected"))

        asyncio.create_task(_emit_errors())
        return NoopAwaitable()

    app_one.updater.start_polling.side_effect = first_start_polling
    app_two.initialize.side_effect = TimeoutError("init timeout")

    async def final_start_polling(*args, **kwargs):
        assert adapter is not None
        adapter._terminating = True

    app_three.updater.start_polling.side_effect = final_start_polling

    with patch.dict(
        module_globals,
        {
            "ApplicationBuilder": MagicMock(return_value=builder),
            "AsyncIOScheduler": MagicMock(
                return_value=MockTelegramBuilder.create_scheduler()
            ),
        },
    ):
        adapter = TelegramPlatformAdapter(
            make_platform_config(
                "telegram",
                telegram_polling_restart_delay=0.1,
            ),
            {},
            asyncio.Queue(),
        )
        await adapter.run()

    assert builder.build.call_count == 3
    app_two.stop.assert_awaited()
    app_two.shutdown.assert_awaited()
    app_three.initialize.assert_awaited()
    app_three.start.assert_awaited()
