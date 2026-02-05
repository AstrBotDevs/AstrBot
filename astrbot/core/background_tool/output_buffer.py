"""输出缓冲区

缓存工具执行的实时输出日志，支持环形缓冲。
"""

from collections import deque

from astrbot.core.tool_execution.utils.rwlock import RWLock


class OutputBuffer:
    """输出缓冲区

    为每个任务维护一个环形缓冲区，存储输出日志。
    使用读写锁优化读多写少场景的并发性能。

    Attributes:
        max_lines: 每个任务的最大行数
    """

    def __init__(self, max_lines: int = 1000):
        """初始化输出缓冲区

        Args:
            max_lines: 每个任务的最大行数，超过后自动丢弃旧行
        """
        self.max_lines = max_lines
        self._buffers: dict[str, deque[str]] = {}
        self._rwlock = RWLock()

    def append(self, task_id: str, line: str) -> None:
        """追加一行输出

        Args:
            task_id: 任务ID
            line: 输出行
        """
        with self._rwlock.write():
            if task_id not in self._buffers:
                self._buffers[task_id] = deque(maxlen=self.max_lines)
            self._buffers[task_id].append(line)

    def get_all(self, task_id: str) -> list[str]:
        """获取所有输出行

        Args:
            task_id: 任务ID

        Returns:
            所有输出行列表
        """
        with self._rwlock.read():
            buffer = self._buffers.get(task_id)
            if buffer is None:
                return []
            return list(buffer)

    def get_recent(self, task_id: str, n: int = 50) -> list[str]:
        """获取最近N行输出

        Args:
            task_id: 任务ID
            n: 行数

        Returns:
            最近N行输出列表
        """
        all_lines = self.get_all(task_id)
        return all_lines[-n:] if len(all_lines) > n else all_lines

    def clear(self, task_id: str) -> None:
        """清空任务的输出缓冲区

        Args:
            task_id: 任务ID
        """
        with self._rwlock.write():
            if task_id in self._buffers:
                self._buffers[task_id].clear()

    def line_count(self, task_id: str) -> int:
        """获取任务的输出行数

        Args:
            task_id: 任务ID

        Returns:
            输出行数
        """
        with self._rwlock.read():
            buffer = self._buffers.get(task_id)
            return len(buffer) if buffer else 0

    def remove(self, task_id: str) -> None:
        """删除任务的输出缓冲区

        Args:
            task_id: 任务ID
        """
        with self._rwlock.write():
            self._buffers.pop(task_id, None)

    def cleanup_old_buffers(self, valid_task_ids: set[str]) -> int:
        """清理不再有效的任务缓冲区

        Args:
            valid_task_ids: 仍然有效的任务ID集合

        Returns:
            清理的缓冲区数量
        """
        with self._rwlock.write():
            to_remove = [tid for tid in self._buffers if tid not in valid_task_ids]
            for tid in to_remove:
                del self._buffers[tid]
            return len(to_remove)
