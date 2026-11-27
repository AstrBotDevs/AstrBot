import json
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image as PILImage

from astrbot.api.message_components import Image, Json, Plain
from astrbot.api.provider import (
    DecisionChoiceAnswer,
    DecisionProvider,
    LLMResponse,
    Provider,
)
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_type import MessageType
from astrbot.core.provider.decision import DecisionService


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


@pytest.mark.asyncio
@pytest.mark.parametrize("invert", [True, False])
async def test_group_caption_decides_each_image_before_captioning(tmp_path, invert):
    mock_context = MagicMock()
    context = GroupChatContext(MagicMock(), mock_context)
    config = deepcopy(DEFAULT_CONFIG)
    settings = config["provider_ltm_settings"]
    settings.update(
        group_icl_enable=True, image_caption=True, image_caption_provider_id="caption"
    )
    assert settings["image_caption_decision"]["invert"] is False
    settings["image_caption_decision"].update(
        provider_id="judge",
        threshold=0.75,
        invert=invert,
        prompt="Is it red?",
        placeholder="Skipped",
    )
    mock_context.get_config.return_value = config
    manager = MagicMock()
    judge = MagicMock(spec=DecisionProvider)
    judge.provider_config = {"modalities": ["image"]}
    manager.get_provider_by_id = AsyncMock(return_value=judge)
    context.context.decision = DecisionService(manager)
    judge.ask.side_effect = [
        {"answer": DecisionChoiceAnswer("o1", 0.9, {"o1": 0.9, "o2": 0.1}, 0.75)},
        {"answer": DecisionChoiceAnswer("o2", 0.9, {"o1": 0.1, "o2": 0.9}, 0.75)},
        {"answer": DecisionChoiceAnswer("o2", 0.9, {"o1": 0.1, "o2": 0.9}, 0.74)},
    ]
    caption = MagicMock(spec=Provider)
    caption.text_chat.return_value = LLMResponse(
        role="assistant", completion_text="Described"
    )
    mock_context.get_provider_by_id.return_value = caption
    event = make_event()
    event.message_obj.sender = SimpleNamespace(nickname="Alice")
    images = []
    for color in ("red", "blue", "white"):
        path = tmp_path / f"{color}.gif"
        PILImage.new("RGB", (32, 32), color).save(path)
        images.append(Image.fromFileSystem(path))
    event.get_messages.return_value = [images[0], Plain("between"), images[1], images[2]]

    rendered = await context._format_message(event, context.cfg(event))

    assert rendered.endswith(
        "[Image: Described] between [Image: Skipped] [Image: Skipped]"
        if invert
        else "[Image: Skipped] between [Image: Described] [Image: Skipped]"
    )
    assert judge.ask.await_count == 3
    for call, color in zip(
        judge.ask.await_args_list, [(255, 0, 0), (0, 0, 255), (255, 255, 255)], strict=True
    ):
        questions, image = call.args
        assert questions["answer"].instructions == "Is it red?"
        with PILImage.open(BytesIO(image.to_bytes())) as preview:
            assert preview.size == (280, 280)
            assert preview.convert("RGB").getpixel((140, 140)) == pytest.approx(
                color, abs=2
            )
    caption.text_chat.assert_awaited_once()
    allowed = judge.ask.await_args_list[0 if invert else 1].args[1]
    assert caption.text_chat.await_args.kwargs["image_urls"] == [allowed.to_data_url()]
    mock_context.get_provider_by_id.assert_called_once_with("caption")
    assert all(
        call.args == ("judge",) for call in manager.get_provider_by_id.await_args_list
    )
