"""伪造工具调用（fake tool call）共享测试数据。

各 provider 测试（OpenAI / Anthropic / Gemini 格式）共用同一组伪造
assistant(tool_calls) + tool 消息对，避免场景漂移。
"""

from astrbot.core.agent.message import FROM_REAL_TOOL_CALL_KEY

FAKE_TOOL_CALL_CONTEXTS = [
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "fake_recall_abc",
                "type": "function",
                "function": {
                    "name": "recall_long_term_memory",
                    "arguments": '{"query": "我的名字是？", "k": 5}',
                },
            }
        ],
    },
    {"role": "tool", "tool_call_id": "fake_recall_abc", "content": "memory json"},
]


def make_fake_pair(
    tool_call_id: str = "fake_call_01",
    name: str = "recall_long_term_memory",
    arguments: str = "{}",
    content: str = "mem result",
    marked: bool = False,
) -> list[dict]:
    """构造一对伪造（或带真实标记的）assistant(tool_calls) + tool 消息。

    Args:
        tool_call_id: assistant 与 tool 共享的调用 ID。
        name: 工具名。
        arguments: 工具参数 JSON 字符串。
        content: 工具返回内容。
        marked: True 时给消息对打上 ``_from_real_tool_call`` 标记，
            模拟真实工具执行产生的消息。
    """
    pair = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        },
        {"role": "tool", "tool_call_id": tool_call_id, "content": content},
    ]
    if marked:
        for message in pair:
            message[FROM_REAL_TOOL_CALL_KEY] = True
    return pair
