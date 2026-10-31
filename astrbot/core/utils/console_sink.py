"""Keep console backpressure away from the application event loop."""

import atexit
import io
import queue
import threading
from typing import TextIO


class BoundedConsoleSink:
    """Write console records on one daemon with bounded, nonblocking admission."""

    def __init__(self, stream: TextIO, capacity: int = 512) -> None:
        """Start a console writer without taking ownership of the stream.

        Args:
            stream: Console or redirected standard output to write to.
            capacity: Maximum number of pending console records.

        Raises:
            ValueError: If capacity is not positive.
        """
        if capacity <= 0:
            raise ValueError("Console queue capacity must be positive")
        self._stream = stream
        self._raw_stream = None
        if isinstance(stream, io.TextIOWrapper):
            # Bypass buffered stdout locks: a blocked daemon must not hold one
            # during interpreter shutdown. Raw console IO also handles Windows.
            self._raw_stream = getattr(stream.buffer, "raw", stream.buffer)
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=capacity)
        self._lock = threading.Lock()
        self._closed = False
        self.dropped = 0
        self._thread = threading.Thread(
            target=self._drain, name="astrbot_console_writer", daemon=True
        )
        self._thread.start()
        atexit.register(self.close)

    def write(self, message: str) -> None:
        """Queue a record, dropping only its console copy when full.

        Args:
            message: Formatted log record, including its line ending.
        """
        with self._lock:
            if self._closed:
                return
            try:
                self._queue.put_nowait(str(message))
            except queue.Full:
                self.dropped += 1

    def _drain(self) -> None:
        """Isolate stream IO and report dropped records after output recovers."""
        reported_dropped = 0
        while True:
            message = self._queue.get()
            try:
                if message is None:
                    return
                with self._lock:
                    dropped = self.dropped
                if dropped > reported_dropped:
                    message += (
                        f"[AstrBot] Skipped {dropped - reported_dropped} console log "
                        "records because the console queue was full.\n"
                    )
                if self._raw_stream is None:
                    self._stream.write(message)
                    self._stream.flush()
                else:
                    data = memoryview(
                        message.encode(
                            self._stream.encoding or "utf-8",
                            self._stream.errors or "backslashreplace",
                        )
                    )
                    while data:
                        written = self._raw_stream.write(data)
                        if not written:
                            raise OSError("Console write made no progress")
                        data = data[written:]
                reported_dropped = dropped
            except Exception:
                # Reporting via the logger would recurse into this sink.
                pass
            finally:
                self._queue.task_done()

    def close(self) -> None:
        """Allow a short drain at exit, without waiting on an unread console.

        This is deliberately not named ``stop`` or ``flush``: Loguru invokes
        those synchronously when removing a sink or logging a record. The same
        writer is shared across console log-level changes.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            while True:
                try:
                    self._queue.put_nowait(None)
                    break
                except queue.Full:
                    try:
                        self._queue.get_nowait()
                        self._queue.task_done()
                        self.dropped += 1
                    except queue.Empty:
                        pass
        self._thread.join(timeout=0.2)
        atexit.unregister(self.close)
