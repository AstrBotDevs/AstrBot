"""TodoList Tool for Agent internal task management."""

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


@dataclass
class TodoListAddTool(FunctionTool[AstrAgentContext]):
    name: str = "todolist_add"
    description: str = (
        "这个工具用于规划你的主要工作流程。请根据任务的整体复杂度，"
        "添加3到7个主要的核心任务到待办事项列表中。每个任务应该是可执行的、明确的步骤。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task descriptions to add",
                },
            },
            "required": ["tasks"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
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


@dataclass
class TodoListUpdateTool(FunctionTool[AstrAgentContext]):
    name: str = "todolist_update"
    description: str = (
        "Update a task's status or description in your todo list. "
        "Status can be: pending, in_progress, completed."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to update",
                },
                "status": {
                    "type": "string",
                    "description": "New status: pending, in_progress, or completed",
                },
                "description": {
                    "type": "string",
                    "description": "Optional new description",
                },
            },
            "required": ["task_id", "status"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
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


TODOLIST_ADD_TOOL = TodoListAddTool()
TODOLIST_UPDATE_TOOL = TodoListUpdateTool()
