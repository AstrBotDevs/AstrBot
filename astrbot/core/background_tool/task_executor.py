"""任务执行器

在后台执行工具，捕获输出，支持取消和超时。
"""

import asyncio
import json
import os
import traceback
from typing import Any, Callable, Awaitable, AsyncGenerator

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from .task_state import BackgroundTask, TaskStatus
from .output_buffer import OutputBuffer
from .task_notifier import TaskNotifier


def _get_background_task_timeout() -> int:
    """从配置文件中读取后台任务超时时间，如果读取失败则返回默认值600秒"""
    try:
        config_path = os.path.join(get_astrbot_data_path(), "cmd_config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8-sig") as f:
                config = json.load(f)
                return config.get("provider_settings", {}).get(
                    "background_task_wait_timeout", 600
                )
    except Exception:
        pass
    return 600


class TaskExecutor:
    """任务执行器

    管理后台任务的执行、取消和状态跟踪。
    """

    def __init__(self, output_buffer: OutputBuffer):
        """初始化任务执行器

        Args:
            output_buffer: 输出缓冲区
        """
        self.output_buffer = output_buffer
        self.notifier = TaskNotifier()
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def execute(
        self,
        task: BackgroundTask,
        handler: Callable[..., Awaitable[str] | AsyncGenerator[str, None]],
    ) -> str | None:
        """执行任务

        Args:
            task: 后台任务
            handler: 工具处理函数

        Returns:
            执行结果
        """
        task.start()
        self._cancel_events[task.task_id] = asyncio.Event()

        # 获取后台任务超时时间
        timeout = _get_background_task_timeout()

        try:
            # 创建执行任务
            exec_coro = self._run_handler(task, handler)
            async_task = asyncio.create_task(exec_coro)
            self._running_tasks[task.task_id] = async_task

            # 使用 wait_for 添加超时控制
            try:
                result = await asyncio.wait_for(async_task, timeout=timeout)
            except asyncio.TimeoutError:
                # 超时，取消任务
                async_task.cancel()
                try:
                    await async_task
                except asyncio.CancelledError:
                    pass
                error_msg = f"Task timed out after {timeout}s and was terminated."
                task.fail(error_msg)
                self._log(task.task_id, f"[TIMEOUT] {error_msg}")
                # 生成超时通知消息
                task.notification_message = self.notifier.build_message(task)
                # 主动触发回调
                await self._trigger_callback(task)
                return None

            task.complete(result or "")
            # 生成完成通知消息
            task.notification_message = self.notifier.build_message(task)
            self._log(task.task_id, "[NOTIFICATION] Task completed, notification ready")
            # 主动触发回调
            await self._trigger_callback(task)
            return result

        except asyncio.CancelledError:
            task.cancel()
            # 生成取消通知消息
            task.notification_message = self.notifier.build_message(task)
            self._log(
                task.task_id, "[CANCELLED] Task was cancelled, notification ready"
            )
            # 主动触发回调
            await self._trigger_callback(task)
            return None

        except Exception as e:
            # 检查是否是 wait_tool_result 被中断的情况，这种情况不需要触发回调
            from astrbot.core.background_tool import WaitInterruptedException

            is_wait_interrupted = isinstance(e, WaitInterruptedException)

            error_msg = f"{e}\n{traceback.format_exc()}"
            task.fail(error_msg)

            if is_wait_interrupted:
                # wait_tool_result 被中断是正常行为，不需要通知用户
                self._log(
                    task.task_id, "[INTERRUPTED] Wait interrupted, no callback needed"
                )
            else:
                # 其他错误需要生成通知消息并触发回调
                task.notification_message = self.notifier.build_message(task)
                self._log(task.task_id, f"[ERROR] {error_msg}, notification ready")
                # 主动触发回调
                await self._trigger_callback(task)
            return None

        finally:
            self._cleanup(task.task_id)

    async def _trigger_callback(self, task: BackgroundTask) -> None:
        """主动触发任务完成回调

        创建一个新的消息事件，内容为任务完成通知，放入EventQueue触发AI响应。
        """
        if not task.event:
            logger.warning(
                f"[TaskExecutor] Task {task.task_id} has no event, cannot trigger callback"
            )
            return

        if not task.event_queue:
            logger.warning(
                f"[TaskExecutor] Task {task.task_id} has no event_queue, cannot trigger AI callback"
            )
            return

        if not task.notification_message:
            logger.warning(
                f"[TaskExecutor] Task {task.task_id} has no notification message"
            )
            return

        try:
            import copy

            from astrbot.core.message.components import Plain
            from astrbot.core.platform.astrbot_message import (
                AstrBotMessage,
                MessageMember,
            )
            from astrbot.core.platform.message_type import MessageType

            # 构建通知消息内容
            from .task_state import TaskStatus

            if task.status == TaskStatus.COMPLETED:
                status = "completed successfully"
            elif task.status == TaskStatus.FAILED:
                status = "failed"
            else:
                status = "was cancelled"

            # 构建给AI的通知消息
            notification_text = (
                f"[Background Task Callback]\n"
                f"Task ID: {task.task_id}\n"
                f"Tool: {task.tool_name}\n"
                f"Status: {status}\n"
            )

            if task.result:
                notification_text += f"Result: {task.result}\n"

            if task.error:
                # 只显示错误的前500字符
                error_preview = task.error[:500]
                if len(task.error) > 500:
                    error_preview += "..."
                notification_text += f"Error: {error_preview}\n"

            notification_text += "\nPlease inform the user about this task completion and provide any relevant details."

            # 克隆原始事件的关键属性，创建新的消息对象
            original_event = task.event

            # 创建新的消息对象
            new_message_obj = AstrBotMessage()
            new_message_obj.type = original_event.message_obj.type
            new_message_obj.self_id = original_event.message_obj.self_id
            new_message_obj.session_id = original_event.message_obj.session_id
            new_message_obj.message_id = f"bg_task_{task.task_id}"
            new_message_obj.group = original_event.message_obj.group
            new_message_obj.sender = original_event.message_obj.sender
            new_message_obj.message = [Plain(notification_text)]
            new_message_obj.message_str = notification_text
            new_message_obj.raw_message = None
            new_message_obj.timestamp = int(__import__("time").time())

            # 创建新的事件对象（使用相同类型的事件）
            # 通过深拷贝原始事件来创建新实例，保留平台特定属性（如 bot）
            new_event = copy.copy(original_event)
            new_event.message_str = notification_text
            new_event.message_obj = new_message_obj
            # 重置关键状态，避免被认为已处理
            new_event._result = None
            new_event._has_send_oper = False
            new_event._extras = {}
            # 重新初始化 trace
            from astrbot.core.utils.trace import TraceSpan

            new_event.trace = TraceSpan(
                name="BackgroundTaskCallback",
                umo=new_event.unified_msg_origin,
                sender_name=new_event.get_sender_name(),
                message_outline=f"[Background Task {task.task_id}]",
            )
            new_event.span = new_event.trace

            # 标记这是一个后台任务回调事件
            new_event.is_wake = True
            new_event.is_at_or_wake_command = True

            # 添加标记，表明这是后台任务回调
            new_event.set_extra("is_background_task_callback", True)
            new_event.set_extra("background_task_id", task.task_id)

            logger.info(
                f"[TaskExecutor] Task {task.task_id} creating callback event, "
                f"is_wake={new_event.is_wake}, is_at_or_wake_command={new_event.is_at_or_wake_command}"
            )

            # 将新事件放入队列
            task.event_queue.put_nowait(new_event)

            # 标记通知已发送
            task.notification_sent = True

            logger.info(
                f"[TaskExecutor] Task {task.task_id} callback event queued for AI processing"
            )

        except Exception as e:
            logger.error(f"[TaskExecutor] Failed to trigger callback: {e}")
            import traceback

            logger.error(traceback.format_exc())

    async def _run_handler(
        self,
        task: BackgroundTask,
        handler: Callable,
    ) -> str | None:
        """运行处理函数"""
        self._log(task.task_id, f"[START] Executing {task.tool_name}")
        self._log(task.task_id, f"[ARGS] {task.tool_args}")

        try:
            # 构建调用参数，如果有event则传递
            call_args = dict(task.tool_args)
            if task.event is not None:
                call_args["event"] = task.event

            result = handler(**call_args)

            # 检查是否是异步生成器
            if hasattr(result, "__anext__"):
                final_result = None
                async for output in result:
                    if output is not None:
                        self._log(task.task_id, str(output))
                        final_result = output
                return final_result

            # 检查是否是协程
            elif asyncio.iscoroutine(result):
                return await result

            else:
                return result

        except Exception as e:
            raise

    async def cancel(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否取消成功
        """
        if task_id not in self._running_tasks:
            return False

        async_task = self._running_tasks.get(task_id)
        if async_task and not async_task.done():
            async_task.cancel()
            # 设置取消事件
            if task_id in self._cancel_events:
                self._cancel_events[task_id].set()
            return True

        return False

    def is_running(self, task_id: str) -> bool:
        """检查任务是否运行中

        Args:
            task_id: 任务ID

        Returns:
            是否运行中
        """
        async_task = self._running_tasks.get(task_id)
        return async_task is not None and not async_task.done()

    def _log(self, task_id: str, message: str) -> None:
        """记录日志到缓冲区"""
        self.output_buffer.append(task_id, message)
        logger.debug(f"[BackgroundTask:{task_id}] {message}")

    def _cleanup(self, task_id: str) -> None:
        """清理任务资源"""
        self._running_tasks.pop(task_id, None)
        self._cancel_events.pop(task_id, None)
