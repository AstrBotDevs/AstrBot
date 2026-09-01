import asyncio
import importlib
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.core.platform import Group
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.star import PluginRegistry, StarMetadata
from astrbot.core.star.star_handler import (
    EventType,
    HandlerRegistry,
    StarHandlerMetadata,
)
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

pytestmark = pytest.mark.platform


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


def _bind_runtime_registries(adapter) -> tuple[HandlerRegistry, PluginRegistry]:
    plugins = PluginRegistry()
    handlers = HandlerRegistry(plugins)
    adapter.bind_runtime_registries(handlers, plugins)
    return handlers, plugins


@pytest.mark.asyncio
async def test_telegram_partial_quote_uses_exact_quote_text():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    reply_update = create_mock_update(
        message_text="😀 prefix target suffix",
        message_id=42,
        user_id=1001,
        username="original_sender",
    )
    update = create_mock_update(
        message_text="What does this mean?",
        reply_to_message=reply_update.message,
        quote=MagicMock(text="target", position=10),
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    reply = result.message[0]
    assert isinstance(reply, Comp.Reply)
    assert reply.id == "42"
    assert reply.message_str == "target"
    assert reply.text == "target"
    assert reply.chain is not None
    assert len(reply.chain) == 1
    assert isinstance(reply.chain[0], Comp.Plain)
    assert reply.chain[0].text == "target"


@pytest.mark.asyncio
@pytest.mark.parametrize("quote_text", [None, ""])
async def test_telegram_reply_without_quote_text_uses_full_message(quote_text):
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    reply_update = create_mock_update(
        message_text="Use the complete replied message",
        message_id=43,
        user_id=1002,
        username="original_sender",
    )
    update = create_mock_update(
        message_text="Follow-up question",
        reply_to_message=reply_update.message,
        quote=MagicMock(text=quote_text) if quote_text is not None else None,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    reply = result.message[0]
    assert isinstance(reply, Comp.Reply)
    assert reply.message_str == "Use the complete replied message"
    assert reply.text == "Use the complete replied message"
    assert reply.chain is not None
    assert len(reply.chain) == 1
    assert isinstance(reply.chain[0], Comp.Plain)
    assert reply.chain[0].text == "Use the complete replied message"


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
    file_component = next(
        component for component in result.message if isinstance(component, Comp.File)
    )
    assert file_component.url == ""
    document.get_file.assert_not_awaited()
    assert await file_component.get_file(allow_return_url=True) == (
        "https://api.telegram.org/file/test/report.md"
    )
    document.get_file.assert_awaited_once()
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
    video_component = next(
        component for component in result.message if isinstance(component, Comp.Video)
    )
    assert video_component.file == ""
    video.get_file.assert_not_awaited()
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
    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Record)
    assert result.message[0].file == ""
    assert result.message[0].url == ""
    voice.get_file.assert_not_awaited()

    media_resolver = MagicMock()
    media_resolver.to_path = AsyncMock(return_value=str(wav_path))
    with patch(
        "astrbot.core.message.components.MediaResolver",
        MagicMock(return_value=media_resolver),
    ):
        resolved_path = await result.message[0].convert_to_file_path()

    assert resolved_path == str(wav_path)
    voice.get_file.assert_awaited_once()
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")
    assert result.message[0].url == "https://api.telegram.org/file/test/voice.oga"


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
    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.message_str == "这首歌是什么"
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.Record)
    assert result.message[0].file == ""
    assert result.message[0].url == ""
    audio.get_file.assert_not_awaited()
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message[1].text == "这首歌是什么"

    media_resolver = MagicMock()
    media_resolver.to_path = AsyncMock(return_value=str(wav_path))
    with patch(
        "astrbot.core.message.components.MediaResolver",
        MagicMock(return_value=media_resolver),
    ):
        resolved_path = await result.message[0].convert_to_file_path()

    assert resolved_path == str(wav_path)
    audio.get_file.assert_awaited_once()
    media_resolver.to_path.assert_awaited_once_with(target_format="wav")
    assert result.message[0].url == "https://api.telegram.org/file/test/song.mp3"


@pytest.mark.asyncio
async def test_telegram_topic_group_message_uses_thread_scoped_session():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update(
        chat_type="supergroup",
        chat_id=-1001234567890,
        message_thread_id=42,
        is_topic_message=True,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group_id == "-1001234567890#42"
    assert result.session_id == "-1001234567890#42"
    assert result.message_str == "Hello World"


@pytest.mark.asyncio
async def test_telegram_group_reply_to_bot_rewrites_text_as_direct_wake():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.username = "test_bot"
    reply_to_bot = create_mock_update(
        message_text="earlier reply",
        chat_type="group",
        chat_id=-10001,
        user_id=12345678,
        username="test_bot",
        message_id=22,
    ).message
    update = create_mock_update(
        message_text="summarize this",
        chat_type="group",
        chat_id=-10001,
        reply_to_message=reply_to_bot,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.message_str == "/ summarize this"
    assert isinstance(result.message[0], Comp.Reply)
    assert any(
        isinstance(component, Comp.Plain) and component.text == "/ summarize this"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_convert_message_with_get_reply_false_skips_reply_chain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    reply_to_message = create_mock_update(
        message_text="quoted",
        chat_type="group",
        chat_id=-10001,
        user_id=200,
        username="quoted_user",
        message_id=22,
    ).message
    update = create_mock_update(
        message_text="current",
        chat_type="group",
        chat_id=-10001,
        reply_to_message=reply_to_message,
    )

    result = await adapter.convert_message(update, _build_context(), get_reply=False)

    assert result is not None
    assert not any(isinstance(component, Comp.Reply) for component in result.message)
    assert result.message_str == "current"


@pytest.mark.asyncio
async def test_telegram_group_command_strips_only_current_bot_mention():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.username = "test_bot"
    context = _build_context()
    context.bot.username = "test_bot"
    mention = MagicMock(type="mention", offset=4, length=9)
    update = create_mock_update(
        message_text="/ask@test_bot hi",
        chat_type="group",
        chat_id=-10001,
        entities=[mention],
    )

    result = await adapter.convert_message(update, context)

    assert result is not None
    assert result.message_str == "/ask hi"
    assert any(
        isinstance(component, Comp.At) and component.qq == "test_bot"
        for component in result.message
    )
    assert any(
        isinstance(component, Comp.Plain) and component.text == "/ask hi"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_group_command_keeps_other_bot_mentions():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.username = "test_bot"
    context = _build_context()
    context.bot.username = "test_bot"
    mention = MagicMock(type="mention", offset=5, length=10)
    update = create_mock_update(
        message_text="ping @other_bot",
        chat_type="group",
        chat_id=-10001,
        entities=[mention],
    )

    result = await adapter.convert_message(update, context)

    assert result is not None
    assert result.message_str == "ping @other_bot"
    assert any(
        isinstance(component, Comp.At) and component.qq == "other_bot"
        for component in result.message
    )
    assert any(
        isinstance(component, Comp.Plain) and component.text == "ping @other_bot"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_topic_reply_to_thread_marker_does_not_create_reply_component():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    thread_marker = create_mock_update(
        message_text="topic marker",
        chat_type="supergroup",
        chat_id=-10001,
        message_id=42,
    ).message
    update = create_mock_update(
        message_text="topic reply",
        chat_type="supergroup",
        chat_id=-10001,
        message_thread_id=42,
        is_topic_message=True,
        reply_to_message=thread_marker,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert result.group_id == "-10001#42"
    assert not any(isinstance(component, Comp.Reply) for component in result.message)
    assert any(
        isinstance(component, Comp.Plain) and component.text == "topic reply"
        for component in result.message
    )


@pytest.mark.asyncio
async def test_telegram_document_with_missing_file_path_does_not_append_caption_plain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    document = create_mock_file(None)
    document.file_name = "report.md"
    update = create_mock_update(
        message_text=None,
        document=document,
        caption="ignored caption",
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.File)
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message_str == "ignored caption"
    assert await result.message[0].get_file(allow_return_url=True) == ""


@pytest.mark.asyncio
async def test_telegram_video_with_missing_file_path_does_not_append_caption_plain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    video = create_mock_file(None)
    video.file_name = "lesson.mp4"
    update = create_mock_update(
        message_text=None,
        video=video,
        caption="ignored caption",
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.Video)
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message_str == "ignored caption"
    with pytest.raises(Exception, match="not a valid file"):
        await result.message[0].convert_to_file_path()


@pytest.mark.asyncio
async def test_telegram_sticker_with_emoji_adds_image_and_plain_text():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    sticker = create_mock_file("https://api.telegram.org/file/test/sticker.webp")
    sticker.emoji = "🙂"
    update = create_mock_update(
        message_text=None,
        sticker=sticker,
    )

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert isinstance(result.message[0], Comp.Image)
    assert result.message[0].file == ""
    assert result.message[0].url == ""
    sticker.get_file.assert_not_awaited()
    assert result.message_str == "Sticker: 🙂"
    assert any(
        isinstance(component, Comp.Plain) and component.text == "Sticker: 🙂"
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
    assert images[0].file == ""
    assert images[0].url == ""
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
    video_note = create_mock_file("https://api.telegram.org/file/test/note.mp4")
    update = create_mock_update(message_text=None, video_note=video_note)

    result = await adapter.convert_message(update, _build_context())

    assert result is not None
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Video)
    assert result.message[0].file == ""
    assert result.message[0].url == ""
    video_note.get_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_start_command_sends_welcome_and_returns_none():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram", start_message="hello start"),
        {},
        asyncio.Queue(),
    )
    context = _build_context()
    context.bot.send_message = AsyncMock()
    update = create_mock_update(message_text="/start")

    result = await adapter.convert_message(update, context)

    assert result is None
    context.bot.send_message.assert_awaited_once_with(
        chat_id=update.effective_chat.id,
        text="hello start",
    )


@pytest.mark.asyncio
async def test_telegram_convert_message_returns_none_without_sender():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = create_mock_update()
    update.message.from_user = None

    result = await adapter.convert_message(update, _build_context())

    assert result is None


@pytest.mark.asyncio
async def test_telegram_register_commands_updates_commands_only_when_hash_changes():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.delete_my_commands = AsyncMock()
    adapter.client.set_my_commands = AsyncMock()
    command = SimpleNamespace(command="ask", description="Ask something")
    adapter.collect_commands = MagicMock(return_value=[command])

    await adapter.register_commands()
    await adapter.register_commands()

    adapter.client.delete_my_commands.assert_awaited_once()
    adapter.client.set_my_commands.assert_awaited_once_with([command])
    assert adapter._last_command_snapshot == (("ask", "Ask something"),)


@pytest.mark.asyncio
async def test_telegram_register_commands_clears_stale_menu_when_no_commands():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.delete_my_commands = AsyncMock()
    adapter.client.set_my_commands = AsyncMock()
    adapter.collect_commands = MagicMock(return_value=[])

    await adapter.register_commands()
    await adapter.register_commands()

    adapter.client.delete_my_commands.assert_awaited_once()
    adapter.client.set_my_commands.assert_not_awaited()
    assert adapter._last_command_snapshot == ()


@pytest.mark.asyncio
async def test_telegram_native_command_refresh_requires_started_application():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.register_commands = AsyncMock()

    await adapter.refresh_registered_commands()
    adapter.register_commands.assert_not_awaited()

    adapter._application_started = True
    await adapter.refresh_registered_commands()
    adapter.register_commands.assert_awaited_once()


def test_telegram_collect_commands_filters_duplicates_invalid_and_inactive_handlers():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    handlers, plugins = _bind_runtime_registries(adapter)
    for metadata in (
        StarMetadata(
            name="Alpha",
            module_path="plugin.alpha",
            activated=True,
        ),
        StarMetadata(
            name="Beta",
            module_path="plugin.beta",
            activated=True,
        ),
        StarMetadata(
            name="Off",
            module_path="plugin.off",
            activated=False,
        ),
    ):
        plugins.publish(metadata)

    async def handler_alpha(event):
        return None

    async def handler_beta(event):
        return None

    async def handler_invalid(event):
        return None

    async def handler_off(event):
        return None

    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.alpha_handler_alpha",
            handler_name="handler_alpha",
            handler_module_path="plugin.alpha",
            handler=handler_alpha,
            event_filters=[
                CommandFilter("ask", alias={"ask_alias"}),
                CommandFilter("child", parent_command_names=["root"]),
            ],
            desc="Primary ask command",
            enabled=True,
        )
    )
    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.beta_handler_beta",
            handler_name="handler_beta",
            handler_module_path="plugin.beta",
            handler=handler_beta,
            event_filters=[
                CommandFilter("ask"),
                CommandGroupFilter("tools", alias={"toolbox"}),
            ],
            desc="Duplicate ask command should lose",
            enabled=True,
        )
    )
    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.beta_handler_invalid",
            handler_name="handler_invalid",
            handler_module_path="plugin.beta",
            handler=handler_invalid,
            event_filters=[CommandFilter("Bad-Name")],
            desc="Should be filtered out",
            enabled=True,
        )
    )
    handlers.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name="plugin.off_handler_off",
            handler_name="handler_off",
            handler_module_path="plugin.off",
            handler=handler_off,
            event_filters=[CommandFilter("hidden")],
            desc="Inactive plugin",
            enabled=True,
        )
    )

    module_globals = adapter.collect_commands.__func__.__globals__
    with patch.dict(
        module_globals,
        {
            "BotCommand": lambda command, description: SimpleNamespace(
                command=command,
                description=description,
            )
        },
    ):
        commands = adapter.collect_commands()

    assert [(cmd.command, cmd.description) for cmd in commands] == [
        ("ask", "Primary ask command"),
        ("ask_alias", "Primary ask command"),
        ("toolbox", "Duplicate ask command should l..."),
        ("tools", "Duplicate ask command should l..."),
    ]


def test_telegram_extract_command_info_skips_nested_groups_and_long_descriptions():
    TelegramPlatformAdapter = _load_telegram_adapter()
    root_group = CommandGroupFilter("root")
    nested_group = CommandGroupFilter("nested", parent_group=root_group)
    handler_md = SimpleNamespace(
        desc="A very long description that should be truncated for Telegram clients",
    )

    group_result = TelegramPlatformAdapter._extract_command_info(
        nested_group,
        handler_md,
        {"start"},
    )
    command_result = TelegramPlatformAdapter._extract_command_info(
        CommandFilter("valid_name", alias={"alias_name"}),
        handler_md,
        {"start"},
    )

    assert group_result is None
    assert command_result == [
        ("valid_name", "A very long description that s..."),
        ("alias_name", "A very long description that s..."),
    ]


@pytest.mark.asyncio
async def test_telegram_message_handler_routes_media_groups_and_regular_messages():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    converted = SimpleNamespace(message_id="m1")
    adapter.handle_media_group_message = AsyncMock()
    adapter.convert_message = AsyncMock(return_value=converted)
    adapter.handle_msg = AsyncMock()
    context = _build_context()

    media_group_update = create_mock_update(media_group_id="album-1")
    await adapter.message_handler(media_group_update, context)

    regular_update = create_mock_update(media_group_id=None)
    await adapter.message_handler(regular_update, context)

    adapter.handle_media_group_message.assert_awaited_once_with(
        media_group_update, context
    )
    adapter.convert_message.assert_awaited_once_with(regular_update, context)
    adapter.handle_msg.assert_awaited_once_with(converted)


@pytest.mark.asyncio
async def test_telegram_handle_media_group_message_schedules_immediate_processing_after_max_wait():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.media_group_timeout = 2.5
    adapter.media_group_max_wait = 1.0
    adapter.scheduler = MockTelegramBuilder.create_scheduler()
    context = _build_context()
    update = create_mock_update(media_group_id="album-2")

    adapter.media_group_cache["album-2"] = {
        "created_at": datetime.now() - timedelta(seconds=5),
        "items": [],
    }

    await adapter.handle_media_group_message(update, context)

    job_call = adapter.scheduler.add_job.call_args
    assert job_call.kwargs["id"] == "media_group_album-2"
    assert job_call.kwargs["replace_existing"] is True
    assert job_call.kwargs["args"] == ["album-2"]


@pytest.mark.asyncio
async def test_telegram_handle_media_group_message_creates_cache_and_uses_debounce_timeout():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.media_group_timeout = 3.0
    adapter.media_group_max_wait = 10.0
    adapter.scheduler = MockTelegramBuilder.create_scheduler()
    context = _build_context()
    update = create_mock_update(media_group_id="album-new")

    await adapter.handle_media_group_message(update, context)

    assert "album-new" in adapter.media_group_cache
    assert adapter.media_group_cache["album-new"]["items"] == [(update, context)]
    job_call = adapter.scheduler.add_job.call_args
    assert job_call.kwargs["id"] == "media_group_album-new"
    assert job_call.kwargs["replace_existing"] is True
    assert job_call.kwargs["args"] == ["album-new"]


@pytest.mark.asyncio
async def test_telegram_process_media_group_merges_media_without_later_reply_chain():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    first_reply = create_mock_update(
        message_text="first quoted",
        chat_type="group",
        chat_id=-20001,
        user_id=200,
        username="first_user",
        message_id=51,
    ).message
    second_reply = create_mock_update(
        message_text="second quoted",
        chat_type="group",
        chat_id=-20001,
        user_id=201,
        username="second_user",
        message_id=52,
    ).message
    first_update = create_mock_update(
        message_text=None,
        chat_type="group",
        chat_id=-20001,
        media_group_id="album-1",
        photo=[create_mock_file("https://api.telegram.org/file/test/photo.jpg")],
        caption="first caption",
        reply_to_message=first_reply,
    )
    second_document = create_mock_file("https://api.telegram.org/file/test/notes.txt")
    second_document.file_name = "notes.txt"
    second_update = create_mock_update(
        message_text=None,
        chat_type="group",
        chat_id=-20001,
        media_group_id="album-1",
        document=second_document,
        caption="second caption",
        reply_to_message=second_reply,
    )
    adapter.media_group_cache["album-1"] = {
        "created_at": MagicMock(),
        "items": [(first_update, _build_context()), (second_update, _build_context())],
    }

    await adapter.process_media_group("album-1")

    adapter.handle_msg.assert_awaited_once()
    merged_message = adapter.handle_msg.await_args.args[0]
    assert (
        sum(isinstance(component, Comp.Reply) for component in merged_message.message)
        == 1
    )
    assert any(
        isinstance(component, Comp.Image) for component in merged_message.message
    )
    assert any(isinstance(component, Comp.File) for component in merged_message.message)
    plain_texts = [
        component.text
        for component in merged_message.message
        if isinstance(component, Comp.Plain)
    ]
    assert plain_texts == ["first caption", "second caption"]


@pytest.mark.asyncio
async def test_telegram_process_media_group_returns_when_first_message_cannot_convert():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.convert_message = AsyncMock(return_value=None)
    adapter.handle_msg = AsyncMock()
    adapter.media_group_cache["album-empty"] = {
        "created_at": MagicMock(),
        "items": [(create_mock_update(media_group_id="album-empty"), _build_context())],
    }

    await adapter.process_media_group("album-empty")

    adapter.handle_msg.assert_not_awaited()
    assert "album-empty" not in adapter.media_group_cache


@pytest.mark.asyncio
async def test_telegram_process_media_group_skips_later_items_that_convert_to_none():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    first_abm = SimpleNamespace(
        message=[Comp.Plain("first"), Comp.Image(file="photo.jpg", url="photo.jpg")],
        message_id="m1",
        session_id="session-1",
    )
    adapter.media_group_cache["album-skip-none"] = {
        "created_at": MagicMock(),
        "items": [
            (create_mock_update(media_group_id="album-skip-none"), _build_context()),
            (create_mock_update(media_group_id="album-skip-none"), _build_context()),
        ],
    }
    adapter.convert_message = AsyncMock(side_effect=[first_abm, None])

    await adapter.process_media_group("album-skip-none")

    adapter.handle_msg.assert_awaited_once_with(first_abm)
    assert "album-skip-none" not in adapter.media_group_cache


@pytest.mark.asyncio
async def test_telegram_process_media_group_returns_when_cache_missing():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()

    await adapter.process_media_group("missing-album")

    adapter.handle_msg.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_process_media_group_returns_when_cached_items_empty():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    adapter.media_group_cache["album-empty-items"] = {
        "created_at": MagicMock(),
        "items": [],
    }

    await adapter.process_media_group("album-empty-items")

    adapter.handle_msg.assert_not_awaited()
    assert "album-empty-items" not in adapter.media_group_cache


@pytest.mark.asyncio
async def test_telegram_process_media_group_swallows_exceptions_from_later_items():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.handle_msg = AsyncMock()
    first_abm = SimpleNamespace(
        message=[Comp.Plain("first")],
        message_id="m1",
        session_id="session-1",
    )
    second_update = create_mock_update(media_group_id="album-error")
    adapter.media_group_cache["album-error"] = {
        "created_at": MagicMock(),
        "items": [
            (create_mock_update(media_group_id="album-error"), _build_context()),
            (second_update, _build_context()),
        ],
    }
    adapter.convert_message = AsyncMock(
        side_effect=[first_abm, RuntimeError("extra convert failed")]
    )

    await adapter.process_media_group("album-error")

    adapter.handle_msg.assert_not_awaited()
    assert "album-error" not in adapter.media_group_cache


@pytest.mark.asyncio
async def test_telegram_send_voice_with_privacy_fallback_sends_document():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MagicMock()
    client.send_voice = AsyncMock(
        side_effect=Exception("Voice_messages_forbidden by privacy")
    )
    client.send_document = AsyncMock()

    class FakeBadRequest(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.message = message

    send_voice_error = FakeBadRequest("Voice_messages_forbidden by privacy")
    client.send_voice.side_effect = send_voice_error
    tg_event_module = _load_telegram_module(
        "astrbot.core.platform.sources.telegram.tg_event"
    )

    with patch.object(tg_event_module, "BadRequest", FakeBadRequest):
        await TelegramPlatformEvent._send_voice_with_fallback(
            client,
            "voice.wav",
            {"chat_id": "123"},
            caption="voice caption",
            use_media_action=False,
        )

    client.send_voice.assert_awaited_once_with(voice="voice.wav", chat_id="123")
    client.send_document.assert_awaited_once_with(
        document="voice.wav",
        caption="voice caption",
        chat_id="123",
    )


@pytest.mark.asyncio
async def test_telegram_send_with_client_prefixes_at_and_reuses_reply_and_thread_id():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()

    await TelegramPlatformEvent.send_with_client(
        client,
        MessageChain(
            [
                Comp.Reply(id="42", chain=[]),
                Comp.At(qq="alice", name="alice"),
                Comp.Plain("hello there"),
            ]
        ),
        "123#99",
    )

    client.send_chat_action.assert_awaited_once_with(
        chat_id="123",
        action="typing",
        message_thread_id="99",
    )
    client.send_message.assert_awaited_once_with(
        text="@alice hello there",
        parse_mode="MarkdownV2",
        chat_id="123",
        reply_to_message_id="42",
        message_thread_id="99",
    )


@pytest.mark.asyncio
async def test_telegram_send_with_client_uses_animation_for_gif(monkeypatch):
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_animation = AsyncMock()
    image = Comp.Image(file="C:/tmp/anim.gif")
    tg_event_module = _load_telegram_module(
        "astrbot.core.platform.sources.telegram.tg_event"
    )
    monkeypatch.setattr(tg_event_module, "_is_gif", lambda _path: True)

    with patch.object(
        type(image),
        "convert_to_file_path",
        AsyncMock(return_value="C:/tmp/anim.gif"),
    ):
        await TelegramPlatformEvent.send_with_client(
            client,
            MessageChain([image]),
            "456",
        )

    client.send_animation.assert_awaited_once_with(
        animation="C:/tmp/anim.gif", chat_id="456"
    )
    client.send_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_send_with_client_sends_record_caption_as_document_fallback():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    record = Comp.Record(file="voice.wav")
    record.text = "voice caption"

    with (
        patch.object(
            type(record),
            "convert_to_file_path",
            AsyncMock(return_value="voice.wav"),
        ),
        patch.object(
            TelegramPlatformEvent,
            "_send_voice_with_fallback",
            AsyncMock(),
        ) as send_voice_with_fallback,
    ):
        await TelegramPlatformEvent.send_with_client(
            client,
            MessageChain([record]),
            "789",
        )

    send_voice_with_fallback.assert_awaited_once_with(
        client,
        "voice.wav",
        {"chat_id": "789"},
        caption="voice caption",
        use_media_action=False,
    )


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
async def test_telegram_streaming_draft_break_flushes_real_message_and_resets_draft():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)
    event._send_message_draft = AsyncMock()
    event._send_final_segment = AsyncMock()
    event._process_chain_items = AsyncMock(
        side_effect=lambda chain, payload, user_name, message_thread_id, on_text: (
            on_text(chain.get_plain_text())
        )
    )
    allocated = iter([11, 12])

    with patch.object(
        TelegramPlatformEvent,
        "_allocate_draft_id",
        side_effect=lambda: next(allocated),
    ):

        async def generator():
            yield MessageChain([Comp.Plain("hello ")])
            yield MessageChain(type="break")
            yield MessageChain([Comp.Plain("world")])

        await event._send_streaming_draft("123", None, {"chat_id": "123"}, generator())

    assert event._send_message_draft.await_args_list == [
        call("123", 11, "\u23f3", None),
        call("123", 12, "\u23f3", None),
    ]
    assert event._send_final_segment.await_args_list == [
        call("hello ", {"chat_id": "123"}),
        call("world", {"chat_id": "123"}),
    ]


@pytest.mark.asyncio
async def test_telegram_streaming_edit_break_resets_message_id_and_sends_new_message():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MockTelegramBuilder.create_bot()
    client.send_message.side_effect = [
        SimpleNamespace(message_id=100),
        SimpleNamespace(message_id=101),
    ]
    event = TelegramPlatformEvent("msg", MagicMock(), MagicMock(), "session", client)
    event._ensure_typing = AsyncMock()
    event._process_chain_items = AsyncMock(
        side_effect=lambda chain, payload, user_name, message_thread_id, on_text: (
            on_text(chain.get_plain_text())
        )
    )

    async def generator():
        yield MessageChain([Comp.Plain("first")])
        yield MessageChain(type="break")
        yield MessageChain([Comp.Plain("second")])

    await event._send_streaming_edit("123", None, {"chat_id": "123"}, generator())

    client.send_message.assert_awaited()
    assert client.send_message.await_args_list[0].kwargs == {
        "text": "first",
        "chat_id": "123",
    }
    assert client.send_message.await_args_list[1].kwargs == {
        "text": "second",
        "chat_id": "123",
    }
    client.edit_message_text.assert_any_await(
        text="first",
        chat_id="123",
        message_id=100,
    )


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
        _bind_runtime_registries(adapter)
        await adapter.run()

    assert builder.build.call_count == 2
    app_one.updater.stop.assert_awaited()
    app_one.bot.delete_my_commands.assert_awaited_once()
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
        _bind_runtime_registries(adapter)
        await adapter.run()

    assert builder.build.call_count == 3
    app_two.stop.assert_awaited()
    app_two.shutdown.assert_awaited()
    app_three.initialize.assert_awaited()
    app_three.start.assert_awaited()


def _telegram_bare_adapter():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter.__new__(TelegramPlatformAdapter)
    adapter.config = {"id": "telegram-test"}
    adapter.client = SimpleNamespace()
    return adapter


def _telegram_message(*, chat_type: str, status: str | None = None):
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
    from astrbot.core.platform.message_type import MessageType

    message = AstrBotMessage()
    message.type = (
        MessageType.FRIEND_MESSAGE
        if chat_type == "private"
        else MessageType.GROUP_MESSAGE
    )
    message.group_id = None if chat_type == "private" else "-1001"
    message.session_id = "1001" if chat_type == "private" else "-1001"
    message.sender = MessageMember("42", "tester")
    message.message_str = "hello"
    message.message = []
    update = SimpleNamespace(
        message=SimpleNamespace(chat=SimpleNamespace(type=chat_type)),
        chat_member=None,
        my_chat_member=None,
    )
    if status is not None:
        update.chat_member = SimpleNamespace(
            new_chat_member=SimpleNamespace(status=status)
        )
    message.raw_message = update
    return message


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("creator", "owner"),
        ("administrator", "admin"),
        ("member", "member"),
        ("restricted", "member"),
        ("kicked", "unknown"),
        (None, "unknown"),
    ],
)
def test_telegram_group_status_maps_or_stays_unknown(status, expected):
    event = _telegram_bare_adapter().create_event(
        _telegram_message(chat_type="group", status=status)
    )
    assert event.platform_member_role == expected
    assert event.platform_role_source == "adapter"


def test_telegram_private_chat_does_not_promote_creator_status():
    event = _telegram_bare_adapter().create_event(
        _telegram_message(chat_type="private", status="creator")
    )
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"


@pytest.mark.asyncio
async def test_telegram_group_admin_role_stays_in_current_session(tmp_path):
    from astrbot.core.auth.service import AuthorizationService
    from astrbot.core.db.sqlite import SQLiteDatabase
    from tests.fixtures.auth import assert_platform_role_stays_in_session

    event = _telegram_bare_adapter().create_event(
        _telegram_message(chat_type="group", status="administrator")
    )
    db = SQLiteDatabase(str(tmp_path / "telegram-auth.db"))
    await db.initialize()
    service = AuthorizationService(db)
    await service.start()
    try:
        await assert_platform_role_stays_in_session(
            service,
            platform_instance="telegram",
            sender_id="42",
            platform_role=event.platform_member_role,
            current_umo="telegram:GroupMessage:-1001",
            other_umo="telegram:GroupMessage:-2002",
        )
    finally:
        await service.close()
        await db.close()


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
    event._client = SimpleNamespace(
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
    event._client = client

    group = await event.get_group()

    assert group is not None
    assert group.group_id == "-100123#42"
    assert group.group_name == "Engineering"
    assert group.group_avatar == "https://api.telegram.org/file/group.jpg"
    assert group is not event.message_obj.group
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
    event._client = client

    group = await event.get_group()

    assert group is not event.message_obj.group
    assert group == Group(group_id="-100123#42", group_name="Cached title")


@pytest.mark.asyncio
async def test_telegram_get_group_joins_relative_avatar_with_file_base_url():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        base_file_url="https://api.telegram.org/file/botTESTTOKEN",
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                title="Engineering",
                photo=SimpleNamespace(big_file_id="photo-1"),
            )
        ),
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="photos/group.jpg")),
        get_chat_member_count=AsyncMock(return_value=3),
        get_chat_administrators=AsyncMock(return_value=[]),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123", group_name="Cached title"),
        group_id="-100123",
    )
    event._client = client

    group = await event.get_group()

    assert (
        group.group_avatar
        == "https://api.telegram.org/file/botTESTTOKEN/photos/group.jpg"
    )


@pytest.mark.asyncio
async def test_telegram_get_group_leaves_avatar_none_when_file_path_unusable():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                title="Engineering",
                photo=SimpleNamespace(big_file_id="photo-1"),
            )
        ),
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="photos/group.jpg")),
        get_chat_member_count=AsyncMock(return_value=3),
        get_chat_administrators=AsyncMock(return_value=[]),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123", group_name="Cached title"),
        group_id="-100123",
    )
    event._client = client

    group = await event.get_group()

    assert group.group_avatar is None


@pytest.mark.asyncio
async def test_telegram_get_group_does_not_use_topic_name_for_other_group():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = SimpleNamespace(
        get_chat=AsyncMock(return_value=SimpleNamespace(title="Other", photo=None)),
        get_chat_member_count=AsyncMock(return_value=2),
        get_chat_administrators=AsyncMock(return_value=[]),
    )
    event = TelegramPlatformEvent.__new__(TelegramPlatformEvent)
    event.message_obj = SimpleNamespace(
        group=Group(group_id="-100123#42", group_name="Engineering-Backend"),
        group_id="-100123#42",
        _telegram_topic_name="Backend",
    )
    event._client = client

    group = await event.get_group(group_id="-100999")

    assert group.group_id == "-100999"
    assert group.group_name == "Other"
