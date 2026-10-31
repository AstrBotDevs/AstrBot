"""Keep console backpressure away from the application event loop."""

import atexit
import math
import queue
import sys
import threading
import time
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

            # Prepare VT or legacy conversion for output on the writer thread.
            # LogManager controls formatted colors using the stream's isatty().
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

    def isatty(self) -> bool:
        """Report the original stream's terminal capability without propagating errors."""
        try:
            return bool(self._original_stream.isatty())
        except Exception:
            return False

    def get_status(self) -> dict:
        """Snapshot process-lifetime counters without waiting on console IO.

        Returns:
            Queue capacity, queued and unfinished records, cumulative drops,
            and writer lifecycle state. Unfinished records include in-flight IO.
            Closed queues may also contain the shutdown marker.
        """
        with self._lock, self._queue.all_tasks_done:
            return {
                "capacity": self._queue.maxsize,
                "queued_records": len(self._queue.queue),
                "unfinished_records": self._queue.unfinished_tasks,
                "dropped_records": self.dropped,
                "closed": self._closed,
                "writer_alive": self._thread.is_alive(),
            }

    def drain(self, timeout: float = 1.0) -> bool:
        """Wait for queued write attempts within a fixed budget.

        Call this outside the event loop. This method is deliberately not named
        ``flush``, which Loguru would invoke synchronously after every record.

        Args:
            timeout: Maximum seconds to wait; zero only checks completion.

        Returns:
            Whether all queued write attempts finished, irrespective of IO errors.

        Raises:
            ValueError: If timeout is negative or not finite.
        """
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Console drain timeout must be finite and nonnegative")
        with self._queue.all_tasks_done:
            return self._queue.all_tasks_done.wait_for(
                lambda: self._queue.unfinished_tasks == 0, timeout=timeout
            )

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
        deadline = time.monotonic() + 0.2
        with self._lock:
            first_close = not self._closed
            if first_close:
                self._closed = True
        if first_close:
            self.drain(max(0.0, deadline - time.monotonic()))
            with self._lock:
                try:
                    self._queue.put_nowait(None)
                except queue.Full:
                    # Admission is closed; only the consumer can change queue
                    # size. Removing at most one record guarantees room to stop.
                    try:
                        self._queue.get_nowait()
                        self._queue.task_done()
                        self.dropped += 1
                    except queue.Empty:
                        pass
                    self._queue.put_nowait(None)
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
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
