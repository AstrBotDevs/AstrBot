"""Keep console backpressure away from the application event loop."""

import atexit
import queue
import sys
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
        self._original_stream = stream
        self._stream = stream
        self.encoding = getattr(stream, "encoding", None)
        if sys.platform == "win32" and (
            stream is sys.__stdout__ or stream is sys.__stderr__
        ):
            from colorama import AnsiToWin32

            # Enable native VT or convert ANSI on legacy consoles in the writer
            # thread. Preserve forced colors when stdout is redirected to a pipe.
            converter = AnsiToWin32(stream, strip=False)
            if converter.should_wrap():
                self._stream = converter.stream
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=capacity)
        self._lock = threading.Lock()
        self._closed = False
        self.dropped = 0
        self._thread = threading.Thread(
            target=self._drain, name="astrbot_console_writer", daemon=True
        )
        self._thread.start()
        atexit.register(self._shutdown)

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
                self._stream.write(message)
                self._stream.flush()
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
            if not self._closed:
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
        if not self._thread.is_alive():
            atexit.unregister(self._shutdown)

    def _shutdown(self) -> None:
        """Avoid a second blocking flush of a stalled standard stream at exit."""
        self.close()
        if self._thread.is_alive():
            # CPython flushes both standard streams after atexit. A daemon may
            # still hold the TextIO buffer lock, so skip only references to that
            # exact stream. Keep its object alive in the writer; do not close it.
            if sys.stdout is self._original_stream:
                sys.stdout = None
            if sys.stderr is self._original_stream:
                sys.stderr = None
