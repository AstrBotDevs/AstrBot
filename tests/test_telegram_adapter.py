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
    with patch.dict(sys.modules, _build_telegram_patched_modules()):
        sys.modules.pop(module_name, None)
        module = importlib.import_module(module_name)
        components_module = sys.modules.get(components_module_name)

    sys.modules[module_name] = module
    _TELEGRAM_MODULES[module_name] = module
    if components_module is not None:
        sys.modules[components_module_name] = components_module
        _TELEGRAM_MODULES[components_module_name] = components_module
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
    assert app.add_handler.call_count == 2


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
