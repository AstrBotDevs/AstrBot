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

    Note:
        等待期间可被用户新消息打断，无超时限制（后台任务本身有超时控制）
    """
    import asyncio

    manager = _get_manager()
    session_id = event.unified_msg_origin

    from astrbot import logger
    from astrbot.core.background_tool import WaitInterruptedException

    logger.info(f"[wait_tool_result] Looking for task {task_id}")

    task = manager.registry.get(task_id)
    if task is None:
        logger.warning(f"[wait_tool_result] Task {task_id} not found in registry")
        return f"Error: Task {task_id} not found."

    logger.info(f"[wait_tool_result] Task {task_id} found, status: {task.status.value}")

    if task.is_finished():
        # 任务已完成，获取输出日志并返回完整信息
        output = manager.get_task_output(task_id, lines=50)
        return build_task_result(task_id, task, output)

    # 清除之前的中断标记（开始新的等待）
    manager.clear_interrupt_flag(session_id)

    # 设置等待标记，防止任务完成时创建回调事件
    task.is_being_waited = True
    logger.info(f"[wait_tool_result] Set is_being_waited=True for task {task_id}")

    try:
        # 循环等待任务完成，每秒检查一次，无超时限制
        while True:
            # 检查是否有中断标记（新消息到来）
            if manager.check_interrupt_flag(session_id):
                manager.clear_interrupt_flag(session_id)
                logger.info(f"[wait_tool_result] Interrupted by new message")
                # 抛出异常，结束当前LLM响应周期
                raise WaitInterruptedException(task_id=task_id, session_id=session_id)

            task = manager.registry.get(task_id)

            if task.is_finished():
                manager.clear_interrupt_flag(session_id)
                # 任务完成，获取输出日志并返回完整信息
                output = manager.get_task_output(task_id, lines=50)
                return build_task_result(task_id, task, output)

            # 等待1秒后继续检查
            await asyncio.sleep(1)
    finally:
        # 无论如何都要清除等待标记
        task.is_being_waited = False
        logger.info(f"[wait_tool_result] Cleared is_being_waited for task {task_id}")


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
