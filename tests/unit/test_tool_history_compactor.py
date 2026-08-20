from astrbot.core.agent.context.truncator import ContextTruncator
from astrbot.core.agent.message import Message
from astrbot.core.agent.tool_history_compactor import compact_consumed_tool_history


def _tool_call(call_id: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "lookup", "arguments": "{}"},
    }


def test_compact_consumed_tool_results_preserves_pairing_fields():
    history = [
        {"role": "assistant", "tool_calls": [_tool_call("one")]},
        {"role": "tool", "tool_call_id": "one", "content": "large result"},
        {"role": "assistant", "content": "Answer based on result"},
    ]

    projected = compact_consumed_tool_history(history, "omitted")

    assert projected[0]["tool_calls"] == history[0]["tool_calls"]
    assert projected[1]["tool_call_id"] == "one"
    assert projected[1]["content"] == "omitted"
    assert history[1]["content"] == "large result"


def test_compactor_keeps_unconsumed_or_provider_state_tool_transactions():
    unconsumed = [
        {"role": "assistant", "tool_calls": [_tool_call("one")]},
        {"role": "tool", "tool_call_id": "one", "content": "result"},
    ]
    stateful = [
        {"role": "assistant", "tool_calls": [_tool_call("two")]},
        {
            "role": "tool",
            "tool_call_id": "two",
            "content": "result",
            "provider_state": {"provider_type": "x", "provider_id": "x", "data": {}},
        },
        {"role": "assistant", "content": "answer"},
    ]

    assert compact_consumed_tool_history(unconsumed) == unconsumed
    assert compact_consumed_tool_history(stateful) == stateful


def test_compacted_parallel_results_remain_valid_for_context_truncator():
    history = [
        {"role": "assistant", "tool_calls": [_tool_call("one"), _tool_call("two")]},
        {"role": "tool", "tool_call_id": "one", "content": "first"},
        {"role": "tool", "tool_call_id": "two", "content": "second"},
        {"role": "assistant", "content": "answer"},
    ]
    projected = compact_consumed_tool_history(history)
    messages = [Message.model_validate(message) for message in projected]

    fixed = ContextTruncator().fix_messages(messages)

    assert [message.role for message in fixed] == [
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]
    assert [message.tool_call_id for message in fixed[1:3]] == ["one", "two"]
