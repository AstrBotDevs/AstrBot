"""任务执行器

在后台执行工具，捕获输出，支持取消和超时。
"""

import asyncio
import json
import os
import traceback
from collections.abc import AsyncGenerator, Awaitable, Callable

from astrbot import logger
from astrbot.core.tool_execution.utils.sanitizer import sanitize_for_log
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .callback_publisher import CallbackPublisher
from .output_buffer import OutputBuffer
from .task_notifier import TaskNotifier
from .task_state import BackgroundTask


def _get_background_task_timeout() -> int:
    """从配置文件中读取后台任务超时时间，如果读取失败则返回默认值600秒

    使用模块级缓存避免每次执行都读取配置文件。
    """
    return _ConfigCache.get_timeout()


class _ConfigCache:
    """配置缓存

    缓存配置值，避免频繁读取配置文件。
    """

    _timeout: int | None = None
    _last_load: float = 0
    _cache_ttl: float = 60.0  # 缓存有效期60秒

    @classmethod
    def get_timeout(cls) -> int:
        """获取超时配置，带缓存"""
        import time

        current_time = time.time()

        # 检查缓存是否过期
        if (
            cls._timeout is not None
            and (current_time - cls._last_load) < cls._cache_ttl
        ):
            return cls._timeout

        # 重新加载配置
        try:
            config_path = os.path.join(get_astrbot_data_path(), "cmd_config.json")
            if os.path.exists(config_path):
                with open(config_path, encoding="utf-8-sig") as f:
                    config = json.load(f)
                    cls._timeout = config.get("provider_settings", {}).get(
                        "background_task_wait_timeout", 600
                    )
                    cls._last_load = current_time
                    return cls._timeout
        except Exception:
            pass

        cls._timeout = 600
        cls._last_load = current_time
        return cls._timeout


class TaskExecutor:
    """任务执行器

    管理后台任务的执行、取消和状态跟踪。
    """

    def __init__(
        self,
        output_buffer: OutputBuffer,
        callback_publisher: CallbackPublisher | None = None,
    ):
        """初始化任务执行器

        Args:
            output_buffer: 输出缓冲区
            callback_publisher: 回调发布器，默认创建新实例
        """
        self.output_buffer = output_buffer
        self.notifier = TaskNotifier()
        self.callback_publisher = callback_publisher or CallbackPublisher()
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
                # 生成超时通知消息（包含输出日志）
                output = "\n".join(self.output_buffer.get_recent(task.task_id, n=50))
                task.notification_message = self.notifier.build_message(task, output)
                # 主动触发回调
                await self.callback_publisher.publish(task)
                return None

            task.complete(result or "")
            # 生成完成通知消息（包含输出日志）
            output = "\n".join(self.output_buffer.get_recent(task.task_id, n=50))
            task.notification_message = self.notifier.build_message(task, output)
            self._log(task.task_id, "[NOTIFICATION] Task completed, notification ready")
            # 主动触发回调
            await self.callback_publisher.publish(task)
            return result

        except asyncio.CancelledError:
            task.cancel()
            # 生成取消通知消息（包含输出日志）
            output = "\n".join(self.output_buffer.get_recent(task.task_id, n=50))
            task.notification_message = self.notifier.build_message(task, output)
            self._log(
                task.task_id, "[CANCELLED] Task was cancelled, notification ready"
            )
            # 主动触发回调
            await self.callback_publisher.publish(task)
            return None

        except Exception as e:
            # 检查是否是 wait_tool_result 被中断的情况，这种情况不需要触发回调
            from astrbot.core.background_tool import WaitInterruptedException

            is_wait_interrupted = isinstance(e, WaitInterruptedException)

            # 用户可见的错误信息（不含敏感堆栈）
            user_error_msg = f"Task failed: {type(e).__name__}: {e}"
            # 仅在 DEBUG 日志中记录完整堆栈
            debug_error_msg = f"{e}\n{traceback.format_exc()}"
            logger.debug(
                f"[BackgroundTask:{task.task_id}] Full traceback: {debug_error_msg}"
            )

            task.fail(user_error_msg)

            if is_wait_interrupted:
                # wait_tool_result 被中断是正常行为，不需要通知用户
                self._log(
                    task.task_id, "[INTERRUPTED] Wait interrupted, no callback needed"
                )
            else:
                # 其他错误需要生成通知消息并触发回调（包含输出日志）
                output = "\n".join(self.output_buffer.get_recent(task.task_id, n=50))
                task.notification_message = self.notifier.build_message(task, output)
                self._log(task.task_id, f"[ERROR] {user_error_msg}, notification ready")
                # 主动触发回调
                await self.callback_publisher.publish(task)
            return None

        finally:
            self._cleanup(task.task_id)
            task.release_references()  # 释放大对象引用，防止内存泄露

    async def _run_handler(
        self,
        task: BackgroundTask,
        handler: Callable,
    ) -> str | None:
        """运行处理函数"""
        self._log(task.task_id, f"[START] Executing {task.tool_name}")
        # 使用脱敏后的参数，防止敏感信息泄露
        self._log(task.task_id, f"[ARGS] {sanitize_for_log(task.tool_args)}")

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
                # handler 可能通过 event.set_result() 设置结果而非直接 return
                if final_result is None and task.event is not None:
                    event_result = task.event.get_result()
                    if event_result is not None:
                        final_result = event_result.get_plain_text()
                        self._log(
                            task.task_id,
                            f"[EVENT_RESULT] Got result from event: {final_result[:200] if final_result else None}",
                        )
                return final_result

            # 检查是否是协程
            elif asyncio.iscoroutine(result):
                coro_result = await result
                # handler 可能通过 event.set_result() 设置结果而非直接 return
                if coro_result is None and task.event is not None:
                    event_result = task.event.get_result()
                    if event_result is not None:
                        coro_result = event_result.get_plain_text()
                        self._log(
                            task.task_id,
                            f"[EVENT_RESULT] Got result from event: {coro_result[:200] if coro_result else None}",
                        )
                return coro_result

            else:
                return result

        except Exception:
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
