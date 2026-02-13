"""任务注册表

管理后台任务的注册、查询、更新、删除。
"""

import threading
import time
from typing import Any

from astrbot.core.tool_execution.utils.rwlock import RWLock

from .task_state import BackgroundTask, TaskStatus


class TaskRegistry:
    """任务注册表

    线程安全的任务管理器，支持按ID和会话查询任务。
    使用读写锁优化读多写少场景的并发性能。
    """

    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: dict[str, BackgroundTask] = {}
                    cls._instance._session_index: dict[str, set[str]] = {}
                    cls._instance._rwlock = RWLock()
        return cls._instance

    def register(self, task: BackgroundTask) -> str:
        """注册任务

        Args:
            task: 后台任务对象

        Returns:
            任务ID
        """
        with self._rwlock.write():
            self._tasks[task.task_id] = task

            # 更新会话索引
            if task.session_id not in self._session_index:
                self._session_index[task.session_id] = set()
            self._session_index[task.session_id].add(task.task_id)

        return task.task_id

    def get(self, task_id: str) -> BackgroundTask | None:
        """获取任务

        Args:
            task_id: 任务ID

        Returns:
            任务对象，不存在返回None
        """
        with self._rwlock.read():
            return self._tasks.get(task_id)

    def get_by_session(self, session_id: str) -> list[BackgroundTask]:
        """按会话获取任务

        Args:
            session_id: 会话ID

        Returns:
            该会话的所有任务列表
        """
        with self._rwlock.read():
            task_ids = self._session_index.get(session_id, set())
            return [self._tasks[tid] for tid in task_ids if tid in self._tasks]

    def get_running_tasks(self, session_id: str) -> list[BackgroundTask]:
        """获取会话中运行中的任务

        Args:
            session_id: 会话ID

        Returns:
            运行中的任务列表
        """
        tasks = self.get_by_session(session_id)
        return [t for t in tasks if t.status == TaskStatus.RUNNING]

    def update(self, task_id: str, **kwargs: Any) -> bool:
        """更新任务属性

        Args:
            task_id: 任务ID
            **kwargs: 要更新的属性

        Returns:
            是否更新成功
        """
        with self._rwlock.write():
            task = self._tasks.get(task_id)
            if task is None:
                return False

            for key, value in kwargs.items():
                if hasattr(task, key):
                    setattr(task, key, value)

        return True

    def remove(self, task_id: str) -> bool:
        """删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否删除成功
        """
        with self._rwlock.write():
            task = self._tasks.pop(task_id, None)
            if task is None:
                return False

            # 更新会话索引
            if task.session_id in self._session_index:
                self._session_index[task.session_id].discard(task_id)

        return True

    def cleanup_finished_tasks(self, max_age_seconds: float = 3600) -> int:
        """清理已完成的旧任务

        Args:
            max_age_seconds: 任务完成后保留的最大时间（秒），默认1小时

        Returns:
            清理的任务数量
        """
        current_time = time.time()
        tasks_to_remove = []

        # 使用读锁收集要删除的任务
        with self._rwlock.read():
            for task_id, task in self._tasks.items():
                # 只清理已完成的任务
                if task.is_finished() and task.completed_at is not None:
                    age = current_time - task.completed_at
                    if age > max_age_seconds:
                        tasks_to_remove.append(task_id)

        # 使用写锁执行删除
        removed_count = 0
        for task_id in tasks_to_remove:
            if self.remove(task_id):
                removed_count += 1

        return removed_count

    def clear(self) -> None:
        """清空所有任务"""
        with self._rwlock.write():
            self._tasks.clear()
            self._session_index.clear()

    def get_all_task_ids(self) -> set[str]:
        """获取所有任务ID（线程安全）"""
        with self._rwlock.read():
            return set(self._tasks.keys())

    def get_all_session_ids(self) -> set[str]:
        """获取所有有活跃任务的会话ID（线程安全）"""
        with self._rwlock.read():
            return {task.session_id for task in self._tasks.values()}

    def count(self) -> int:
        """获取任务数量"""
        with self._rwlock.read():
            return len(self._tasks)

    def count_by_status(self) -> dict[str, int]:
        """按状态统计任务数量

        Returns:
            状态 -> 数量的字典
        """
        with self._rwlock.read():
            counts: dict[str, int] = {}
            for task in self._tasks.values():
                status = task.status.value
                counts[status] = counts.get(status, 0) + 1
            return counts
