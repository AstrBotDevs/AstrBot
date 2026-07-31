"""伪造工具调用（fake tool call）共享测试数据。

各 provider 测试（OpenAI / Anthropic / Gemini 格式）共用同一组伪造
assistant(tool_calls) + tool 消息对，避免场景漂移。
"""

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
