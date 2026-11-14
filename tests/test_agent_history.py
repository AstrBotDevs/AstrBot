from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.message import (
    AssistantMessageSegment,
    Message,
    TextPart,
    ToolCall,
    ToolCallMessageSegment,
    dump_messages,
    load_messages,
)
from astrbot.core.astr_agent_runtime.history import save_agent_history
from astrbot.core.db.po import Conversation
from astrbot.core.provider.entities import LLMResponse, ProviderRequest, ToolCallsResult
from astrbot.core.provider.provider import Provider


@pytest.mark.parametrize("role", ["_checkpoint", "unknown"])
def test_load_messages_rejects_non_message_roles(role):
    with pytest.raises(ValueError, match="role"):
        load_messages([{"role": role, "content": "invalid"}])


def test_working_messages_round_trip_preserves_temporary_markers():
    history = [
        {"role": "user", "content": "transient", "_no_save": True},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "persisted"},
                {"type": "text", "text": "temporary", "_no_save": True},
            ],
        },
        {"role": "assistant", "content": "ok"},
    ]

    messages = load_messages(history)

    assert messages[0]._no_save is True
    assert messages[1].content[1]._no_save is True
    assert dump_messages(messages, include_temporary=True) == history
    assert dump_messages([message for message in messages if not message._no_save]) == [
        {"role": "user", "content": [{"type": "text", "text": "persisted"}]},
        {"role": "assistant", "content": "ok"},
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

    assert dump_messages(messages) == [
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
    assert dump_messages([message]) == [
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
    assert dump_messages([message]) == [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]},
    ]


def test_provider_ensure_message_to_dicts_accepts_models_and_dicts():
    messages = [
        Message(role="user", content="hello"),
        {"role": "assistant", "content": "world"},
    ]

    assert Provider._ensure_message_to_dicts(object(), messages) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


@pytest.mark.asyncio
async def test_failed_llm_response_preserves_input_for_linked_turn_retry():
    writer = SimpleNamespace(turn_id="turn-1", save_history=AsyncMock())
    commit = AsyncMock()
    request = ProviderRequest(
        conversation=Conversation(
            platform_id="webchat",
            user_id="webchat:FriendMessage:test",
            cid="conversation-1",
        )
    )

    await save_agent_history(
        req=request,
        llm_response=LLMResponse(role="err", completion_text="upstream failed"),
        all_messages=[Message(role="user", content="hello")],
        commit=commit,
        writer=writer,
        runner_stats=None,
    )

    writer.save_history.assert_awaited_once_with(
        [
            {"role": "user", "content": "hello"},
        ],
    )
    commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_aborted_response_persists_synthetic_stop_turn():
    conversation_manager = AsyncMock()
    context = SimpleNamespace(conversation_manager=conversation_manager)
    event = SimpleNamespace(
        unified_msg_origin="webchat:FriendMessage:test",
    )
    request = ProviderRequest(
        conversation=Conversation(
            platform_id="webchat",
            user_id="webchat:FriendMessage:test",
            cid="conversation-1",
        )
    )

    await save_agent_history(
        req=request,
        llm_response=LLMResponse(role="assistant", completion_text="Output stopped."),
        all_messages=[
            Message(role="user", content="Explain the result."),
            Message(role="user", content=[TextPart(text="Stop output.")]),
            Message(role="assistant", content=[TextPart(text="Output stopped.")]),
        ],
        commit=lambda history, token_usage: (
            context.conversation_manager.update_conversation(
                event.unified_msg_origin,
                request.conversation.cid,
                history=history,
                token_usage=token_usage,
            )
        ),
        runner_stats=None,
        user_aborted=True,
    )

    conversation_manager.update_conversation.assert_awaited_once_with(
        "webchat:FriendMessage:test",
        "conversation-1",
        history=[
            {"role": "user", "content": "Explain the result."},
            {
                "role": "user",
                "content": [{"type": "text", "text": "Stop output."}],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Output stopped."}],
            },
        ],
        token_usage=None,
    )


@pytest.mark.asyncio
async def test_terminal_tool_result_persists_private_history():
    conversation_manager = AsyncMock()
    context = SimpleNamespace(conversation_manager=conversation_manager)
    event = SimpleNamespace(
        unified_msg_origin="qq:GroupMessage:test",
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

    await save_agent_history(
        req=request,
        llm_response=None,
        all_messages=[
            Message(role="user", content="latest group observation"),
            assistant_message,
            tool_message,
        ],
        commit=lambda history, token_usage: (
            context.conversation_manager.update_conversation(
                event.unified_msg_origin,
                request.conversation.cid,
                history=history,
                token_usage=token_usage,
            )
        ),
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
async def test_terminal_tool_result_with_turn_uses_none_token_usage():
    writer = SimpleNamespace(turn_id="turn-1", save_history=AsyncMock())
    commit = AsyncMock()
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

    await save_agent_history(
        req=request,
        llm_response=None,
        all_messages=[
            Message(role="user", content="latest group observation"),
            assistant_message,
            tool_message,
        ],
        commit=commit,
        writer=writer,
        runner_stats=None,
    )

    writer.save_history.assert_awaited_once_with(
        [
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
    )
    commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_response_without_tool_result_skips_history_save():
    conversation_manager = AsyncMock()
    context = SimpleNamespace(conversation_manager=conversation_manager)
    event = SimpleNamespace(
        unified_msg_origin="qq:GroupMessage:test",
    )
    request = ProviderRequest(
        conversation=Conversation(
            platform_id="qq",
            user_id="qq:GroupMessage:test",
            cid="conversation-1",
        )
    )

    await save_agent_history(
        req=request,
        llm_response=None,
        all_messages=[Message(role="user", content="latest group observation")],
        commit=lambda history, token_usage: (
            context.conversation_manager.update_conversation(
                event.unified_msg_origin,
                request.conversation.cid,
                history=history,
                token_usage=token_usage,
            )
        ),
        runner_stats=None,
    )

    conversation_manager.update_conversation.assert_not_awaited()
