import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.message_components import Image, Plain
from astrbot.api.provider import LLMResponse, ProviderRequest
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


def make_group_context_event(message, nickname="user"):
    event = MagicMock()
    event.unified_msg_origin = "aiocqhttp:GroupMessage:user_123_group_456"
    event.message_obj = SimpleNamespace(
        message=message,
        sender=SimpleNamespace(nickname=nickname),
    )
    event.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event.get_messages.return_value = message

    store, get_extra, set_extra = _make_extras_store()
    event.get_extra.side_effect = get_extra
    event.set_extra.side_effect = set_extra
    return event


def make_group_chat_context():
    context = MagicMock()
    context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_message_max_cnt": 1000,
            "image_caption": True,
            "image_caption_provider_id": "vision-provider",
            "active_reply": {
                "enable": False,
                "method": "possibility_reply",
                "possibility_reply": 0,
            },
        },
        "provider_settings": {"image_caption_prompt": "Describe the image."},
    }
    return GroupChatContext(MagicMock(), context)


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
async def test_group_context_preserves_message_order_while_captioning_image():
    group_context = make_group_chat_context()
    caption_started = asyncio.Event()
    release_caption = asyncio.Event()

    async def delayed_caption(*_args):
        caption_started.set()
        await release_caption.wait()
        return "a driving test conversation"

    group_context.get_image_caption = delayed_caption
    image_event = make_group_context_event([Image.fromURL("https://example.com/a.jpg")])
    text_event = make_group_context_event([Plain("I think I might fail")])

    image_task = asyncio.create_task(group_context.handle_message(image_event))
    await caption_started.wait()
    text_task = asyncio.create_task(group_context.handle_message(text_event))
    await asyncio.sleep(0)
    text_completed_before_caption = text_task.done()

    release_caption.set()
    await asyncio.gather(image_task, text_task)

    req = ProviderRequest()
    await group_context.on_req_llm(text_event, req)

    assert not text_completed_before_caption
    assert len(req.extra_user_content_parts) == 1
    assert (
        "[Image: a driving test conversation]" in req.extra_user_content_parts[0].text
    )


@pytest.mark.asyncio
async def test_group_context_keeps_image_placeholder_when_caption_fails():
    group_context = make_group_chat_context()
    group_context.get_image_caption = AsyncMock(
        side_effect=RuntimeError("caption failed")
    )
    image_event = make_group_context_event([Image.fromURL("https://example.com/a.jpg")])

    await group_context.handle_message(image_event)

    records = list(group_context.raw_records[image_event.unified_msg_origin])
    assert len(records) == 1
    assert records[0].endswith(":  [Image]")


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
