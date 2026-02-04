"""LLM工具集

提供给LLM调用的后台任务管理工具。
"""

import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .manager import BackgroundToolManager


# 获取全局管理器实例
def _get_manager() -> BackgroundToolManager:
    return BackgroundToolManager()


# 从配置中读取后台任务等待超时时间
def _get_background_task_wait_timeout() -> int:
    """从配置文件中读取后台任务等待超时时间，如果读取失败则返回默认值300秒"""
    try:
        config_path = os.path.join(get_astrbot_data_path(), "cmd_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
                return config.get("provider_settings", {}).get(
                    "background_task_wait_timeout", 300
                )
    except Exception:
        pass
    return 300


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
        工具输出日志
    """
    manager = _get_manager()

    task = manager.registry.get(task_id)
    if task is None:
        return f"Error: Task {task_id} not found."

    output = manager.get_task_output(task_id, lines=lines)
    status = task.status.value

    if not output:
        return f"Task {task_id} ({status}): No output yet."

    return f"Task {task_id} ({status}):\n{output}"


async def wait_tool_result(
    event: "AstrMessageEvent",
    task_id: str,
    timeout: float | None = None,
) -> str:
    """等待后台工具执行完成（可被新消息打断）

    Args:
        event: 消息事件
        task_id: 任务ID
        timeout: 超时时间（秒），默认从配置中读取

    Returns:
        工具执行结果

    Raises:
        WaitInterruptedException: 当被用户新消息中断时抛出

    Note:
        等待期间可被用户新消息打断
    """
    import asyncio
    import time

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
        if task.result:
            return f"Task {task_id} completed: {task.result}"
        elif task.error:
            return f"Task {task_id} failed: {task.error}"
        else:
            return f"Task {task_id} finished with status: {task.status.value}"

    # 如果没有指定timeout，从配置中读取
    if timeout is None:
        timeout = _get_background_task_wait_timeout()

    start_time = time.time()

    # 清除之前的中断标记（开始新的等待）
    manager.clear_interrupt_flag(session_id)

    # 循环等待任务完成，每秒检查一次
    while True:
        # 检查是否有中断标记（新消息到来）
        if manager.check_interrupt_flag(session_id):
            elapsed = time.time() - start_time
            manager.clear_interrupt_flag(session_id)
            logger.info(
                f"[wait_tool_result] Interrupted by new message after {elapsed:.0f}s"
            )
            # 抛出异常，结束当前LLM响应周期
            raise WaitInterruptedException(task_id=task_id, session_id=session_id)

        task = manager.registry.get(task_id)

        if task.is_finished():
            manager.clear_interrupt_flag(session_id)
            if task.result:
                return f"Task {task_id} completed: {task.result}"
            elif task.error:
                return f"Task {task_id} failed: {task.error}"
            else:
                return f"Task {task_id} finished with status: {task.status.value}"

        elapsed = time.time() - start_time

        # 检查是否超时
        if elapsed >= timeout:
            manager.clear_interrupt_flag(session_id)
            return f"Task {task_id} is still running. Timeout after {timeout}s."

        # 等待1秒后继续检查
        await asyncio.sleep(1)


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
