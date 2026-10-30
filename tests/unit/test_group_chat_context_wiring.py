import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.message_components import Json, Plain
from astrbot.api.provider import LLMResponse, Provider
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_type import MessageType


def make_main_with_conversation_manager(conv_mgr):
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_using_provider_async = AsyncMock(
        side_effect=lambda *args, **kwargs: main.context.get_using_provider(
            *args,
            **kwargs,
        )
    )
    main.context.conversation_manager = conv_mgr
    return main


def _make_extras_store():
    """Return a mutable dict and get_extra / set_extra side_effects bound to it."""
    store: dict[str, object] = {}
    get_extra = lambda key, default=None: store.get(key, default)  # noqa: E731
    set_extra = store.__setitem__  # type: ignore[assignment]
    return store, get_extra, set_extra


def make_event(
    umo: str = "aiocqhttp:GroupMessage:user_123_group_456",
    *,
    handlers_parsed_params: dict | None = None,
):
    event = MagicMock()
    event.unified_msg_origin = umo
    event.get_platform_id.return_value = "aiocqhttp"
    event.message_obj = SimpleNamespace(message=[Plain("hello")])
    event.message_str = "hello"
    event.session_id = "session-1"

    store, get_extra, set_extra = _make_extras_store()
    # Simulate WakingCheckStage output: an empty dict means no command matched.
    store["handlers_parsed_params"] = (
        {} if handlers_parsed_params is None else handlers_parsed_params
    )
    event.get_extra.side_effect = get_extra
    event.set_extra.side_effect = set_extra
    return event


@pytest.mark.asyncio
async def test_active_reply_does_not_create_conversation_when_current_missing():
    conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value=None),
        new_conversation=AsyncMock(),
        get_conversation=AsyncMock(),
    )
    main = make_main_with_conversation_manager(conv_mgr)
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": False,
            "active_reply": {"enable": True},
        },
    }
    main.context.get_using_provider.return_value = object()
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=True),
        handle_message=AsyncMock(),
    )
    event = make_event()

    results = [item async for item in main.on_message(event)]

    assert results == []
    conv_mgr.get_curr_conversation_id.assert_awaited_once_with(event.unified_msg_origin)
    conv_mgr.new_conversation.assert_not_called()
    conv_mgr.get_conversation.assert_not_called()
    event.request_llm.assert_not_called()


@pytest.mark.asyncio
async def test_active_reply_reuses_current_umo_conversation():
    conv = SimpleNamespace(cid="cid-1")
    conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="cid-1"),
        new_conversation=AsyncMock(),
        get_conversation=AsyncMock(return_value=conv),
    )
    main = make_main_with_conversation_manager(conv_mgr)
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": False,
            "active_reply": {"enable": True},
        },
    }
    main.context.get_using_provider.return_value = object()
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=True),
        handle_message=AsyncMock(),
    )
    event = make_event("aiocqhttp:GroupMessage:user_999_group_456")
    llm_request = object()
    event.request_llm.return_value = llm_request

    results = [item async for item in main.on_message(event)]

    assert results == [llm_request]
    conv_mgr.get_curr_conversation_id.assert_awaited_once_with(event.unified_msg_origin)
    conv_mgr.new_conversation.assert_not_called()
    conv_mgr.get_conversation.assert_awaited_once_with(
        event.unified_msg_origin,
        "cid-1",
    )
    event.request_llm.assert_called_once_with(
        prompt="hello",
        session_id="session-1",
        image_urls=[],
        conversation=conv,
    )


@pytest.mark.asyncio
async def test_on_message_does_not_clear_group_context_on_first_enabled_message():
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": True,
            "active_reply": {"enable": False},
        },
    }
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=False),
        handle_message=AsyncMock(),
        remove_session=AsyncMock(),
    )
    event = make_event()

    async for _ in main.on_message(event):
        pass

    main.group_chat_context.need_active_reply.assert_awaited_once_with(event)
    main.group_chat_context.handle_message.assert_awaited_once_with(event)
    main.group_chat_context.remove_session.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_records_json_card_and_checks_active_reply():
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": True,
            "active_reply": {"enable": False},
        },
    }
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=False),
        handle_message=AsyncMock(),
    )
    event = make_event()
    event.message_obj.message = [Json(data={"meta": {"news": {"title": "News"}}})]

    async for _ in main.on_message(event):
        pass

    main.group_chat_context.need_active_reply.assert_awaited_once_with(event)
    main.group_chat_context.handle_message.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_on_message_skips_recording_when_command_handler_matched():
    """A slash-command message (handlers_parsed_params non-empty) must not be
    recorded into the group context buffer."""
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": True,
            "active_reply": {"enable": False},
        },
    }
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=False),
        handle_message=AsyncMock(),
    )
    event = make_event(
        handlers_parsed_params={
            "astrbot.builtin_stars.builtin_commands.main_reset": {}
        },
    )

    async for _ in main.on_message(event):
        pass

    main.group_chat_context.need_active_reply.assert_awaited_once_with(event)
    main.group_chat_context.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_response_persists_final_complete_chain():
    """Persist the final runner response for an enabled group session."""
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_message_history_enable": True,
            "group_message_history_max_cnt": 700,
        },
    }
    main.context.message_history_manager.insert_message_chain = AsyncMock()
    event = make_event()
    event.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event.get_platform_name.return_value = "aiocqhttp"
    event.get_self_id.return_value = "bot-1"
    response = LLMResponse(
        role="assistant",
        result_chain=MessageChain([Plain("complete response")]),
    )

    await main.persist_llm_response(event, response)

    main.context.message_history_manager.insert_message_chain.assert_awaited_once_with(
        platform_id="aiocqhttp",
        user_id=event.unified_msg_origin,
        message_chain=response.result_chain,
        role="bot",
        sender_id="bot-1",
        sender_name="bot",
        max_messages=700,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("card_data", "expected"),
    [
        (
            {
                "meta": {
                    "detail_1": {
                        "title": "WeChat AI models",
                        "desc": "AI learning\nwith examples",
                        "qqdocurl": "https://example.com/detail",
                    }
                }
            },
            " [Shared Card: Title: WeChat AI models; Description: AI learning "
            "with examples; URL: https://example.com/detail]",
        ),
        (
            {
                "data": json.dumps(
                    {
                        "meta": {
                            "news": {
                                "title": "Wrapped card",
                                "jumpUrl": "https://example.com/news",
                            }
                        }
                    }
                )
            },
            " [Shared Card: Title: Wrapped card; URL: https://example.com/news]",
        ),
        ({"app": "com.example.unknown"}, " [Shared Card]"),
    ],
)
async def test_format_message_summarizes_json_card(card_data, expected):
    context = GroupChatContext(MagicMock(), MagicMock())
    event = MagicMock()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [Json(data=card_data)]

    formatted = await context._format_message(event, {})

    assert formatted.endswith(expected)


@pytest.mark.asyncio
async def test_format_message_truncates_long_json_card_fields():
    context = GroupChatContext(MagicMock(), MagicMock())
    event = MagicMock()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [
        Json(
            data={
                "meta": {"news": {"desc": "a" * 201}},
            }
        )
    ]

    formatted = await context._format_message(event, {})

    assert f"Description: {'a' * 200}...]" in formatted


def _caption_context(provider, *, max_size=1280):
    """Build a context whose config derives the caption limits via cfg()."""
    provider_settings = {
        "image_caption_prompt": "describe",
        "image_compress_options": {"max_size": max_size},
    }
    config = {
        "provider_ltm_settings": {
            "group_message_max_cnt": 1000,
            "image_caption": True,
            "image_caption_provider_id": "ollama/vision",
            "active_reply": {
                "enable": False,
                "method": "possibility_reply",
                "possibility_reply": 0.0,
                "whitelist": [],
            },
        },
        "provider_settings": provider_settings,
    }
    context = MagicMock()
    context.get_config.return_value = config
    context.get_provider_by_id.return_value = provider
    return context


def _caption_provider(caption: str):
    provider = MagicMock(spec=Provider)
    provider.text_chat = AsyncMock(
        return_value=SimpleNamespace(completion_text=caption),
    )
    return provider


@pytest.mark.asyncio
async def test_image_caption_uses_normalized_image(monkeypatch, tmp_path):
    """Animated images are prepared (montage JPEG) before captioning."""
    from astrbot.api.message_components import Image
    from astrbot.builtin_stars.astrbot import group_chat_context as gcc_module

    prepared = tmp_path / "model_image_montage.jpg"
    prepared.write_bytes(b"\xff\xd8fake-jpeg")
    seen: dict[str, object] = {}

    async def fake_prepare_model_image(image_ref, *, max_size, output_dir):
        seen.update(ref=image_ref, max_size=max_size)
        return str(prepared), True, True, "/tmp/original.gif"

    monkeypatch.setattr(gcc_module, "prepare_model_image", fake_prepare_model_image)

    provider = _caption_provider("a red square")
    gcc = gcc_module.GroupChatContext(
        MagicMock(), _caption_context(provider, max_size=640)
    )
    event = make_event()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [
        Image(file="anim.jpg", url="https://example.com/anim"),
    ]

    cfg = gcc.cfg(event)
    assert cfg["image_max_size"] == 640
    formatted = await gcc._format_message(event, cfg)

    assert "[Image: a red square]" in formatted
    assert seen == {"ref": "https://example.com/anim", "max_size": 640}
    prompt = provider.text_chat.await_args.kwargs["prompt"]
    assert "montage of evenly sampled frames" in prompt
    assert provider.text_chat.await_args.kwargs["image_urls"] == [str(prepared)]
    assert not prepared.exists(), "temporary prepared image must be cleaned up"


@pytest.mark.asyncio
async def test_image_caption_skips_oversized_and_bomb_images(monkeypatch):
    """Oversized or decompression-bomb images are skipped, never forwarded."""
    from astrbot.api.message_components import Image
    from astrbot.builtin_stars.astrbot import group_chat_context as gcc_module

    provider = _caption_provider("never")
    gcc = gcc_module.GroupChatContext(MagicMock(), _caption_context(provider))
    event = make_event()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [Image(file="big.png", url="https://x/big.png")]
    cfg = gcc.cfg(event)

    for error in (
        gcc_module.ImageInputTooLargeError("/tmp/big.png"),
        gcc_module.DecompressionBombError("too many pixels"),
    ):

        async def boom(*args, _error=error, **kwargs):
            raise _error

        monkeypatch.setattr(gcc_module, "prepare_model_image", boom)
        formatted = await gcc._format_message(event, cfg)

        assert gcc_module.IMAGE_CAPTION_SKIPPED in formatted
        provider.text_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_caption_removes_downloaded_source(monkeypatch, tmp_path):
    """A detached download under the temp dir is removed after captioning."""
    from astrbot.api.message_components import Image
    from astrbot.builtin_stars.astrbot import group_chat_context as gcc_module

    monkeypatch.setattr(gcc_module, "get_astrbot_temp_path", lambda: str(tmp_path))
    downloaded = tmp_path / "downloaded.png"
    downloaded.write_bytes(b"png")

    async def fake_prepare_model_image(image_ref, *, max_size, output_dir):
        return str(downloaded), False, False, str(downloaded)

    monkeypatch.setattr(gcc_module, "prepare_model_image", fake_prepare_model_image)

    provider = _caption_provider("a download")
    gcc = gcc_module.GroupChatContext(MagicMock(), _caption_context(provider))
    event = make_event()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [Image(file="d.png", url="https://x/d.png")]

    formatted = await gcc._format_message(event, gcc.cfg(event))

    assert "[Image: a download]" in formatted
    assert not downloaded.exists(), "detached download must be cleaned up"


@pytest.mark.asyncio
async def test_image_caption_falls_back_to_original_ref(monkeypatch):
    """A preparation failure keeps the previous behaviour (raw reference)."""
    from astrbot.api.message_components import Image
    from astrbot.builtin_stars.astrbot import group_chat_context as gcc_module

    async def boom(*args, **kwargs):
        raise RuntimeError("download failed")

    monkeypatch.setattr(gcc_module, "prepare_model_image", boom)

    provider = _caption_provider("fallback")
    gcc = gcc_module.GroupChatContext(MagicMock(), _caption_context(provider))
    event = make_event()
    event.message_obj = SimpleNamespace(sender=SimpleNamespace(nickname="Alice"))
    event.get_messages.return_value = [Image(file="anim.jpg", url="https://x/anim")]

    formatted = await gcc._format_message(event, gcc.cfg(event))

    assert "[Image: fallback]" in formatted
    assert provider.text_chat.await_args.kwargs["image_urls"] == ["https://x/anim"]
