"""输出缓冲区

缓存工具执行的实时输出日志，支持环形缓冲。
"""

import threading
from collections import deque


class OutputBuffer:
    """输出缓冲区

    为每个任务维护一个环形缓冲区，存储输出日志。

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
        self._lock = threading.Lock()

    def append(self, task_id: str, line: str) -> None:
        """追加一行输出

        Args:
            task_id: 任务ID
            line: 输出行
        """
        with self._lock:
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
        with self._lock:
            if task_id in self._buffers:
                self._buffers[task_id].clear()

    def line_count(self, task_id: str) -> int:
        """获取任务的输出行数

        Args:
            task_id: 任务ID

        Returns:
            输出行数
        """
        buffer = self._buffers.get(task_id)
        return len(buffer) if buffer else 0
