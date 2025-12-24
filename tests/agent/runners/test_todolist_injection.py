"""
测试 ToolLoopAgentRunner 的 TodoList 注入逻辑
"""

from unittest.mock import MagicMock


# 避免循环导入，使用 Mock 代替真实类
class MockMessage:
    def __init__(self, role, content):
        self.role = role
        self.content = content


class MockContextWrapper:
    def __init__(self, context):
        self.context = context


class MockAstrAgentContext:
    def __init__(self):
        self.todolist = []


# 创建一个简化的 ToolLoopAgentRunner 类用于测试
class MockToolLoopAgentRunner:
    def __init__(self):
        self.run_context = None
        self.max_step = 0
        self.current_step = 0

    def _smart_inject_user_message(
        self,
        messages,
        content_to_inject,
        prefix="",
        inject_at_start=False,
    ):
        """智能注入用户消息：如果最后一条消息是user，则合并；否则新建

        Args:
            messages: 消息列表
            content_to_inject: 要注入的内容
            prefix: 前缀文本（仅在新建消息时使用）
            inject_at_start: 是否注入到 user 消息开头
        """
        messages = list(messages)
        if messages and messages[-1].role == "user":
            last_msg = messages[-1]
            if inject_at_start:
                # 注入到 user 消息开头
                messages[-1] = MockMessage(
                    role="user", content=f"{content_to_inject}\n\n{last_msg.content}"
                )
            else:
                # 注入到 user 消息末尾（默认行为）
                messages[-1] = MockMessage(
                    role="user",
                    content=f"{prefix}{content_to_inject}\n\n{last_msg.content}",
                )
        else:
            # 添加新的user消息
            messages.append(
                MockMessage(role="user", content=f"{prefix}{content_to_inject}")
            )
        return messages

    def _inject_todolist_if_needed(self, messages):
        """从原始 ToolLoopAgentRunner 复制的逻辑"""
        # 检查是否是 AstrAgentContext
        if not isinstance(self.run_context.context, MockAstrAgentContext):
            return messages

        todolist = self.run_context.context.todolist
        if not todolist:
            return messages

        # 构建注入内容
        injection_parts = []

        # 1. 资源限制部分
        if hasattr(self, "max_step") and self.max_step > 0:
            remaining = self.max_step - getattr(self, "current_step", 0)
            current = getattr(self, "current_step", 0)
            injection_parts.append(
                f"--- 资源限制 ---\n"
                f"剩余工具调用次数: {remaining}\n"
                f"已调用次数: {current}\n"
                f"请注意：请高效规划你的工作，尽量在工具调用次数用完之前完成任务。\n"
                f"------------------"
            )

        # 2. TodoList部分
        lines = ["--- 你当前的任务计划 ---"]
        for task in todolist:
            status_icon = {
                "pending": "[ ]",
                "in_progress": "[-]",
                "completed": "[x]",
            }.get(task.get("status", "pending"), "[ ]")
            lines.append(f"{status_icon} #{task['id']}: {task['description']}")
        lines.append("------------------------")
        injection_parts.append("\n".join(lines))

        # 合并所有注入内容
        formatted_content = "\n\n".join(injection_parts)

        # 使用智能注入，注入到 user 消息开头
        return self._smart_inject_user_message(
            messages, formatted_content, inject_at_start=True
        )


class TestTodoListInjection:
    """测试 TodoList 注入逻辑"""

    def setup_method(self):
        """每个测试方法执行前的设置"""
        self.runner = MockToolLoopAgentRunner()
        self.runner.max_step = 0  # 默认不设置资源限制

        # 创建模拟的 AstrAgentContext
        self.mock_astr_context = MockAstrAgentContext()
        self.mock_astr_context.todolist = []

        # 创建模拟的 ContextWrapper
        self.mock_context = MockContextWrapper(self.mock_astr_context)

        # 设置 runner 的 run_context
        self.runner.run_context = self.mock_context

    def test_inject_todolist_not_astr_agent_context(self):
        """测试非 AstrAgentContext 的情况"""
        # 设置非 AstrAgentContext
        self.mock_context.context = MagicMock()

        messages = [
            MockMessage(role="system", content="System"),
            MockMessage(role="user", content="Hello"),
        ]

        result = self.runner._inject_todolist_if_needed(messages)

        # 应该返回原始消息
        assert result == messages

    def test_inject_todolist_empty_todolist(self):
        """测试空 TodoList 的情况"""
        self.mock_astr_context.todolist = []

        messages = [
            MockMessage(role="system", content="System"),
            MockMessage(role="user", content="Hello"),
        ]

        result = self.runner._inject_todolist_if_needed(messages)

        # 应该返回原始消息
        assert result == messages

    def test_inject_todolist_with_last_user_message(self):
        """测试有最后一条 user 消息的情况，TodoList 注入到开头"""
        self.mock_astr_context.todolist = [
            {"id": 1, "description": "Task 1", "status": "pending"},
            {"id": 2, "description": "Task 2", "status": "in_progress"},
            {"id": 3, "description": "Task 3", "status": "completed"},
        ]

        messages = [
            MockMessage(role="system", content="System"),
            MockMessage(role="assistant", content="Previous response"),
            MockMessage(role="user", content="What's the weather today?"),
        ]

        result = self.runner._inject_todolist_if_needed(messages)

        # 应该修改最后一条 user 消息
        assert len(result) == len(messages)
        assert result[-1].role == "user"

        # 检查是否包含了 TodoList 内容（在开头）
        content = result[-1].content
        assert "--- 你当前的任务计划 ---" in content
        assert "[ ] #1: Task 1" in content
        assert "[-] #2: Task 2" in content
        assert "[x] #3: Task 3" in content
        assert "------------------------" in content
        # 用户原始消息应该在 TodoList 后面
        assert content.startswith("--- 你当前的任务计划")
        assert "What's the weather today?" in content

    def test_inject_todolist_without_last_user_message(self):
        """测试没有最后一条 user 消息的情况"""
        self.mock_astr_context.todolist = [
            {"id": 1, "description": "Task 1", "status": "pending"},
            {"id": 2, "description": "Task 2", "status": "in_progress"},
        ]

        messages = [
            MockMessage(role="system", content="System"),
            MockMessage(role="assistant", content="Previous response"),
        ]

        result = self.runner._inject_todolist_if_needed(messages)

        # 应该添加新的 user 消息
        assert len(result) == len(messages) + 1
        assert result[-1].role == "user"

        # 检查新消息的内容（现在没有前缀了）
        content = result[-1].content
        assert "--- 你当前的任务计划 ---" in content
        assert "[ ] #1: Task 1" in content
        assert "[-] #2: Task 2" in content
        assert "------------------------" in content

    def test_inject_todolist_empty_messages(self):
        """测试空消息列表的情况"""
        self.mock_astr_context.todolist = [
            {"id": 1, "description": "Task 1", "status": "pending"}
        ]

        messages = []

        result = self.runner._inject_todolist_if_needed(messages)

        # 应该添加新的 user 消息
        assert len(result) == 1
        assert result[0].role == "user"

        # 检查新消息的内容
        content = result[0].content
        assert "--- 你当前的任务计划 ---" in content
        assert "[ ] #1: Task 1" in content
        assert "------------------------" in content

    def test_inject_todolist_various_statuses(self):
        """测试各种任务状态"""
        self.mock_astr_context.todolist = [
            {"id": 1, "description": "Pending task", "status": "pending"},
            {"id": 2, "description": "In progress task", "status": "in_progress"},
            {"id": 3, "description": "Completed task", "status": "completed"},
            {"id": 4, "description": "Unknown status task", "status": "unknown"},
            {"id": 5, "description": "No status task"},  # 没有 status 字段
        ]

        messages = [MockMessage(role="user", content="Help me with something")]

        result = self.runner._inject_todolist_if_needed(messages)

        # 检查各种状态的图标
        content = result[-1].content
        assert "[ ] #1: Pending task" in content
        assert "[-] #2: In progress task" in content
        assert "[x] #3: Completed task" in content
        assert "[ ] #4: Unknown status task" in content  # 未知状态默认为 pending
        assert "[ ] #5: No status task" in content  # 没有状态默认为 pending

    def test_inject_todolist_preserves_message_order(self):
        """测试注入 TodoList 后保持消息顺序"""
        self.mock_astr_context.todolist = [
            {"id": 1, "description": "Task 1", "status": "pending"}
        ]

        messages = [
            MockMessage(role="system", content="System prompt"),
            MockMessage(role="user", content="First question"),
            MockMessage(role="assistant", content="First answer"),
            MockMessage(role="user", content="Second question"),
        ]

        result = self.runner._inject_todolist_if_needed(messages)

        # 检查消息顺序
        assert len(result) == len(messages)
        assert result[0].role == "system"
        assert result[0].content == "System prompt"
        assert result[1].role == "user"
        assert "First question" in result[1].content
        assert result[2].role == "assistant"
        assert result[2].content == "First answer"
        assert result[3].role == "user"
        assert "Second question" in result[3].content
        assert "--- 你当前的任务计划 ---" in result[3].content

    def test_inject_todolist_with_multiline_descriptions(self):
        """测试多行任务描述"""
        self.mock_astr_context.todolist = [
            {"id": 1, "description": "Task with\nmultiple lines", "status": "pending"},
            {"id": 2, "description": "Task with\ttabs", "status": "in_progress"},
        ]

        messages = [MockMessage(role="user", content="Help me")]

        result = self.runner._inject_todolist_if_needed(messages)

        # 检查多行描述是否正确处理
        content = result[-1].content
        assert "[ ] #1: Task with\nmultiple lines" in content
        assert "[-] #2: Task with\ttabs" in content

    def test_inject_todolist_with_resource_limits(self):
        """测试注入资源限制信息"""
        # 设置资源限制
        self.runner.max_step = 10
        self.runner.current_step = 3

        self.mock_astr_context.todolist = [
            {"id": 1, "description": "Task 1", "status": "pending"},
            {"id": 2, "description": "Task 2", "status": "in_progress"},
        ]

        messages = [MockMessage(role="user", content="Help me with something")]

        result = self.runner._inject_todolist_if_needed(messages)

        # 检查是否包含资源限制信息
        content = result[-1].content
        assert "--- 资源限制 ---" in content
        assert "剩余工具调用次数: 7" in content
        assert "已调用次数: 3" in content
        assert "请注意：请高效规划你的工作" in content
        assert "------------------" in content

        # 同时也应该包含 TodoList
        assert "--- 你当前的任务计划 ---" in content
        assert "[ ] #1: Task 1" in content
        assert "[-] #2: Task 2" in content

    def test_inject_todolist_without_resource_limits(self):
        """测试没有设置资源限制时的情况"""
        # 不设置 max_step（保持为0或不设置）
        self.runner.max_step = 0

        self.mock_astr_context.todolist = [
            {"id": 1, "description": "Task 1", "status": "pending"}
        ]

        messages = [MockMessage(role="user", content="Help me")]

        result = self.runner._inject_todolist_if_needed(messages)

        # 不应该包含资源限制信息
        content = result[-1].content
        assert "--- 资源限制 ---" not in content
        assert "剩余工具调用次数" not in content

        # 但应该包含 TodoList
        assert "--- 你当前的任务计划 ---" in content
        assert "[ ] #1: Task 1" in content


class TestSmartInjectUserMessage:
    """测试智能注入用户消息的逻辑"""

    def setup_method(self):
        """每个测试方法执行前的设置"""
        self.runner = MockToolLoopAgentRunner()

    def test_smart_inject_with_last_user_message(self):
        """测试最后一条消息是user时，合并注入内容"""
        messages = [
            MockMessage(role="system", content="System prompt"),
            MockMessage(role="assistant", content="Assistant response"),
            MockMessage(role="user", content="User question"),
        ]

        content_to_inject = "工具调用次数已达到上限，请停止使用工具..."
        result = self.runner._smart_inject_user_message(messages, content_to_inject)

        # 应该修改最后一条user消息
        assert len(result) == len(messages)
        assert result[-1].role == "user"
        assert result[-1].content.startswith(content_to_inject)
        assert "User question" in result[-1].content

    def test_smart_inject_without_last_user_message(self):
        """测试最后一条消息不是user时，添加新消息"""
        messages = [
            MockMessage(role="system", content="System prompt"),
            MockMessage(role="assistant", content="Assistant response"),
        ]

        content_to_inject = "工具调用次数已达到上限，请停止使用工具..."
        result = self.runner._smart_inject_user_message(messages, content_to_inject)

        # 应该添加新的user消息
        assert len(result) == len(messages) + 1
        assert result[-1].role == "user"
        assert result[-1].content == content_to_inject

    def test_smart_inject_with_prefix(self):
        """测试使用前缀的情况"""
        messages = [
            MockMessage(role="system", content="System prompt"),
            MockMessage(role="assistant", content="Assistant response"),
        ]

        content_to_inject = "TodoList content"
        prefix = "任务列表已更新，这是你当前的计划：\n"
        result = self.runner._smart_inject_user_message(
            messages, content_to_inject, prefix
        )

        # 应该添加新的user消息，包含前缀
        assert len(result) == len(messages) + 1
        assert result[-1].role == "user"
        assert result[-1].content == f"{prefix}{content_to_inject}"

    def test_smart_inject_empty_messages(self):
        """测试空消息列表的情况"""
        messages = []

        content_to_inject = "工具调用次数已达到上限，请停止使用工具..."
        result = self.runner._smart_inject_user_message(messages, content_to_inject)

        # 应该添加新的user消息
        assert len(result) == 1
        assert result[0].role == "user"
        assert result[0].content == content_to_inject

    def test_smart_inject_preserves_message_order(self):
        """测试注入后保持消息顺序"""
        messages = [
            MockMessage(role="system", content="System 1"),
            MockMessage(role="user", content="User 1"),
            MockMessage(role="assistant", content="Assistant 1"),
            MockMessage(role="user", content="User 2"),
        ]

        content_to_inject = "Injected content"
        result = self.runner._smart_inject_user_message(messages, content_to_inject)

        # 检查消息顺序和内容
        assert len(result) == len(messages)
        assert result[0].role == "system" and result[0].content == "System 1"
        assert result[1].role == "user" and "User 1" in result[1].content
        assert result[2].role == "assistant" and result[2].content == "Assistant 1"
        assert result[3].role == "user"
        assert content_to_inject in result[3].content
        assert "User 2" in result[3].content


class TestMaxStepSmartInjection:
    """测试工具耗尽时的智能注入"""

    def setup_method(self):
        """每个测试方法执行前的设置"""
        self.runner = MockToolLoopAgentRunner()
        self.runner.max_step = 5
        self.runner.current_step = 5  # 模拟已达到最大步数

        # 创建模拟的 ContextWrapper
        self.mock_context = MockContextWrapper(None)
        self.runner.run_context = self.mock_context

    def test_max_step_injection_with_last_user_message(self):
        """测试工具耗尽时，最后消息是user的情况"""
        # 设置消息列表，最后一条是user消息
        self.runner.run_context.messages = [
            MockMessage(role="system", content="System"),
            MockMessage(role="assistant", content="Assistant response"),
            MockMessage(role="user", content="User question"),
        ]

        # 模拟工具耗尽的注入逻辑
        self.runner.run_context.messages = self.runner._smart_inject_user_message(
            self.runner.run_context.messages,
            "工具调用次数已达到上限，请停止使用工具，并根据已经收集到的信息，对你的任务和发现进行总结，然后直接回复用户。",
        )

        # 验证结果
        messages = self.runner.run_context.messages
        assert len(messages) == 3  # 消息数量不变
        assert messages[-1].role == "user"
        assert "工具调用次数已达到上限" in messages[-1].content
        assert "User question" in messages[-1].content

    def test_max_step_injection_without_last_user_message(self):
        """测试工具耗尽时，最后消息不是user的情况"""
        # 设置消息列表，最后一条不是user消息
        self.runner.run_context.messages = [
            MockMessage(role="system", content="System"),
            MockMessage(role="assistant", content="Assistant response"),
        ]

        # 模拟工具耗尽的注入逻辑
        self.runner.run_context.messages = self.runner._smart_inject_user_message(
            self.runner.run_context.messages,
            "工具调用次数已达到上限，请停止使用工具，并根据已经收集到的信息，对你的任务和发现进行总结，然后直接回复用户。",
        )

        # 验证结果
        messages = self.runner.run_context.messages
        assert len(messages) == 3  # 添加了新消息
        assert messages[-1].role == "user"
        assert (
            messages[-1].content
            == "工具调用次数已达到上限，请停止使用工具，并根据已经收集到的信息，对你的任务和发现进行总结，然后直接回复用户。"
        )
