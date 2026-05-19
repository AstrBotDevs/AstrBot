from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.db.po import Conversation
from astrbot.core.group_message_flow_mgr import GroupMessageFlowManager
from astrbot.core.message.components import Plain, Reply
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse, ProviderRequest


class ConcreteAstrMessageEvent(AstrMessageEvent):
    async def send(self, message):
        await super().send(message)


class SyncDictComponent:
    def to_dict(self):
        return {"type": "sync", "data": {"items": [Plain(text="nested sync")]}}


def _flow_config(overrides: dict | None = None) -> dict:
    config = deepcopy(DEFAULT_CONFIG)
    config["provider_ltm_settings"]["group_icl_enable"] = True
    config["provider_ltm_settings"]["group_context_mode"] = "flow"
    config["provider_ltm_settings"]["group_flow_max_records"] = 0
    config["provider_ltm_settings"]["image_caption"] = False
    config["provider_ltm_settings"]["active_reply"]["enable"] = False
    if overrides:
        config["provider_ltm_settings"].update(overrides)
    return config


def _event(text: str, sender_id: str = "user-1", sender_name: str = "Alice"):
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.self_id = "bot-1"
    message.session_id = "group-1"
    message.message_id = f"msg-{text}"
    message.sender = MessageMember(user_id=sender_id, nickname=sender_name)
    message.group_id = "group-1"
    message.message = [Plain(text=text)]
    message.message_str = text
    message.raw_message = None
    return ConcreteAstrMessageEvent(
        message_str=text,
        message_obj=message,
        platform_meta=PlatformMetadata(
            name="aiocqhttp",
            description="test",
            id="default",
        ),
        session_id="group-1",
    )


def _conversation(cid: str = "conv-1") -> Conversation:
    return Conversation(
        platform_id="default",
        user_id="default:GroupMessage:group-1",
        cid=cid,
        history=[],
    )


@pytest.fixture
def flow_context(temp_db):
    return _flow_context(temp_db)


def _flow_context(temp_db, config: dict | None = None):
    manager = GroupMessageFlowManager(temp_db)
    config = config or _flow_config()
    return SimpleNamespace(
        get_config=lambda umo=None: config,
        get_using_provider=lambda *args, **kwargs: None,
        get_provider_by_id=lambda *args, **kwargs: None,
        group_message_flow_manager=manager,
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value="conv-1"),
        ),
    )


@pytest.mark.asyncio
async def test_group_flow_delta_excludes_current_message(temp_db, flow_context):
    ltm = LongTermMemory(AsyncMock(), flow_context)
    previous = _event("previous message", sender_name="Alice")
    trigger = _event("trigger message", sender_name="Bob")

    await ltm.handle_message(previous)
    await ltm.handle_message(trigger)

    req = ProviderRequest(prompt="trigger message", conversation=_conversation())
    await ltm.on_req_llm(trigger, req)

    assert "<group_messages_delta>" in req.system_prompt
    assert "previous message" in req.system_prompt
    assert "Alice" in req.system_prompt
    assert "trigger message" not in req.system_prompt
    assert "message_id" not in req.system_prompt
    assert "seq_" not in req.system_prompt


@pytest.mark.asyncio
async def test_group_flow_cursor_advances_between_turns(temp_db, flow_context):
    ltm = LongTermMemory(AsyncMock(), flow_context)
    first = _event("first background")
    first_trigger = _event("first trigger")
    second_background = _event("second background", sender_name="Carol")
    second_trigger = _event("second trigger")

    await ltm.handle_message(first)
    await ltm.handle_message(first_trigger)
    first_req = ProviderRequest(prompt="first trigger", conversation=_conversation())
    await ltm.on_req_llm(first_trigger, first_req)
    await ltm.after_req_llm(
        first_trigger,
        LLMResponse(role="assistant", completion_text="first response"),
    )

    await ltm.handle_message(second_background)
    await ltm.handle_message(second_trigger)
    second_req = ProviderRequest(prompt="second trigger", conversation=_conversation())
    await ltm.on_req_llm(second_trigger, second_req)

    assert "first background" not in second_req.system_prompt
    assert "first trigger" not in second_req.system_prompt
    assert "second background" in second_req.system_prompt
    assert "second trigger" not in second_req.system_prompt


@pytest.mark.asyncio
async def test_group_flow_cursor_advances_only_after_llm_success(temp_db, flow_context):
    ltm = LongTermMemory(AsyncMock(), flow_context)
    background = _event("background before first trigger")
    trigger = _event("first trigger")
    second_trigger = _event("second trigger")

    await ltm.handle_message(background)
    await ltm.handle_message(trigger)
    first_req = ProviderRequest(prompt="first trigger", conversation=_conversation())
    await ltm.on_req_llm(trigger, first_req)

    await ltm.handle_message(second_trigger)
    retry_req = ProviderRequest(prompt="second trigger", conversation=_conversation())
    await ltm.on_req_llm(second_trigger, retry_req)

    assert "background before first trigger" in retry_req.system_prompt
    assert "first trigger" in retry_req.system_prompt
    assert "second trigger" not in retry_req.system_prompt

    await ltm.after_req_llm(
        trigger,
        LLMResponse(role="assistant", completion_text="first response"),
    )
    committed_req = ProviderRequest(
        prompt="second trigger", conversation=_conversation()
    )
    await ltm.on_req_llm(second_trigger, committed_req)

    assert "background before first trigger" not in committed_req.system_prompt
    assert "first trigger" not in committed_req.system_prompt
    assert "second trigger" not in committed_req.system_prompt


@pytest.mark.asyncio
async def test_group_flow_delta_limit_keeps_tail_messages(temp_db):
    context = _flow_context(
        temp_db,
        _flow_config({"group_flow_max_delta_messages": 2}),
    )
    ltm = LongTermMemory(AsyncMock(), context)
    first = _event("first background")
    second = _event("second background")
    third = _event("third background")
    trigger = _event("trigger message")

    for event in [first, second, third, trigger]:
        await ltm.handle_message(event)

    req = ProviderRequest(prompt="trigger message", conversation=_conversation())
    await ltm.on_req_llm(trigger, req)

    assert "first background" not in req.system_prompt
    assert "second background" in req.system_prompt
    assert "third background" in req.system_prompt
    assert "trigger message" not in req.system_prompt


@pytest.mark.asyncio
async def test_group_flow_delta_truncates_each_message(temp_db):
    context = _flow_context(
        temp_db,
        _flow_config({"group_flow_max_message_chars": 32}),
    )
    ltm = LongTermMemory(AsyncMock(), context)
    background = _event("hello " + ("x" * 100) + "TAIL_SHOULD_NOT_APPEAR")
    trigger = _event("trigger message")

    await ltm.handle_message(background)
    await ltm.handle_message(trigger)

    req = ProviderRequest(prompt="trigger message", conversation=_conversation())
    await ltm.on_req_llm(trigger, req)

    assert "hello" in req.system_prompt
    assert "TAIL_SHOULD_NOT_APPEAR" not in req.system_prompt
    assert "trigger message" not in req.system_prompt


@pytest.mark.asyncio
async def test_group_flow_reset_moves_cursor_to_latest(temp_db, flow_context):
    ltm = LongTermMemory(AsyncMock(), flow_context)
    before_reset = _event("before reset")
    reset_command = _event("/reset")
    after_reset_trigger = _event("after reset trigger")

    await ltm.handle_message(before_reset)
    await ltm.handle_message(reset_command)
    await ltm.remove_session(reset_command)
    await ltm.handle_message(after_reset_trigger)

    req = ProviderRequest(prompt="after reset trigger", conversation=_conversation())
    await ltm.on_req_llm(after_reset_trigger, req)

    assert "before reset" not in req.system_prompt
    assert "/reset" not in req.system_prompt
    assert "after reset trigger" not in req.system_prompt


@pytest.mark.asyncio
async def test_group_flow_serializes_nested_reply_components(temp_db, flow_context):
    ltm = LongTermMemory(AsyncMock(), flow_context)
    event = _event("reply wrapper")
    event.message_obj.message = [
        Reply(id="quoted-1", chain=[Plain(text="quoted text")]),
        Plain(text="reply wrapper"),
    ]

    await ltm.handle_message(event)

    rows = await flow_context.group_message_flow_manager.get_records_after(
        flow_session_id="default:GroupMessage:group-1",
        after_id=0,
    )

    assert len(rows) == 1
    assert rows[0].content[0]["type"] == "reply"
    assert rows[0].content[0]["data"]["chain"][0]["data"]["text"] == "quoted text"


@pytest.mark.asyncio
async def test_group_flow_serializes_sync_to_dict_components(temp_db, flow_context):
    ltm = LongTermMemory(AsyncMock(), flow_context)

    content = await ltm._components_to_dict([SyncDictComponent()])

    assert content == [
        {
            "type": "sync",
            "data": {"items": [{"type": "text", "data": {"text": "nested sync"}}]},
        }
    ]
