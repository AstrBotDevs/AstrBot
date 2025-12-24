"""
功能展示脚本：演示 ContextManager 和 TodoList 注入的核心逻辑
运行方式：python showcase_features.py

复用核心组件逻辑，避免重复实现。
"""

import asyncio
import json
from typing import Any

# ============ 复用的核心组件（从 astrbot.core 复制） ============


class TokenCounter:
    """Token计数器：从 astrbot.core.context_manager.token_counter 复制"""

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self._estimate_tokens(part["text"])
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    tc_str = json.dumps(tc)
                    total += self._estimate_tokens(tc_str)
        return total

    def _estimate_tokens(self, text: str) -> int:
        chinese_count = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
        other_count = len(text) - chinese_count
        return int(chinese_count * 0.6 + other_count * 0.3)


class ContextCompressor:
    """上下文压缩器：从 astrbot.core.context_manager.context_compressor 复制"""

    async def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages


class DefaultCompressor(ContextCompressor):
    """默认压缩器"""

    async def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages


class ContextManager:
    """上下文管理器：从 astrbot.core.context_manager.context_manager 复制"""

    COMPRESSION_THRESHOLD = 0.82

    def __init__(self, model_context_limit: int, provider=None):
        self.model_context_limit = model_context_limit
        self.threshold = self.COMPRESSION_THRESHOLD
        self.token_counter = TokenCounter()
        if provider:
            self.compressor = LLMSummaryCompressor(provider)
        else:
            self.compressor = DefaultCompressor()

    async def process(
        self, messages: list[dict[str, Any]], max_messages_to_keep: int = 20
    ) -> list[dict[str, Any]]:
        if self.model_context_limit == -1:
            return messages

        needs_compression, initial_token_count = await self._initial_token_check(
            messages
        )
        messages = await self._run_compression(messages, needs_compression)
        messages = await self._run_final_processing(messages, max_messages_to_keep)
        return messages

    async def _initial_token_check(
        self, messages: list[dict[str, Any]]
    ) -> tuple[bool, int | None]:
        if not messages:
            return False, None
        total_tokens = self.token_counter.count_tokens(messages)
        usage_rate = total_tokens / self.model_context_limit
        needs_compression = usage_rate > self.threshold
        return needs_compression, total_tokens if needs_compression else None

    async def _run_compression(
        self, messages: list[dict[str, Any]], needs_compression: bool
    ) -> list[dict[str, Any]]:
        if not needs_compression:
            return messages
        messages = await self._compress_by_summarization(messages)
        tokens_after = self.token_counter.count_tokens(messages)
        if tokens_after / self.model_context_limit > self.threshold:
            messages = self._compress_by_halving(messages)
        return messages

    async def _compress_by_summarization(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return await self.compressor.compress(messages)

    def _compress_by_halving(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if len(messages) <= 2:
            return messages
        keep_count = len(messages) // 2
        return messages[:1] + messages[-keep_count:]

    async def _run_final_processing(
        self, messages: list[dict[str, Any]], max_messages_to_keep: int
    ) -> list[dict[str, Any]]:
        return messages


class LLMSummaryCompressor(ContextCompressor):
    """LLM摘要压缩器：从 astrbot.core.context_manager.context_compressor 复制"""

    def __init__(self, provider, keep_recent: int = 4):
        self.provider = provider
        self.keep_recent = keep_recent

    async def compress(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(messages) <= self.keep_recent + 1:
            return messages
        system_msg = (
            messages[0] if messages and messages[0].get("role") == "system" else None
        )
        start_idx = 1 if system_msg else 0
        messages_to_summarize = messages[start_idx : -self.keep_recent]
        recent_messages = messages[-self.keep_recent :]
        if not messages_to_summarize:
            return messages
        instruction_message = {"role": "user", "content": INSTRUCTION_TEXT}
        llm_payload = messages_to_summarize + [instruction_message]
        try:
            response = await self.provider.text_chat(messages=llm_payload)
            summary_content = response.completion_text
        except Exception:
            return messages
        result = []
        if system_msg:
            result.append(system_msg)
        result.append({"role": "system", "content": f"历史会话摘要：{summary_content}"})
        result.extend(recent_messages)
        return result


# ============ 模拟数据准备 ============

LONG_MESSAGE_HISTORY = [
    {
        "role": "system",
        "content": "你是一个有用的AI助手，专门帮助用户处理各种日常任务和查询。",
    },
    {
        "role": "user",
        "content": "帮我查询今天北京的天气情况，包括温度、湿度和空气质量指数",
    },
    {
        "role": "assistant",
        "content": "好的，我来帮你查询北京今天的详细天气信息。",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "北京", "details": true}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "北京今天晴天，温度25度，湿度60%，空气质量指数良好",
    },
    {
        "role": "assistant",
        "content": "北京今天是晴天，温度25度，湿度60%，空气质量指数良好，适合外出活动。",
    },
    {"role": "user", "content": "那明天的天气预报怎么样？会不会下雨？"},
    {
        "role": "assistant",
        "content": "让我查询明天北京的天气预报信息。",
        "tool_calls": [
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "北京", "date": "明天", "forecast": true}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_2",
        "content": "北京明天多云转阴，温度23度，下午可能有小雨，降水概率40%",
    },
    {
        "role": "assistant",
        "content": "北京明天是多云转阴，温度23度，下午可能有小雨，降水概率40%，建议带伞出门。",
    },
    {"role": "user", "content": "好的，那帮我设置一个明天的提醒吧"},
    {
        "role": "assistant",
        "content": "好的，请告诉我具体的提醒内容和时间，我来帮你设置。",
    },
    {"role": "user", "content": "明天早上8点提醒我开会，会议地点在公司三楼会议室"},
    {
        "role": "assistant",
        "content": "收到，我来帮你设置这个提醒。",
        "tool_calls": [
            {
                "id": "call_3",
                "type": "function",
                "function": {
                    "name": "set_reminder",
                    "arguments": '{"time": "明天8:00", "content": "开会 - 公司三楼会议室"}',
                },
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "call_3",
        "content": "提醒已设置成功：明天早上8:00 - 开会（公司三楼会议室）",
    },
    {
        "role": "assistant",
        "content": "好的，我已经帮你设置了提醒：明天早上8点提醒你开会，会议地点在公司三楼会议室。",
    },
]

EXAMPLE_TODOLIST = [
    {"id": 1, "description": "查询天气信息", "status": "completed"},
    {"id": 2, "description": "设置会议提醒", "status": "in_progress"},
    {"id": 3, "description": "总结今日任务", "status": "pending"},
]

INSTRUCTION_TEXT = """请基于我们完整的对话记录，生成一份全面的项目进展与内容总结报告。
1、报告需要首先明确阐述最初的任务目标、其包含的各个子目标以及当前已完成的子目标清单。
2、请系统性地梳理对话中涉及的所有核心话题，并总结每个话题的最终讨论结果，同时特别指出当前最新的核心议题及其进展。
3、请详细分析工具使用情况，包括统计总调用次数，并从工具返回的结果中提炼出最有价值的关键信息。整个总结应结构清晰、内容详实。"""


# ============ 辅助函数 ============


def print_separator(title: str):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_subsection(title: str):
    print(f"\n--- {title} ---\n")


def print_messages(messages: list[dict[str, Any]], indent: int = 0):
    prefix = "  " * indent
    for i, msg in enumerate(messages):
        print(f"{prefix}[{i}] role={msg.get('role')}")
        if msg.get("content"):
            content = str(msg["content"])
            if len(content) > 100:
                content = content[:100] + "..."
            print(f"{prefix}    content: {content}")
        if msg.get("tool_calls"):
            print(f"{prefix}    tool_calls: {len(msg['tool_calls'])} calls")


def format_todolist(
    todolist: list[dict], max_tool_calls: int = None, current_tool_calls: int = None
) -> str:
    """格式化 TodoList（复用于 tool_loop_agent_runner.py）"""
    lines = []
    if max_tool_calls is not None and current_tool_calls is not None:
        lines.append("--- 资源限制 ---")
        lines.append(f"剩余工具调用次数: {max_tool_calls - current_tool_calls}")
        lines.append(f"已调用次数: {current_tool_calls}")
        lines.append("请注意：请高效规划你的工作，尽量在工具调用次数用完之前完成任务。")
        lines.append("------------------")
        lines.append("")
    lines.append("--- 你当前的任务计划 ---")
    for task in todolist:
        status_icon = {"pending": "[ ]", "in_progress": "[-]", "completed": "[x]"}.get(
            task.get("status", "pending"), "[ ]"
        )
        lines.append(f"{status_icon} #{task['id']}: {task['description']}")
    lines.append("------------------------")
    return "\n".join(lines)


def inject_todolist_to_messages(
    messages: list[dict],
    todolist: list[dict],
    max_tool_calls: int = None,
    current_tool_calls: int = None,
) -> list[dict]:
    """注入 TodoList（复用于 tool_loop_agent_runner.py）"""
    formatted_todolist = format_todolist(todolist, max_tool_calls, current_tool_calls)
    messages = [msg.copy() for msg in messages]
    if messages and messages[-1].get("role") == "user":
        last_msg = messages[-1]
        messages[-1] = {
            "role": "user",
            "content": f"{formatted_todolist}\n\n{last_msg.get('content', '')}",
        }
    else:
        messages.append(
            {
                "role": "user",
                "content": f"任务列表已更新，这是你当前的计划：\n{formatted_todolist}",
            }
        )
    return messages


# ============ Mock Provider ============


class MockProvider:
    """模拟 LLM Provider，用于演示摘要压缩"""

    async def text_chat(self, messages: list[dict]) -> "MockResponse":
        return MockResponse(
            completion_text="""【项目进展总结报告】
1. 任务目标：用户需要查询天气信息并设置提醒
   - 已完成子目标：查询北京今日天气（晴天，25度，湿度60%，空气质量良好）
   - 已完成子目标：查询北京明日天气预报（多云转阴，23度，下午可能小雨，降水概率40%）
   - 已完成子目标：设置会议提醒（明天早上8点，开会-公司三楼会议室）

2. 核心话题梳理：
   - 天气查询：提供了详细的今日和明日天气信息
   - 提醒设置：成功设置了会议提醒
   - 当前最新议题：提醒设置已完成，用户可放心

3. 工具使用情况：
   - 总调用次数：3次
   - get_weather：2次
   - set_reminder：1次"""
        )


class MockResponse:
    def __init__(self, completion_text: str):
        self.completion_text = completion_text


# ============ 演示包装类 ============


class DemoContextManager:
    """演示用 ContextManager 包装类：调用真实组件，添加打印输出"""

    def __init__(self, model_context_limit: int, provider=None):
        self.real_manager = ContextManager(model_context_limit, provider)
        self.token_counter = TokenCounter()

    async def process(self, messages: list[dict]) -> list[dict]:
        total_tokens = self.token_counter.count_tokens(messages)
        usage_rate = total_tokens / self.real_manager.model_context_limit

        print(f"  初始Token数: {total_tokens}")
        print(f"  上下文限制: {self.real_manager.model_context_limit}")
        print(f"  使用率: {usage_rate:.2%}")
        print(f"  触发阈值: {self.real_manager.threshold:.0%}")

        if usage_rate > self.real_manager.threshold:
            print("  ✓ 超过阈值，触发压缩/截断")

            if (
                self.real_manager.compressor.__class__.__name__
                == "LLMSummaryCompressor"
            ):
                print("  → Agent模式：执行摘要压缩")
                messages_to_summarize = (
                    messages[1:]
                    if messages and messages[0].get("role") == "system"
                    else messages
                )
                print("\n    【摘要压缩详情】")
                print("    被摘要的旧消息历史:")
                print_messages(messages_to_summarize, indent=3)

            result = await self.real_manager.process(messages)

            tokens_after = self.token_counter.count_tokens(result)
            if (
                tokens_after / self.real_manager.model_context_limit
                > self.real_manager.threshold
            ):
                print("  → 摘要后仍超过阈值，执行对半砍")
        else:
            print("  ✗ 未超过阈值，无需压缩")
            result = messages

        return result


# ============ 主展示函数 ============


async def demo_context_manager():
    """演示 ContextManager 的工作流程"""
    print_separator("DEMO 1: ContextManager Workflow")

    print_subsection("Agent模式（触发摘要压缩）")

    print("【输入】完整消息历史:")
    print_messages(LONG_MESSAGE_HISTORY, indent=1)

    print("\n【处理】执行 ContextManager.process (AGENT 模式):")

    mock_provider = MockProvider()
    demo_cm = DemoContextManager(model_context_limit=150, provider=mock_provider)
    result_agent = await demo_cm.process(LONG_MESSAGE_HISTORY)

    print("\n【输出】摘要压缩后的消息历史:")
    print_messages(result_agent, indent=1)
    print(f"\n  消息数量: {len(LONG_MESSAGE_HISTORY)} → {len(result_agent)}")


async def demo_todolist_injection():
    """演示 TodoList 自动注入"""
    print_separator("DEMO 2: TodoList Auto-Injection")

    print_subsection("场景 A: 注入到最后的用户消息")

    messages_with_user = [
        {"role": "user", "content": "帮我查询天气"},
        {"role": "assistant", "content": "好的，正在查询..."},
        {"role": "user", "content": "明天早上8点提醒我开会"},
    ]

    print("【输入】消息历史（最后一条是 user）:")
    print_messages(messages_with_user, indent=1)

    print("\n【输入】TodoList:")
    for task in EXAMPLE_TODOLIST:
        status_icon = {"pending": "[ ]", "in_progress": "[-]", "completed": "[x]"}.get(
            task["status"], "[ ]"
        )
        print(f"  {status_icon} #{task['id']}: {task['description']}")

    print("\n【处理】执行 TodoList 注入逻辑...")
    max_tool_calls = 10
    current_tool_calls = 3
    result_a = inject_todolist_to_messages(
        messages_with_user, EXAMPLE_TODOLIST, max_tool_calls, current_tool_calls
    )

    print("\n【输出】注入后的消息历史:")
    print_messages(result_a, indent=1)

    print("\n【详细】最后一条消息的完整内容:")
    print(f"  {result_a[-1]['content']}")

    print_subsection("场景 B: 在Tool Call后创建新消息注入")

    messages_with_tool = [
        {"role": "user", "content": "帮我查询天气"},
        {
            "role": "assistant",
            "content": "正在查询...",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "北京今天晴天"},
    ]

    print("【输入】消息历史（最后一条是 tool）:")
    print_messages(messages_with_tool, indent=1)

    print("\n【输入】TodoList:")
    for task in EXAMPLE_TODOLIST:
        status_icon = {"pending": "[ ]", "in_progress": "[-]", "completed": "[x]"}.get(
            task["status"], "[ ]"
        )
        print(f"  {status_icon} #{task['id']}: {task['description']}")

    print("\n【处理】执行 TodoList 注入逻辑...")
    result_b = inject_todolist_to_messages(
        messages_with_tool, EXAMPLE_TODOLIST, max_tool_calls, current_tool_calls
    )

    print("\n【输出】注入后的消息历史:")
    print_messages(result_b, indent=1)

    print("\n【详细】新增的用户消息完整内容:")
    print(f"  {result_b[-1]['content']}")


async def demo_max_step_smart_injection():
    """演示工具耗尽时的智能注入"""
    print_separator("DEMO 3: Max Step Smart Injection")

    print_subsection("场景 A: 工具耗尽时，最后消息是user（合并注入）")

    messages_with_user = [
        {"role": "user", "content": "帮我分析这个项目的代码结构"},
        {
            "role": "assistant",
            "content": "好的，我来帮你分析代码结构。",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "main.py"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "读取到main.py文件内容...",
        },
        {
            "role": "assistant",
            "content": "我已经读取了main.py文件，现在让我继续分析其他文件。",
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "list_dir", "arguments": '{"path": "."}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_2",
            "content": "目录结构：src/, tests/, docs/",
        },
        {"role": "user", "content": "好的，请继续分析src目录下的文件"},
    ]

    print("【输入】消息历史（最后一条是user）:")
    print_messages(messages_with_user, indent=1)

    print("\n【处理】模拟工具耗尽，执行智能注入逻辑...")
    max_step_message = "工具调用次数已达到上限，请停止使用工具，并根据已经收集到的信息，对你的任务和发现进行总结，然后直接回复用户。"

    result_a = inject_todolist_to_messages(messages_with_user, EXAMPLE_TODOLIST, 10, 7)
    if result_a and result_a[-1].get("role") == "user":
        result_a[-1]["content"] = f"{max_step_message}\n\n{result_a[-1]['content']}"

    print("\n【输出】智能注入后的消息历史:")
    print_messages(result_a, indent=1)

    print("\n【详细】最后一条消息的完整内容:")
    print(f"  {result_a[-1]['content']}")

    print_subsection("场景 B: 工具耗尽时，最后消息是tool（新增消息注入）")

    messages_with_tool = [
        {"role": "user", "content": "帮我分析这个项目的代码结构"},
        {
            "role": "assistant",
            "content": "好的，我来帮你分析代码结构。",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "main.py"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "读取到main.py文件内容...",
        },
        {
            "role": "assistant",
            "content": "我已经读取了main.py文件，现在让我继续分析其他文件。",
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "list_dir", "arguments": '{"path": "."}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_2",
            "content": "目录结构：src/, tests/, docs/",
        },
        {
            "role": "assistant",
            "content": "继续分析src目录...",
            "tool_calls": [
                {
                    "id": "call_3",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "src/main.py"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_3",
            "content": "读取到src/main.py文件内容...",
        },
    ]

    print("【输入】消息历史（最后一条是tool）:")
    print_messages(messages_with_tool, indent=1)

    print("\n【处理】模拟工具耗尽，执行智能注入逻辑...")
    result_b = inject_todolist_to_messages(messages_with_tool, EXAMPLE_TODOLIST, 10, 7)
    result_b.append({"role": "user", "content": max_step_message})

    print("\n【输出】智能注入后的消息历史:")
    print_messages(result_b, indent=1)

    print("\n【详细】新增的用户消息完整内容:")
    print(f"  {result_b[-1]['content']}")


async def main():
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "AstrBot 功能展示脚本" + " " * 38 + "║")
    print(
        "║"
        + " " * 10
        + "ContextManager & TodoList & MaxStep Injection"
        + " " * 23
        + "║"
    )
    print("╚" + "═" * 78 + "╝")

    await demo_context_manager()
    await demo_todolist_injection()
    await demo_max_step_smart_injection()

    print("\n" + "=" * 80)
    print("  展示完成！")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
