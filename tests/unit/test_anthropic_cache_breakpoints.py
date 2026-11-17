import copy

from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

apply = ProviderAnthropic._apply_explicit_prompt_cache_breakpoints
MARK = {"type": "ephemeral"}


def test_marks_system_and_conversation_tail_without_changing_content():
    tool_result = {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}
    history = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}],
        },
        {"role": "user", "content": [tool_result]},
    ]
    payloads = {"system": [{"type": "text", "text": "sys"}], "messages": history}
    original = copy.deepcopy(payloads)
    apply(payloads)
    assert payloads["system"][-1]["cache_control"] == MARK
    assert payloads["messages"][-1]["content"][-1]["cache_control"] == MARK
    # Only the tail is marked, and the caller's block object is not mutated.
    assert "cache_control" not in tool_result
    assert payloads["messages"][:2] == original["messages"][:2]
    stripped = copy.deepcopy(payloads)
    stripped["system"][-1].pop("cache_control")
    stripped["messages"][-1]["content"][-1].pop("cache_control")
    assert stripped == original


def test_string_tail_becomes_marked_text_block():
    payloads = {"messages": [{"role": "user", "content": "hi"}]}
    apply(payloads)
    assert payloads["messages"][-1]["content"] == [
        {"type": "text", "text": "hi", "cache_control": MARK}
    ]


def test_skips_uncacheable_blocks_and_respects_limit():
    payloads = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "answer"},
                    {"type": "thinking", "thinking": "t", "signature": "s"},
                ],
            }
        ]
    }
    apply(payloads)
    content = payloads["messages"][-1]["content"]
    assert content[0]["cache_control"] == MARK
    assert "cache_control" not in content[1]

    full = {
        "system": [{"type": "text", "text": "s", "cache_control": MARK}],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": str(i), "cache_control": MARK}
                    for i in range(3)
                ]
                + [{"type": "text", "text": "tail"}],
            }
        ],
    }
    apply(full)
    assert "cache_control" not in full["messages"][-1]["content"][-1]


def test_existing_tool_breakpoints_reserve_request_budget():
    # Three marked tools leave room for only one more marker.
    tools = [{"name": str(i), "cache_control": MARK} for i in range(3)]
    payload = {
        "tools": tools,
        "system": [{"type": "text", "text": "sys"}],
        "messages": [{"role": "user", "content": "hi"}],
    }
    apply(payload)
    blocks = [*payload["tools"], *payload["system"]]
    content = payload["messages"][0]["content"]
    if isinstance(content, list):
        blocks.extend(content)
    assert sum("cache_control" in block for block in blocks) <= 4
    assert payload["tools"] == tools
