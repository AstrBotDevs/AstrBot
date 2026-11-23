from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.provider import ProviderRequest
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.platform.message_type import MessageType

UMO = "aiocqhttp:GroupMessage:group_456"


def _config(*, icl_enable: bool) -> dict:
    return {
        "wake_prefix": ["/"],
        "platform_settings": {
            "empty_mention_waiting": True,
            "empty_mention_waiting_need_reply": True,
        },
        "provider_settings": {"image_caption_prompt": ""},
        "provider_ltm_settings": {
            "group_icl_enable": icl_enable,
            "image_caption": False,
            "active_reply": {
                "enable": False,
                "method": "possibility_reply",
                "possibility_reply": 0.1,
            },
        },
    }


def _make_event(components: list, nickname: str) -> MagicMock:
    extras: dict[str, object] = {}
    event = MagicMock()
    event.unified_msg_origin = UMO
    event.get_self_id.return_value = "bot"
    event.get_platform_id.return_value = "aiocqhttp"
    event.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event.get_messages.return_value = components
    event.message_obj = SimpleNamespace(
        message=components,
        sender=SimpleNamespace(nickname=nickname),
    )
    event.get_extra.side_effect = extras.get
    event.set_extra.side_effect = extras.__setitem__
    return event


def _make_main(icl_enable: bool) -> Main:
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = _config(icl_enable=icl_enable)
    main.context.conversation_manager = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="cid-1"),
        get_conversation=AsyncMock(return_value=SimpleNamespace(cid="cid-1")),
    )
    main.group_chat_context = GroupChatContext(MagicMock(), main.context)
    return main


async def _run_empty_mention(main: Main, event: MagicMock) -> None:
    """Drive handle_empty_mention up to the LLM request it yields."""
    handler = main.handle_empty_mention(event)
    await anext(handler)
    await handler.aclose()


@pytest.mark.asyncio
async def test_empty_mention_injects_unreplied_group_messages():
    main = _make_main(icl_enable=True)
    earlier = _make_event([Comp.Plain("do you like cats?")], "alice")
    await main.group_chat_context.handle_message(earlier)

    mention = _make_event([Comp.At(qq="bot", name="bot")], "bob")
    await _run_empty_mention(main, mention)

    req = ProviderRequest(prompt="ignored")
    await main.group_chat_context.on_req_llm(mention, req)

    injected = "".join(part.text for part in req.extra_user_content_parts)
    assert "do you like cats?" in injected
    assert "alice" in injected


@pytest.mark.asyncio
async def test_empty_mention_does_not_record_when_group_context_disabled():
    main = _make_main(icl_enable=False)
    earlier = _make_event([Comp.Plain("do you like cats?")], "alice")
    await main.group_chat_context.handle_message(earlier)

    mention = _make_event([Comp.At(qq="bot", name="bot")], "bob")
    await _run_empty_mention(main, mention)

    assert mention.get_extra("_group_context_record_id") is None
