"""
功能展示脚本：演示 ContextManager 和 TodoList 注入的核心逻辑
运行方式：python showcase_features.py
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock

# ============ 模拟数据准备 ============

# 长消息历史（10+条消息，包含 user, assistant, tool calls）
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

# 示例 TodoList
EXAMPLE_TODOLIST = [
    {"id": 1, "description": "查询天气信息", "status": "completed"},
    {"id": 2, "description": "设置会议提醒", "status": "in_progress"},
    {"id": 3, "description": "总结今日任务", "status": "pending"},
]


# ============ 辅助函数 ============


def print_separator(title: str):
    """打印分隔线和标题"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_subsection(title: str):
    """打印子标题"""
    print(f"\n--- {title} ---\n")


def print_messages(messages: list[dict[str, Any]], indent: int = 0):
    """格式化打印消息列表"""
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
        if msg.get("tool_call_id"):
            print(f"{prefix}    tool_call_id: {msg['tool_call_id']}")


def format_todolist(
    todolist: list[dict], max_tool_calls: int = None, current_tool_calls: int = None
) -> str:
    """格式化 TodoList（模拟注入逻辑）"""
    lines = []
    if max_tool_calls is not None and current_tool_calls is not None:
        lines.append("--- 资源限制 ---")
        lines.append(f"剩余工具调用次数: {max_tool_calls - current_tool_calls}")
        lines.append(f"已调用次数: {current_tool_calls}")
        lines.append("...")
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
    """模拟 TodoList 注入逻辑"""
    formatted_todolist = format_todolist(todolist, max_tool_calls, current_tool_calls)
    messages = [msg.copy() for msg in messages]

    if messages and messages[-1].get("role") == "user":
        # 场景A：前置到最后一条user消息
        last_msg = messages[-1]
        messages[-1] = {
            "role": "user",
            "content": f"{formatted_todolist}\n\n{last_msg.get('content', '')}",
        }
    else:
        # 场景B：添加新的user消息
        messages.append(
            {
                "role": "user",
                "content": f"任务列表已更新，这是你当前的计划：\n{formatted_todolist}",
            }
        )

    return messages


# ============ ContextManager 模拟实现 ============


class MockContextManager:
    """模拟 ContextManager 的核心逻辑"""

    def __init__(
        self, model_context_limit: int, is_agent_mode: bool = False, provider=None
    ):
        self.model_context_limit = model_context_limit
        self.is_agent_mode = is_agent_mode
        self.threshold = 0.82
        self.provider = provider

    def count_tokens(self, messages: list[dict]) -> int:
        """粗算Token数（中文0.6，其他0.3）"""
        total = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            chinese_chars = sum(1 for c in content if "\u4e00" <= c <= "\u9fff")
            other_chars = len(content) - chinese_chars
            total += int(chinese_chars * 0.6 + other_chars * 0.3)
        return total

    async def process_context(self, messages: list[dict]) -> list[dict]:
        """主处理方法"""
        total_tokens = self.count_tokens(messages)
        usage_rate = total_tokens / self.model_context_limit

        print(f"  初始Token数: {total_tokens}")
        print(f"  上下文限制: {self.model_context_limit}")
        print(f"  使用率: {usage_rate:.2%}")
        print(f"  触发阈值: {self.threshold:.0%}")

        if usage_rate > self.threshold:
            print("  ✓ 超过阈值，触发压缩/截断")

            if self.is_agent_mode:
                print("  → Agent模式：执行摘要压缩")
                messages = await self._compress_by_summarization(messages)

                # 第二次检查
                tokens_after = self.count_tokens(messages)
                if tokens_after / self.model_context_limit > self.threshold:
                    print("  → 摘要后仍超过阈值，执行对半砍")
                    messages = self._compress_by_halving(messages)
            else:
                print("  → 普通模式：执行对半砍")
                messages = self._compress_by_halving(messages)
        else:
            print("  ✗ 未超过阈值，无需压缩")

        return messages

    async def _compress_by_summarization(self, messages: list[dict]) -> list[dict]:
        """摘要压缩（模拟更智能的实现）"""
        if self.provider:
            # 确定要摘要的消息（除了system消息）
            messages_to_summarize = (
                messages[1:]
                if messages and messages[0].get("role") == "system"
                else messages
            )

            print("\n    【摘要压缩详情】")
            print("    被摘要的旧消息历史:")
            print_messages(messages_to_summarize, indent=3)

            # 读取指令文本
            instruction_text = """请基于我们完整的对话记录，生成一份全面的项目进展与内容总结报告。
1、报告需要首先明确阐述最初的任务目标、其包含的各个子目标以及当前已完成的子目标清单。
2、请系统性地梳理对话中涉及的所有核心话题，并总结每个话题的最终讨论结果，同时特别指出当前最新的核心议题及其进展。
3、请详细分析工具使用情况，包括统计总调用次数，并从工具返回的结果中提炼出最有价值的关键信息。整个总结应结构清晰、内容详实。"""

            print(f"\n    来自 summary_prompt.md 的指令文本:\n    {instruction_text}")

            # 创建指令消息
            instruction_message = {"role": "user", "content": instruction_text}

            # 发送给模拟Provider的载荷
            payload = messages_to_summarize + [instruction_message]
            print(
                "\n    发送给模拟Provider的载荷 (messages_to_summarize + [instruction_message]):"
            )
            print_messages(payload, indent=3)

            # 模拟Provider返回的结构化摘要
            structured_summary = """【项目进展总结报告】
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
   - get_weather：2次（查询今日和明日天气）
   - set_reminder：1次（设置会议提醒）
   - 关键信息：天气数据准确，提醒设置成功"""

            print(f"\n    模拟Provider返回的结构化摘要:\n    {structured_summary}")

            # 最终被压缩替换后的消息列表
            compressed_messages = [
                {"role": "system", "content": messages[0].get("content", "")},
                {"role": "user", "content": structured_summary},
                *messages[-2:],  # 保留最后2条
            ]

            print("\n    最终被压缩替换后的消息列表:")
            print_messages(compressed_messages, indent=3)

            return compressed_messages
        return messages

    def _compress_by_halving(self, messages: list[dict]) -> list[dict]:
        """对半砍：删除中间50%"""
        if len(messages) <= 2:
            return messages

        keep_count = len(messages) // 2
        return messages[:1] + messages[-keep_count:]


# ============ 主展示函数 ============


async def demo_context_manager():
    """演示 ContextManager 的工作流程"""
    print_separator("DEMO 1: ContextManager Workflow")

    # Agent模式（摘要压缩）
    print_subsection("Agent模式（触发摘要压缩）")

    print("【输入】完整消息历史:")
    print_messages(LONG_MESSAGE_HISTORY, indent=1)

    print("\n【处理】执行 ContextManager.process_context (AGENT 模式):")
    mock_provider = MagicMock()
    cm_agent = MockContextManager(
        model_context_limit=150, is_agent_mode=True, provider=mock_provider
    )
    result_agent = await cm_agent.process_context(LONG_MESSAGE_HISTORY)

    print("\n【输出】摘要压缩后的消息历史:")
    print_messages(result_agent, indent=1)
    print(f"\n  消息数量: {len(LONG_MESSAGE_HISTORY)} → {len(result_agent)}")


async def demo_todolist_injection():
    """演示 TodoList 自动注入"""
    print_separator("DEMO 2: TodoList Auto-Injection")

    # 场景A：注入到现有用户消息
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
    # 模拟资源限制：最大工具调用次数10，当前已调用3次
    max_tool_calls = 10
    current_tool_calls = 3
    result_a = inject_todolist_to_messages(
        messages_with_user, EXAMPLE_TODOLIST, max_tool_calls, current_tool_calls
    )

    print("\n【输出】注入后的消息历史:")
    print_messages(result_a, indent=1)

    print("\n【详细】最后一条消息的完整内容:")
    print(f"  {result_a[-1]['content']}")

    # 场景B：创建新用户消息进行注入
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
    # 模拟资源限制：最大工具调用次数10，当前已调用3次
    max_tool_calls = 10
    current_tool_calls = 3
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

    # 场景A：最后消息是user，合并注入
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

    # 模拟智能注入：最后消息是user，合并
    result_a = messages_with_user.copy()
    if result_a and result_a[-1].get("role") == "user":
        last_msg = result_a[-1]
        result_a[-1] = {
            "role": "user",
            "content": f"{max_step_message}\n\n{last_msg.get('content', '')}",
        }

    print("\n【输出】智能注入后的消息历史:")
    print_messages(result_a, indent=1)

    print("\n【详细】最后一条消息的完整内容:")
    print(f"  {result_a[-1]['content']}")

    # 场景B：最后消息不是user，新增消息
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
    # 模拟智能注入：最后消息不是user，新增
    result_b = messages_with_tool.copy()
    result_b.append({"role": "user", "content": max_step_message})

    print("\n【输出】智能注入后的消息历史:")
    print_messages(result_b, indent=1)

    print("\n【详细】新增的用户消息完整内容:")
    print(f"  {result_b[-1]['content']}")


async def main():
    """主函数"""
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
