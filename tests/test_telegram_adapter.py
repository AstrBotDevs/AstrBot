import asyncio
import importlib
import sys
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
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

    components_module_name = "astrbot.core.platform.sources.telegram.components"
    filters_module_name = "astrbot.core.platform.sources.telegram.filters"
    with patch.dict(sys.modules, _build_telegram_patched_modules()):
        sys.modules.pop(module_name, None)
        module = importlib.import_module(module_name)
        components_module = sys.modules.get(components_module_name)
        filters_module = sys.modules.get(filters_module_name)

    sys.modules[module_name] = module
    _TELEGRAM_MODULES[module_name] = module
    if components_module is not None:
        sys.modules[components_module_name] = components_module
        _TELEGRAM_MODULES[components_module_name] = components_module
    if filters_module is not None:
        sys.modules[filters_module_name] = filters_module
        _TELEGRAM_MODULES[filters_module_name] = filters_module
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


def _load_telegram_components():
    _load_telegram_platform_event()
    return _TELEGRAM_MODULES["astrbot.core.platform.sources.telegram.components"]


def _load_telegram_filters():
    return _load_telegram_module("astrbot.core.platform.sources.telegram.filters")


def _build_context() -> MagicMock:
    context = MagicMock()
    context.bot.username = "test_bot"
    context.bot.id = 12345678
    return context


def _build_user(user_id: int = 42, username: str = "alice") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.full_name = username
    user.first_name = username
    return user


def _build_chat(chat_id: int = -100, chat_type: str = "supergroup") -> MagicMock:
    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type
    return chat


async def _commit_and_get_event(adapter, abm):
    await adapter.handle_msg(abm)
    return adapter._event_queue.get_nowait()


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


@pytest.mark.asyncio
async def test_telegram_send_with_inline_keyboard_and_message_options():
    TelegramPlatformEvent = _load_telegram_platform_event()
    components = _load_telegram_components()
    client = MagicMock()
    client.send_message = AsyncMock()
    client.send_chat_action = AsyncMock()
    message = MessageChain()
    message.message("approve this")
    message.chain.append(
        components.TelegramMessageOptions(
            parse_mode="HTML",
            link_preview_is_disabled=True,
            link_preview_url="https://example.com/preview",
            link_preview_prefer_small_media=True,
            link_preview_show_above_text=True,
        ),
    )
    message.chain.append(
        components.TelegramInlineKeyboard(
            [
                [
                    components.TelegramInlineButton(
                        "Approve",
                        callback_data="approval:yes",
                    ),
                    components.TelegramInlineButton(
                        "Details",
                        url="https://example.com/details",
                    ),
                ],
            ],
        ),
    )

    await TelegramPlatformEvent.send_with_client(client, message, "123456")

    call = client.send_message.await_args.kwargs
    assert call["text"] == "approve this"
    assert call["parse_mode"] == "HTML"
    assert call["link_preview_options"].is_disabled is True
    assert call["link_preview_options"].url == "https://example.com/preview"
    assert call["reply_markup"].inline_keyboard[0][0].callback_data == "approval:yes"
    assert (
        call["reply_markup"].inline_keyboard[0][1].url == "https://example.com/details"
    )


@pytest.mark.asyncio
async def test_telegram_send_respects_plaintext_markdown_toggle():
    TelegramPlatformEvent = _load_telegram_platform_event()
    client = MagicMock()
    client.send_message = AsyncMock()
    client.send_chat_action = AsyncMock()
    message = MessageChain()
    message.use_markdown_ = False
    message.message("**plain**")

    await TelegramPlatformEvent.send_with_client(client, message, "123456")

    call = client.send_message.await_args.kwargs
    assert call["text"] == "**plain**"
    assert "parse_mode" not in call


@pytest.mark.asyncio
async def test_telegram_send_by_session_preserves_markdown_options_and_keyboard():
    TelegramPlatformAdapter = _load_telegram_adapter()
    components = _load_telegram_components()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.client.send_message = AsyncMock()
    adapter.client.send_chat_action = AsyncMock()
    message = MessageChain()
    message.message("proactive")
    message.chain.append(components.TelegramMessageOptions(parse_mode="Markdown"))
    message.chain.append(
        components.TelegramInlineKeyboard(
            [[components.TelegramInlineButton("OK", callback_data="ok")]],
        ),
    )
    session = MagicMock()
    session.session_id = "123456"

    await adapter.send_by_session(session, message)

    call = adapter.client.send_message.await_args.kwargs
    assert call["parse_mode"] == "Markdown"
    assert call["reply_markup"].inline_keyboard[0][0].callback_data == "ok"


@pytest.mark.asyncio
async def test_telegram_send_with_reply_keyboard_remove_keyboard_and_force_reply():
    TelegramPlatformEvent = _load_telegram_platform_event()
    components = _load_telegram_components()
    client = MagicMock()
    client.send_message = AsyncMock()
    client.send_chat_action = AsyncMock()

    reply_keyboard_message = MessageChain()
    reply_keyboard_message.message("choose")
    reply_keyboard_message.chain.append(
        components.TelegramReplyKeyboard(
            [
                [
                    components.TelegramKeyboardButton(
                        "Share phone",
                        request_contact=True,
                    ),
                    "Cancel",
                ],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Choose",
        ),
    )
    await TelegramPlatformEvent.send_with_client(
        client,
        reply_keyboard_message,
        "123456",
    )
    reply_markup = client.send_message.await_args.kwargs["reply_markup"]
    assert reply_markup.keyboard[0][0].request_contact is True
    assert reply_markup.keyboard[0][1] == "Cancel"
    assert reply_markup.resize_keyboard is True
    assert reply_markup.one_time_keyboard is True
    assert reply_markup.input_field_placeholder == "Choose"

    remove_keyboard_message = MessageChain()
    remove_keyboard_message.message("remove")
    remove_keyboard_message.chain.append(
        components.TelegramRemoveKeyboard(selective=True)
    )
    await TelegramPlatformEvent.send_with_client(
        client,
        remove_keyboard_message,
        "123456",
    )
    remove_markup = client.send_message.await_args.kwargs["reply_markup"]
    assert remove_markup.selective is True

    force_reply_message = MessageChain()
    force_reply_message.message("reply")
    force_reply_message.chain.append(
        components.TelegramForceReply(
            selective=True,
            input_field_placeholder="Reply",
        ),
    )
    await TelegramPlatformEvent.send_with_client(client, force_reply_message, "123456")
    force_markup = client.send_message.await_args.kwargs["reply_markup"]
    assert force_markup.selective is True
    assert force_markup.input_field_placeholder == "Reply"


def test_telegram_inline_button_validates_actions_and_callback_data():
    components = _load_telegram_components()

    with pytest.raises(ValueError, match="exactly one"):
        components.TelegramInlineButton("Missing")

    with pytest.raises(ValueError, match="exactly one"):
        components.TelegramInlineButton(
            "Too many",
            callback_data="ok",
            url="https://example.com",
        )

    with pytest.raises(ValueError, match="1-64"):
        components.TelegramInlineButton("Empty", callback_data="")

    with pytest.raises(ValueError, match="1-64"):
        components.TelegramInlineButton("Too long", callback_data="x" * 65)

    button = components.TelegramInlineButton("中文", callback_data="确认")
    assert len(button.callback_data.encode("utf-8")) <= 64

    url_button = components.TelegramInlineButton(
        "Open",
        url="https://example.com",
        pay=False,
    ).to_telegram_button()
    assert url_button.url == "https://example.com"
    assert not hasattr(url_button, "pay")

    styled_button = components.TelegramInlineButton(
        "Styled",
        callback_data="styled",
        style="primary",
        icon_custom_emoji_id="5368324170671202286",
    ).to_telegram_button()
    assert styled_button.style == "primary"
    assert styled_button.icon_custom_emoji_id == "5368324170671202286"


def test_telegram_command_config_normalization_supports_wildcard_and_empty_language():
    TelegramPlatformAdapter = _load_telegram_adapter()

    assert TelegramPlatformAdapter._normalize_command_plugin_allowlist(["*"]) is None
    assert (
        TelegramPlatformAdapter._normalize_command_plugin_allowlist(
            "allowed,*",
        )
        is None
    )
    assert TelegramPlatformAdapter._command_language_code({"language_code": ""}) is None
    assert (
        TelegramPlatformAdapter._command_language_code({"language_code": " zh "})
        == "zh"
    )


def test_telegram_event_filter_matches_structured_events():
    TelegramPlatformEvent = _load_telegram_platform_event()
    filters_module = _load_telegram_filters()
    platform_meta = MagicMock()
    platform_meta.name = "telegram"
    platform_meta.id = "telegram"
    message_obj = MagicMock()
    message_obj.type = "FriendMessage"
    message_obj.sender.user_id = "42"
    message_obj.sender.nickname = "alice"
    message_obj.raw_message.callback_query.data = "approve:42"
    event = TelegramPlatformEvent(
        "approve:42", message_obj, platform_meta, "42", MagicMock()
    )
    event.set_extra("telegram_event_type", "callback_query")

    callback_filter = filters_module.telegram_event_filter(
        callback_data_prefix="approve:",
    )(raise_error=False)
    assert callback_filter.filter(event, MagicMock()) is True

    inline_event = TelegramPlatformEvent(
        "", message_obj, platform_meta, "42", MagicMock()
    )
    inline_event.set_extra("telegram_event_type", "inline_query")
    inline_filter = filters_module.telegram_event_filter("inline_query")(
        raise_error=False,
    )
    assert inline_filter.filter(inline_event, MagicMock()) is True
    assert callback_filter.filter(inline_event, MagicMock()) is False

    member_event = TelegramPlatformEvent(
        "", message_obj, platform_meta, "42", MagicMock()
    )
    member_event.set_extra("telegram_event_type", "member_left")
    member_filter = filters_module.telegram_event_filter(
        ["member_joined", "member_left"]
    )(
        raise_error=False,
    )
    assert member_filter.filter(member_event, MagicMock()) is True

    other_platform = MagicMock()
    other_platform.get_platform_name.return_value = "discord"
    assert member_filter.filter(other_platform, MagicMock()) is False


@pytest.mark.asyncio
async def test_telegram_callback_query_is_converted_to_platform_event():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    callback_query = MagicMock()
    callback_query.id = "callback-id"
    callback_query.data = "approval:yes"
    callback_query.game_short_name = None
    callback_query.from_user.id = 42
    callback_query.from_user.username = "alice"
    callback_query.message.message_id = 99
    callback_query.message.chat.id = -100
    callback_query.message.chat.type = "supergroup"
    callback_query.message.is_topic_message = True
    callback_query.message.message_thread_id = 7
    callback_query.answer = AsyncMock()
    update = MagicMock()
    update.callback_query = callback_query

    abm = await adapter.convert_callback_query(update, _build_context())

    assert abm is not None
    assert abm.message_str == "approval:yes"
    assert abm.sender.user_id == "42"
    assert abm.group_id == "-100#7"
    assert abm.session_id == "-100#7"
    event = adapter.handle_msg.__globals__["TelegramPlatformEvent"](
        abm.message_str,
        abm,
        adapter.meta(),
        abm.session_id,
        adapter.client,
    )
    assert event.is_button_interaction()
    assert event.get_interaction_custom_id() == "approval:yes"
    assert event.get_interaction_data() == "approval:yes"
    assert event.get_interaction_user_id() == "42"

    await event.answer_interaction("done", show_alert=True, cache_time=5)

    callback_query.answer.assert_awaited_once_with(
        text="done",
        show_alert=True,
        url=None,
        cache_time=5,
    )


@pytest.mark.asyncio
async def test_telegram_inline_query_is_converted_and_answered():
    TelegramPlatformAdapter = _load_telegram_adapter()
    components = _load_telegram_components()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    inline_query = MagicMock()
    inline_query.id = "inline-id"
    inline_query.query = "search text"
    inline_query.from_user = _build_user(42, "alice")
    update = MagicMock()
    update.inline_query = inline_query

    abm = await adapter.convert_inline_query(update, _build_context())

    assert abm is not None
    assert abm.message_str == "search text"
    event = await _commit_and_get_event(adapter, abm)
    assert event.get_extra("telegram_event_type") == "inline_query"
    assert event.get_inline_query_text() == "search text"
    assert event.call_llm is True

    result = components.TelegramInlineQueryResult(
        "article",
        id="article-1",
        title="Result",
        input_message_content=components.TelegramInputTextMessageContent(
            "hello",
            parse_mode="MarkdownV2",
        ),
    )
    await event.answer_inline_query([result], cache_time=5, is_personal=True)

    answer_call = adapter.client.answer_inline_query.await_args.kwargs
    assert answer_call["inline_query_id"] == "inline-id"
    assert answer_call["cache_time"] == 5
    assert answer_call["is_personal"] is True
    assert answer_call["results"][0].title == "Result"
    assert answer_call["results"][0].input_message_content.message_text == "hello"


@pytest.mark.asyncio
async def test_telegram_chosen_inline_result_is_converted():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    chosen_result = MagicMock()
    chosen_result.result_id = "article-1"
    chosen_result.query = "search text"
    chosen_result.from_user = _build_user(42, "alice")
    update = MagicMock()
    update.chosen_inline_result = chosen_result

    abm = await adapter.convert_chosen_inline_result(update, _build_context())

    assert abm is not None
    assert abm.message_id == "article-1"
    event = await _commit_and_get_event(adapter, abm)
    assert event.get_extra("telegram_event_type") == "chosen_inline_result"
    assert event.get_chosen_inline_result().result_id == "article-1"
    assert event.call_llm is True


@pytest.mark.asyncio
async def test_telegram_chat_member_events_are_converted():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    update = MagicMock()
    update.update_id = 77
    update.chat_member = MagicMock()
    update.chat_member.from_user = _build_user(42, "admin")
    update.chat_member.chat = _build_chat(-100, "supergroup")
    update.chat_member.old_chat_member.status = "member"
    update.chat_member.new_chat_member.status = "administrator"

    abm = await adapter.convert_chat_member_update(
        update,
        _build_context(),
        "chat_member",
    )

    assert abm is not None
    assert abm.group_id == "-100"
    event = await _commit_and_get_event(adapter, abm)
    assert event.get_extra("telegram_event_type") == "chat_member"
    assert event.get_chat_member_update().chat.id == -100
    assert event.call_llm is True

    my_update = MagicMock()
    my_update.update_id = 78
    my_update.my_chat_member = MagicMock()
    my_update.my_chat_member.from_user = _build_user(43, "owner")
    my_update.my_chat_member.chat = _build_chat(-101, "supergroup")
    my_update.my_chat_member.old_chat_member.status = "left"
    my_update.my_chat_member.new_chat_member.status = "member"

    my_abm = await adapter.convert_chat_member_update(
        my_update,
        _build_context(),
        "my_chat_member",
    )
    my_event = await _commit_and_get_event(adapter, my_abm)
    assert my_event.get_extra("telegram_event_type") == "my_chat_member"
    assert my_event.get_chat_member_update().chat.id == -101
    assert my_event.call_llm is True


@pytest.mark.asyncio
async def test_telegram_member_joined_and_left_are_converted():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    new_member = _build_user(99, "newbie")
    join_update = create_mock_update(
        message_text=None,
        chat_type="supergroup",
        chat_id=-100,
        user_id=42,
        username="admin",
        new_chat_members=[new_member],
    )

    join_abm = await adapter.convert_message(join_update, _build_context())

    assert join_abm is not None
    join_event = await _commit_and_get_event(adapter, join_abm)
    assert join_event.get_extra("telegram_event_type") == "member_joined"
    assert join_event.get_extra("telegram_payload")[0].id == 99
    assert join_event.call_llm is True

    left_member = _build_user(100, "leaver")
    left_update = create_mock_update(
        message_text=None,
        chat_type="supergroup",
        chat_id=-100,
        user_id=42,
        username="admin",
        left_chat_member=left_member,
    )

    left_abm = await adapter.convert_message(left_update, _build_context())
    left_event = await _commit_and_get_event(adapter, left_abm)
    assert left_event.get_extra("telegram_event_type") == "member_left"
    assert left_event.get_extra("telegram_payload").id == 100
    assert left_event.call_llm is True


def test_telegram_application_builder_uses_adapter_proxy_config():
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__
    builder = MockTelegramBuilder.create_application_builder()

    with patch.dict(
        module_globals,
        {
            "ApplicationBuilder": MagicMock(return_value=builder),
            "AsyncIOScheduler": MagicMock(
                return_value=MockTelegramBuilder.create_scheduler()
            ),
        },
    ):
        TelegramPlatformAdapter(
            make_platform_config(
                "telegram",
                telegram_proxy="http://127.0.0.1:7890",
                telegram_get_updates_proxy="http://127.0.0.1:7891",
            ),
            {},
            asyncio.Queue(),
        )

    builder.proxy.assert_called_once_with("http://127.0.0.1:7890")
    builder.get_updates_proxy.assert_called_once_with("http://127.0.0.1:7891")
    app = builder.build.return_value
    handlers = [call.args[0] for call in app.add_handler.call_args_list]
    assert app.add_handler.call_count == 6
    assert handlers[0].filters is module_globals["filters"].ALL
    handler_type_names = [type(handler).__name__ for handler in handlers]
    assert "MockCallbackQueryHandler" in handler_type_names
    assert "MockInlineQueryHandler" in handler_type_names
    assert "MockChosenInlineResultHandler" in handler_type_names
    assert handler_type_names.count("MockChatMemberHandler") == 2


@pytest.mark.asyncio
async def test_telegram_command_registration_filters_plugins_and_uses_scopes():
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__

    async def _handler(*args, **kwargs):
        return None

    @dataclass
    class _Plugin:
        name: str
        display_name: str
        root_dir_name: str
        module_path: str
        activated: bool = True

    @dataclass
    class _Handler:
        handler_module_path: str
        event_filters: list
        desc: str
        enabled: bool = True

    handlers = [
        _Handler(
            "plugins.allowed.main",
            [module_globals["CommandFilter"]("allowed", alias={"alias"})],
            "Allowed command",
        ),
        _Handler(
            "plugins.denied.main",
            [module_globals["CommandFilter"]("denied")],
            "Denied command",
        ),
    ]
    star_map = {
        "plugins.allowed.main": _Plugin(
            "allowed_plugin",
            "Allowed",
            "allowed",
            "plugins.allowed.main",
        ),
        "plugins.denied.main": _Plugin(
            "denied_plugin",
            "Denied",
            "denied",
            "plugins.denied.main",
        ),
    }
    adapter = TelegramPlatformAdapter(
        make_platform_config(
            "telegram",
            telegram_command_registered_plugins=["allowed_plugin"],
            telegram_command_scopes=[
                {"type": "default", "language_code": "en"},
                {"type": "chat", "chat_id": 12345, "language_code": "zh"},
            ],
        ),
        {},
        asyncio.Queue(),
    )

    with patch.dict(
        module_globals, {"star_handlers_registry": handlers, "star_map": star_map}
    ):
        await adapter.register_commands()

    assert adapter.client.delete_my_commands.await_count == 2
    assert adapter.client.set_my_commands.await_count == 2
    first_commands = adapter.client.set_my_commands.await_args_list[0].args[0]
    assert [cmd.command for cmd in first_commands] == ["alias", "allowed"]
    assert {cmd.description for cmd in first_commands} == {"Allowed command"}
    first_kwargs = adapter.client.set_my_commands.await_args_list[0].kwargs
    second_kwargs = adapter.client.set_my_commands.await_args_list[1].kwargs
    assert first_kwargs["language_code"] == "en"
    assert second_kwargs["language_code"] == "zh"
    assert "BotCommandScopeDefault" in repr(type(first_kwargs["scope"]))
    assert "BotCommandScopeChat" in repr(type(second_kwargs["scope"]))


def test_telegram_event_filter_does_not_pollute_bot_command_collection():
    TelegramPlatformAdapter = _load_telegram_adapter()
    filters_module = _load_telegram_filters()
    module_globals = TelegramPlatformAdapter.__init__.__globals__

    @dataclass
    class _Plugin:
        name: str
        display_name: str
        root_dir_name: str
        module_path: str
        activated: bool = True

    @dataclass
    class _Handler:
        handler_module_path: str
        event_filters: list
        desc: str
        enabled: bool = True

    telegram_custom_filter = filters_module.telegram_event_filter("inline_query")(
        raise_error=False,
    )
    handlers = [
        _Handler(
            "plugins.allowed.main",
            [module_globals["CommandFilter"]("ok"), telegram_custom_filter],
            "OK command",
        ),
        _Handler(
            "plugins.inline_only.main",
            [telegram_custom_filter],
            "Inline only",
        ),
    ]
    star_map = {
        "plugins.allowed.main": _Plugin(
            "allowed_plugin",
            "Allowed",
            "allowed",
            "plugins.allowed.main",
        ),
        "plugins.inline_only.main": _Plugin(
            "inline_plugin",
            "Inline",
            "inline_only",
            "plugins.inline_only.main",
        ),
    }
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )

    with patch.dict(
        module_globals, {"star_handlers_registry": handlers, "star_map": star_map}
    ):
        commands = adapter.collect_commands()

    assert [command.command for command in commands] == ["ok"]


@pytest.mark.asyncio
async def test_telegram_command_registration_skips_when_command_count_exceeds_limit():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    adapter.collect_commands = MagicMock(
        return_value=[
            MagicMock(command=f"cmd{i}", description="desc") for i in range(101)
        ],
    )

    await adapter.register_commands()

    adapter.client.delete_my_commands.assert_not_awaited()
    adapter.client.set_my_commands.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_run_starts_webhook_when_configured():
    TelegramPlatformAdapter = _load_telegram_adapter()
    module_globals = TelegramPlatformAdapter.__init__.__globals__
    app = MockTelegramBuilder.create_application()
    app.updater.running = False
    builder = MagicMock()
    builder.token.return_value = builder
    builder.base_url.return_value = builder
    builder.base_file_url.return_value = builder
    builder.build.return_value = app

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
                telegram_update_mode="webhook",
                telegram_webhook_listen="127.0.0.1",
                telegram_webhook_port=9443,
                telegram_webhook_url_path="/tg-hook",
                telegram_webhook_url="https://example.com/tg-hook",
                telegram_webhook_secret_token="secret",
                telegram_webhook_drop_pending_updates=True,
            ),
            {},
            asyncio.Queue(),
        )

        async def start_webhook_side_effect(*args, **kwargs):
            adapter._terminating = True

        app.updater.start_webhook.side_effect = start_webhook_side_effect
        await adapter.run()

    app.updater.start_polling.assert_not_called()
    webhook_kwargs = app.updater.start_webhook.call_args.kwargs
    assert webhook_kwargs["listen"] == "127.0.0.1"
    assert webhook_kwargs["port"] == 9443
    assert webhook_kwargs["url_path"] == "tg-hook"
    assert webhook_kwargs["webhook_url"] == "https://example.com/tg-hook"
    assert webhook_kwargs["secret_token"] == "secret"
    assert webhook_kwargs["drop_pending_updates"] is True
    assert "inline_query" in webhook_kwargs["allowed_updates"]
    assert "chat_member" in webhook_kwargs["allowed_updates"]


@pytest.mark.asyncio
async def test_telegram_polling_mode_still_uses_start_polling():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )

    async def start_polling_side_effect(*args, **kwargs):
        adapter._terminating = True

    adapter.application.updater.start_polling.side_effect = start_polling_side_effect
    await adapter.run()

    adapter.application.updater.start_webhook.assert_not_called()
    polling_kwargs = adapter.application.updater.start_polling.call_args.kwargs
    assert polling_kwargs["error_callback"] == adapter._on_polling_error
    assert "chosen_inline_result" in polling_kwargs["allowed_updates"]


@pytest.mark.asyncio
async def test_telegram_message_helpers_edit_delete_copy_forward():
    TelegramPlatformEvent = _load_telegram_platform_event()
    components = _load_telegram_components()
    client = MockTelegramBuilder.create_bot()
    message_obj = MagicMock()
    message_obj.type = "GroupMessage"
    message_obj.group_id = "-100#7"
    message_obj.message_id = "99"
    message_obj.sender.user_id = "42"
    message_obj.sender.nickname = "alice"
    platform_meta = MagicMock()
    platform_meta.name = "telegram"
    platform_meta.id = "telegram"
    event = TelegramPlatformEvent("msg", message_obj, platform_meta, "-100#7", client)
    keyboard = components.TelegramInlineKeyboard(
        [[components.TelegramInlineButton("OK", callback_data="ok")]],
    )

    await event.edit_text("edited", reply_markup=keyboard, parse_mode="HTML")
    await event.edit_reply_markup(reply_markup=keyboard)
    await event.delete_message()
    await event.copy_message("-200#8")
    await event.forward_message("-300#9")

    edit_text_kwargs = client.edit_message_text.await_args.kwargs
    assert edit_text_kwargs["chat_id"] == "-100"
    assert edit_text_kwargs["message_id"] == 99
    assert edit_text_kwargs["parse_mode"] == "HTML"
    assert edit_text_kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "ok"
    assert client.edit_message_reply_markup.await_args.kwargs["chat_id"] == "-100"
    assert client.delete_message.await_args.kwargs == {
        "chat_id": "-100",
        "message_id": 99,
    }
    assert client.copy_message.await_args.kwargs["chat_id"] == "-200"
    assert client.copy_message.await_args.kwargs["from_chat_id"] == "-100"
    assert client.copy_message.await_args.kwargs["message_thread_id"] == 8
    assert client.forward_message.await_args.kwargs["chat_id"] == "-300"
    assert client.forward_message.await_args.kwargs["message_thread_id"] == 9


@pytest.mark.asyncio
async def test_telegram_common_inbound_message_types_are_converted():
    TelegramPlatformAdapter = _load_telegram_adapter()
    adapter = TelegramPlatformAdapter(
        make_platform_config("telegram"),
        {},
        asyncio.Queue(),
    )
    audio = create_mock_file("https://api.telegram.org/file/test/song.mp3")
    audio.file_name = "song.mp3"
    audio_update = create_mock_update(message_text=None, audio=audio)

    audio_result = await adapter.convert_message(audio_update, _build_context())

    assert any(isinstance(component, Comp.File) for component in audio_result.message)

    location = MagicMock()
    location.latitude = 1.25
    location.longitude = 2.5
    location_update = create_mock_update(message_text=None, location=location)

    location_result = await adapter.convert_message(location_update, _build_context())

    assert isinstance(location_result.message[0], Comp.Location)
    assert location_result.message[0].lat == 1.25
    assert location_result.message[0].lon == 2.5

    poll = MagicMock()
    poll.question = "Pick one"
    poll_update = create_mock_update(message_text=None, poll=poll)

    poll_result = await adapter.convert_message(poll_update, _build_context())
    poll_event = await _commit_and_get_event(adapter, poll_result)

    assert poll_event.get_extra("telegram_event_type") == "poll"
    assert poll_event.get_extra("telegram_payload").question == "Pick one"
    assert poll_event.call_llm is False

    dice = MagicMock()
    dice.emoji = "\U0001f3b2"
    dice.value = 6
    dice_update = create_mock_update(message_text=None, dice=dice)

    dice_result = await adapter.convert_message(dice_update, _build_context())
    dice_event = await _commit_and_get_event(adapter, dice_result)

    assert dice_result.message_str == "Dice: \U0001f3b2=6"
    assert dice_event.get_extra("telegram_event_type") == "dice"
    assert dice_event.get_extra("telegram_payload").value == 6
    assert dice_event.call_llm is False
