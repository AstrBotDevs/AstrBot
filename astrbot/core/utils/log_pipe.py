import io
import os
import threading
from collections.abc import Callable, Iterable
from logging import Logger
from types import TracebackType
from typing import Any, Self


class LogPipe(threading.Thread, io.TextIOBase):
    """A pipe wrapper that routes written content to a logger.

    Implements TextIO interface for compatibility with code expecting
    a text stream, while also logging all written content.
    """

    def __init__(
        self,
        level: int,
        logger: Logger,
        identifier: str | None = None,
        callback: Callable[[str], None] | None = None,
    ) -> None:
        threading.Thread.__init__(self)
        self.daemon = True
        self.level = level
        self._logger = logger
        self._identifier = identifier
        self._callback = callback
        self._closed = False
        self.fd_read, self.fd_write = os.pipe()
        self._reader = os.fdopen(self.fd_read, "r")
        self.mode = "w"
        self.name = f"<LogPipe-{self._identifier}>"
        self.start()

    def fileno(self) -> int:
        return self.fd_write

    def write(self, s: str) -> int:
        """Write string to pipe - content will be logged."""
        if self._closed:
            raise ValueError("I/O operation on closed file")
        self._logger.log(self.level, f"[{self._identifier}] {s.rstrip()}")
        if self._callback:
            self._callback(s.strip())
        return len(s)

    def flush(self) -> None:
        """No-op for compatibility - log writes are immediate."""
        pass

    def close(self) -> None:
        """Close the write end of the pipe."""
        if not self._closed:
            self._closed = True
            os.close(self.fd_write)

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return not self._closed

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def writelines(self, lines: Iterable[Any]) -> None:
        for line in lines:
            self.write(line)

    def run(self) -> None:
        """Read from pipe and log each line."""
        for line in iter(self._reader.readline, ""):
            if self._closed:
                break
            stripped = line.strip()
            if stripped:
                self._logger.log(self.level, f"[{self._identifier}] {stripped}")
                if self._callback:
                    self._callback(stripped)
        self._reader.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
