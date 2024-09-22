from asyncio import Queue
from collections import deque
from typing import Deque

class CachedQueue(Queue):
    def __init__(self, maxsize: int = 0, cachesize: int = 200):
        super().__init__(maxsize)
        self.cache = deque(maxlen=cachesize)

    def put_nowait(self, item):
        self.cache.append(item)
        super().put_nowait(item)

    def get_nowait(self):
        item = super().get_nowait()
        return item

    def get(self):
        item = super().get()
        return item

    def clear(self):
        self.cache.clear()
        with self.mutex:
            self._queue.clear()

    def get_cache(self) -> Deque:
        return self.cache