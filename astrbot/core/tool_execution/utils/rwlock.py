"""读写锁实现

优化读多写少场景的并发性能。
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager


class RWLock:
    """读写锁

    允许多个读取者同时访问，但写入者独占访问。
    适用于读多写少的场景，如任务注册表和输出缓冲区。

    用法:
        lock = RWLock()

        # 读取（允许并发）
        with lock.read():
            data = some_dict.get(key)

        # 写入（独占）
        with lock.write():
            some_dict[key] = value
    """

    def __init__(self):
        self._read_ready = threading.Condition(threading.Lock())
        self._readers = 0
        self._writers_waiting = 0
        self._writer_active = False

    @contextmanager
    def read(self) -> Generator[None, None, None]:
        """获取读锁"""
        with self._read_ready:
            # 等待直到没有活跃的写入者和等待的写入者
            while self._writer_active or self._writers_waiting > 0:
                self._read_ready.wait()
            self._readers += 1

        try:
            yield
        finally:
            with self._read_ready:
                self._readers -= 1
                if self._readers == 0:
                    self._read_ready.notify_all()

    @contextmanager
    def write(self) -> Generator[None, None, None]:
        """获取写锁"""
        with self._read_ready:
            self._writers_waiting += 1
            # 等待直到没有读取者和活跃的写入者
            while self._readers > 0 or self._writer_active:
                self._read_ready.wait()
            self._writers_waiting -= 1
            self._writer_active = True

        try:
            yield
        finally:
            with self._read_ready:
                self._writer_active = False
                self._read_ready.notify_all()
