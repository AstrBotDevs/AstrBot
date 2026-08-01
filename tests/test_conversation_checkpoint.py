from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.message import (
    AssistantMessageSegment,
    CheckpointData,
    CheckpointMessageSegment,
    Message,
    TextPart,
    ToolCall,
    ToolCallMessageSegment,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
    get_checkpoint_id,
    strip_checkpoint_messages,
)
from astrbot.core.db.po import Conversation
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, ToolCallsResult
from astrbot.core.provider.provider import Provider
from astrbot.dashboard.services.chat_service import find_turn_range


def test_checkpoint_message_segment_round_trip():
    message = CheckpointMessageSegment(content=CheckpointData(id="cp-1"))

    dumped = message.model_dump()

    assert dumped == {"role": "_checkpoint", "content": {"id": "cp-1"}}
    assert get_checkpoint_id(dumped) == "cp-1"
    assert Message.model_validate(dumped).content == CheckpointData(id="cp-1")


def test_checkpoint_requires_checkpoint_data():
    with pytest.raises(ValueError, match="checkpoint message content"):
        Message(role="_checkpoint", content="cp-1")


def test_checkpoint_data_is_only_allowed_for_checkpoint_role():
    with pytest.raises(ValueError, match="CheckpointData is only allowed"):
        Message(role="user", content=CheckpointData(id="cp-1"))


def test_strip_checkpoint_messages():
    history = [
        {"role": "user", "content": "hello"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "assistant", "content": "world"},
    ]

    assert strip_checkpoint_messages(history) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_bind_and_dump_checkpoint_messages_preserves_boundaries():
    history = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old bot"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "next user"},
    ]

    messages = bind_checkpoint_messages(history)

    assert len(messages) == 3
    assert messages[1]._checkpoint_after == CheckpointData(id="cp-1")
    assert dump_messages_with_checkpoints(messages) == [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old bot"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "next user"},
    ]


def test_dump_checkpoint_messages_drops_checkpoint_when_message_is_dropped():
    history = [
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old bot"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "latest user"},
    ]

    messages = bind_checkpoint_messages(history)

    assert dump_messages_with_checkpoints(messages[2:]) == [
        {"role": "user", "content": "latest user"},
    ]


def test_dump_messages_filters_temp_content_parts():
    messages = [
        Message(
            role="user",
            content=[
                TextPart(text="persisted"),
                TextPart(text="temporary").mark_as_temp(),
            ],
        ),
        Message(role="assistant", content="ok"),
    ]

    assert dump_messages_with_checkpoints(messages) == [
        {"role": "user", "content": [{"type": "text", "text": "persisted"}]},
        {"role": "assistant", "content": "ok"},
    ]


def test_content_part_no_save_round_trip_from_dict():
    message = Message.model_validate(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "persisted"},
                {"type": "text", "text": "temporary", "_no_save": True},
            ],
        }
    )

    assert isinstance(message.content, list)
    assert message.content[0]._no_save is False
    assert message.content[1]._no_save is True
    assert dump_messages_with_checkpoints([message]) == [
        {"role": "user", "content": [{"type": "text", "text": "persisted"}]},
    ]


@pytest.mark.asyncio
async def test_provider_request_assemble_context_preserves_temp_content_part_marker():
    request = ProviderRequest(
        prompt="hello",
        extra_user_content_parts=[TextPart(text="temporary").mark_as_temp()],
    )

    message = Message.model_validate(await request.assemble_context())

    assert isinstance(message.content, list)
    assert message.content[1].text == "temporary"
    assert message.content[1]._no_save is True
    assert dump_messages_with_checkpoints([message]) == [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]},
    ]


def test_provider_ensure_message_to_dicts_skips_checkpoints():
    messages = [
        Message(role="user", content="hello"),
        CheckpointMessageSegment(content=CheckpointData(id="cp-1")),
        {"role": "assistant", "content": "world"},
        {"role": "_checkpoint", "content": {"id": "cp-2"}},
    ]

    assert Provider._ensure_message_to_dicts(object(), messages) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_chat_service_find_turn_range():
    history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "_checkpoint", "content": {"id": "cp-1"}},
        {"role": "user", "content": "c"},
        {"role": "assistant", "content": "d"},
        {"role": "_checkpoint", "content": {"id": "cp-2"}},
    ]

    assert find_turn_range(history, "cp-2") == (3, 5)
    assert find_turn_range(history, "missing") is None


@pytest.mark.asyncio
async def test_failed_llm_response_persists_checkpoint_for_retry():
    conversation_manager = AsyncMock()
    stage = InternalAgentSubStage()
    stage.conv_manager = conversation_manager
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:test",
        get_extra=lambda key: {"llm_checkpoint_id": "cp-1"}.get(key),
    )
    request = ProviderRequest(
        conversation=Conversation(
            platform_id="webchat",
            user_id="webchat:FriendMessage:test",
            cid="conversation-1",
        )
    )

    await stage._save_to_history(
        event,
        request,
        LLMResponse(role="err", completion_text="upstream failed"),
        [Message(role="user", content="hello")],
        runner_stats=None,
    )

    conversation_manager.update_conversation.assert_awaited_once_with(
        "webchat:FriendMessage:test",
        "conversation-1",
        history=[
            {"role": "user", "content": "hello"},
            {"role": "_checkpoint", "content": {"id": "cp-1"}},
        ],
        token_usage=None,
    )


@pytest.mark.asyncio
async def test_terminal_tool_result_persists_history_without_checkpoint():
    conversation_manager = AsyncMock()
    stage = InternalAgentSubStage()
    stage.conv_manager = conversation_manager
    event = SimpleNamespace(
        unified_msg_origin="qq:GroupMessage:test",
        get_extra=lambda _key: None,
    )
    tool_call = ToolCall(
        id="call-1",
        function=ToolCall.FunctionBody(name="stay_silent", arguments="{}"),
    )
    assistant_message = AssistantMessageSegment(tool_calls=[tool_call])
    tool_message = ToolCallMessageSegment(
        content="The tool has no return value.",
        tool_call_id="call-1",
    )
    request = ProviderRequest(
        conversation=Conversation(
            platform_id="qq",
            user_id="qq:GroupMessage:test",
            cid="conversation-1",
            token_usage=1234,
        ),
        tool_calls_result=ToolCallsResult(
            tool_calls_info=assistant_message,
            tool_calls_result=[tool_message],
        ),
    )

    await stage._save_to_history(
        event,
        request,
        None,
        [
            Message(role="user", content="latest group observation"),
            assistant_message,
            tool_message,
        ],
        runner_stats=None,
    )

    conversation_manager.update_conversation.assert_awaited_once_with(
        "qq:GroupMessage:test",
        "conversation-1",
        history=[
            {"role": "user", "content": "latest group observation"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call-1",
                        "function": {
                            "name": "stay_silent",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": "The tool has no return value.",
                "tool_call_id": "call-1",
            },
        ],
        token_usage=1234,
    )


@pytest.mark.asyncio
async def test_terminal_tool_result_with_checkpoint_uses_none_token_usage():
    conversation_manager = AsyncMock()
    stage = InternalAgentSubStage()
    stage.conv_manager = conversation_manager
    event = SimpleNamespace(
        unified_msg_origin="qq:GroupMessage:test",
        get_extra=lambda key: {"llm_checkpoint_id": "cp-1"}.get(key),
    )
    tool_call = ToolCall(
        id="call-1",
        function=ToolCall.FunctionBody(name="stay_silent", arguments="{}"),
    )
    assistant_message = AssistantMessageSegment(tool_calls=[tool_call])
    tool_message = ToolCallMessageSegment(
        content="The tool has no return value.",
        tool_call_id="call-1",
    )
    request = ProviderRequest(
        conversation=Conversation(
            platform_id="qq",
            user_id="qq:GroupMessage:test",
            cid="conversation-1",
            token_usage=1234,
        ),
        tool_calls_result=ToolCallsResult(
            tool_calls_info=assistant_message,
            tool_calls_result=[tool_message],
        ),
    )

    await stage._save_to_history(
        event,
        request,
        None,
        [
            Message(role="user", content="latest group observation"),
            assistant_message,
            tool_message,
        ],
        runner_stats=None,
    )

    conversation_manager.update_conversation.assert_awaited_once_with(
        "qq:GroupMessage:test",
        "conversation-1",
        history=[
            {"role": "user", "content": "latest group observation"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call-1",
                        "function": {
                            "name": "stay_silent",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": "The tool has no return value.",
                "tool_call_id": "call-1",
            },
            {"role": "_checkpoint", "content": {"id": "cp-1"}},
        ],
        token_usage=None,
    )


@pytest.mark.asyncio
async def test_empty_response_without_tool_result_skips_history_save():
    conversation_manager = AsyncMock()
    stage = InternalAgentSubStage()
    stage.conv_manager = conversation_manager
    event = SimpleNamespace(
        unified_msg_origin="qq:GroupMessage:test",
        get_extra=lambda _key: None,
    )
    request = ProviderRequest(
        conversation=Conversation(
            platform_id="qq",
            user_id="qq:GroupMessage:test",
            cid="conversation-1",
        )
    )

    await stage._save_to_history(
        event,
        request,
        None,
        [Message(role="user", content="latest group observation")],
        runner_stats=None,
    )

    conversation_manager.update_conversation.assert_not_awaited()
