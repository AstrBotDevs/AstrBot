"""测试 TodoList 工具本身的行为"""

import pytest


class MockContextWrapper:
    def __init__(self, context):
        self.context = context


class MockAstrAgentContext:
    def __init__(self):
        self.todolist = []


# 简化版工具实现（避免循环导入）
class TodoListAddTool:
    name: str = "todolist_add"

    async def call(self, context: MockContextWrapper, **kwargs):
        tasks = kwargs.get("tasks", [])
        if not tasks:
            return "error: No tasks provided."

        todolist = context.context.todolist
        next_id = max([t["id"] for t in todolist], default=0) + 1

        added = []
        for desc in tasks:
            task = {"id": next_id, "description": desc, "status": "pending"}
            todolist.append(task)
            added.append(f"#{next_id}: {desc}")
            next_id += 1

        return f"已添加 {len(added)} 个任务:\n" + "\n".join(added)


class TodoListUpdateTool:
    name: str = "todolist_update"

    async def call(self, context: MockContextWrapper, **kwargs):
        # 检查必填参数
        if "status" not in kwargs or kwargs.get("status") is None:
            return "error: 参数缺失，status 是必填参数"

        task_id = kwargs.get("task_id")
        status = kwargs.get("status")
        description = kwargs.get("description")

        for task in context.context.todolist:
            if task["id"] == task_id:
                task["status"] = status
                if description:
                    task["description"] = description
                return f"已更新任务 #{task_id}: {task['description']} [{status}]"

        return f"未找到任务 #{task_id}"


class TestTodoListAddTool:
    """测试 TodoListAddTool 本身的行为"""

    def setup_method(self):
        self.context = MockAstrAgentContext()
        self.context.todolist = []
        self.context_wrapper = MockContextWrapper(self.context)
        self.tool = TodoListAddTool()

    @pytest.mark.asyncio
    async def test_assign_ids_when_list_empty(self):
        """空列表时，ID 应该从 1 开始"""
        result = await self.tool.call(
            self.context_wrapper,
            tasks=["task 1", "task 2"],
        )

        # 验证 ID 分配
        assert len(self.context.todolist) == 2
        assert self.context.todolist[0]["id"] == 1
        assert self.context.todolist[0]["description"] == "task 1"
        assert self.context.todolist[0]["status"] == "pending"

        assert self.context.todolist[1]["id"] == 2
        assert self.context.todolist[1]["description"] == "task 2"
        assert self.context.todolist[1]["status"] == "pending"

        assert "已添加 2 个任务" in result

    @pytest.mark.asyncio
    async def test_assign_ids_when_list_non_empty(self):
        """非空列表时，ID 应该在最大 ID 基础上递增"""
        # 预置已有任务
        self.context.todolist = [
            {"id": 1, "description": "existing 1", "status": "pending"},
            {"id": 3, "description": "existing 3", "status": "completed"},
        ]

        await self.tool.call(
            self.context_wrapper,
            tasks=["new 1", "new 2"],
        )

        # 最大 ID 是 3，新任务应该是 4, 5
        assert len(self.context.todolist) == 4
        assert self.context.todolist[2]["id"] == 4
        assert self.context.todolist[2]["description"] == "new 1"

        assert self.context.todolist[3]["id"] == 5
        assert self.context.todolist[3]["description"] == "new 2"

    @pytest.mark.asyncio
    async def test_add_single_task(self):
        """添加单个任务"""
        await self.tool.call(
            self.context_wrapper,
            tasks=["single task"],
        )

        assert len(self.context.todolist) == 1
        assert self.context.todolist[0]["id"] == 1
        assert self.context.todolist[0]["description"] == "single task"

    @pytest.mark.asyncio
    async def test_error_when_tasks_missing(self):
        """缺少 tasks 参数应该返回错误"""
        result = await self.tool.call(self.context_wrapper)

        assert "error" in result.lower()
        assert len(self.context.todolist) == 0

    @pytest.mark.asyncio
    async def test_error_when_tasks_empty(self):
        """tasks 为空列表应该返回错误"""
        result = await self.tool.call(
            self.context_wrapper,
            tasks=[],
        )

        assert "error" in result.lower()
        assert len(self.context.todolist) == 0


class TestTodoListUpdateTool:
    """测试 TodoListUpdateTool 本身的行为"""

    def setup_method(self):
        self.context = MockAstrAgentContext()
        self.context.todolist = [
            {"id": 1, "description": "task 1", "status": "pending"},
            {"id": 2, "description": "task 2", "status": "in_progress"},
        ]
        self.context_wrapper = MockContextWrapper(self.context)
        self.tool = TodoListUpdateTool()

    @pytest.mark.asyncio
    async def test_update_status_and_description(self):
        """可以同时更新状态和描述"""
        result = await self.tool.call(
            self.context_wrapper,
            task_id=1,
            status="completed",
            description="task 1 updated",
        )

        task = self.context.todolist[0]
        assert task["status"] == "completed"
        assert task["description"] == "task 1 updated"
        assert "已更新任务 #1" in result

    @pytest.mark.asyncio
    async def test_update_only_status_keeps_description(self):
        """仅更新状态时，描述不变"""
        original_desc = self.context.todolist[1]["description"]

        await self.tool.call(
            self.context_wrapper,
            task_id=2,
            status="completed",
        )

        task = self.context.todolist[1]
        assert task["status"] == "completed"
        assert task["description"] == original_desc

    @pytest.mark.asyncio
    async def test_update_only_description_keeps_status(self):
        """仅更新描述时，状态不变（但需要传入 status 参数）"""
        # 工具要求必须传入 status，这里预期返回错误提示
        result = await self.tool.call(
            self.context_wrapper,
            task_id=1,
            description="only description updated",
        )

        # 工具应该返回错误提示，而不是修改任务
        assert "参数缺失" in result or "必须提供 status" in result
        # 验证任务未被修改
        assert self.context.todolist[0]["description"] == "task 1"
        assert self.context.todolist[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_update_nonexistent_task_returns_error(self):
        """更新不存在的 task_id 应该返回错误"""
        result = await self.tool.call(
            self.context_wrapper,
            task_id=999,
            status="completed",
        )

        assert "未找到任务 #999" in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["pending", "in_progress", "completed"])
    async def test_accepts_valid_status_values(self, status):
        """验证常见状态值可以被接受"""
        await self.tool.call(
            self.context_wrapper,
            task_id=1,
            status=status,
        )

        task = self.context.todolist[0]
        assert task["status"] == status

    @pytest.mark.asyncio
    async def test_update_preserves_other_tasks(self):
        """更新一个任务不影响其他任务"""
        original_task1 = self.context.todolist[0].copy()
        original_task2 = self.context.todolist[1].copy()

        await self.tool.call(
            self.context_wrapper,
            task_id=1,
            status="completed",
        )

        # 任务2应该不变
        assert self.context.todolist[1] == original_task2
        # 任务1只有状态变了
        assert self.context.todolist[0]["id"] == original_task1["id"]
        assert self.context.todolist[0]["description"] == original_task1["description"]
        assert self.context.todolist[0]["status"] == "completed"
