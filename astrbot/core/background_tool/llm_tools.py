"""LLM工具集

提供给LLM调用的后台任务管理工具。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .manager import BackgroundToolManager
from .task_formatter import build_task_result


# 获取全局管理器实例
def _get_manager() -> BackgroundToolManager:
    return BackgroundToolManager()


async def get_tool_output(
    event: "AstrMessageEvent",
    task_id: str,
    lines: int = 50,
) -> str:
    """查看后台工具的输出日志

    Args:
        event: 消息事件
        task_id: 任务ID
        lines: 返回最近N行日志，默认50行

    Returns:
        工具输出日志和最终结果
    """
    manager = _get_manager()

    task = manager.registry.get(task_id)
    if task is None:
        return f"Error: Task {task_id} not found."

    output = manager.get_task_output(task_id, lines=lines)
    return build_task_result(task_id, task, output)


async def wait_tool_result(
    event: "AstrMessageEvent",
    task_id: str,
) -> str:
    """等待后台工具执行完成（可被新消息打断）

    Args:
        event: 消息事件
        task_id: 任务ID

    Returns:
        工具执行结果

    Raises:
        WaitInterruptedException: 当被用户新消息中断时抛出
    """
    import asyncio

    manager = _get_manager()
    session_id = event.unified_msg_origin

    from astrbot import logger
    from astrbot.core.background_tool import WaitInterruptedException

    logger.info(f"[wait_tool_result] Looking for task {task_id}")

    task = manager.registry.get(task_id)
    if task is None:
        return f"Error: Task {task_id} not found."

    if task.is_finished():
        output = manager.get_task_output(task_id, lines=50)
        return build_task_result(task_id, task, output)

    manager.clear_interrupt_flag(session_id)
    task.is_being_waited = True
    logger.info(f"[wait_tool_result] Using event-driven wait for task {task_id}")

    try:
        while True:
            # 检查中断标记
            if manager.check_interrupt_flag(session_id):
                manager.clear_interrupt_flag(session_id)
                raise WaitInterruptedException(task_id=task_id, session_id=session_id)

            # 使用事件等待，超时0.5秒后检查中断
            if task.completion_event:
                try:
                    await asyncio.wait_for(task.completion_event.wait(), timeout=0.5)
                    break  # 事件触发，任务完成
                except asyncio.TimeoutError:
                    pass  # 继续循环检查中断
            else:
                await asyncio.sleep(0.5)
                if task.is_finished():
                    break
    finally:
        task.is_being_waited = False

    output = manager.get_task_output(task_id, lines=50)
    return build_task_result(task_id, task, output)


async def stop_tool(
    event: "AstrMessageEvent",
    task_id: str,
) -> str:
    """终止正在执行的后台工具

    Args:
        event: 消息事件
        task_id: 任务ID

    Returns:
        终止结果
    """
    manager = _get_manager()

    task = manager.registry.get(task_id)
    if task is None:
        return f"Error: Task {task_id} not found."

    if task.is_finished():
        return f"Task {task_id} has already finished ({task.status.value})."

    success = await manager.stop_task(task_id)

    if success:
        return f"Task {task_id} has been stopped/cancelled."
    else:
        return f"Failed to stop task {task_id}."


async def list_running_tools(
    event: "AstrMessageEvent",
) -> str:
    """列出当前会话中正在运行的后台工具

    Args:
        event: 消息事件

    Returns:
        运行中的工具列表
    """
    manager = _get_manager()
    session_id = event.unified_msg_origin

    running_tasks = manager.list_running_tasks(session_id)

    if not running_tasks:
        return "No background tools are currently running."

    lines = ["Running background tools:"]
    for task in running_tasks:
        lines.append(f"- {task['task_id']}: {task['tool_name']} ({task['status']})")

    return "\n".join(lines)
