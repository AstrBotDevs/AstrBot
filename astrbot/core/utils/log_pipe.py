import locale
import os
import threading
from logging import Logger


class LogPipe(threading.Thread):
    """Drain a subprocess pipe and forward every line to a Python logger.

    Lines are decoded UTF-8 first, falling back to the host locale encoding
    with ``errors="replace"``: children do not share one stderr encoding
    (Node.js writes UTF-8 on Windows regardless of locale, while a Python
    child below 3.15 without ``PYTHONUTF8`` logs in the host locale, which is
    the same machine's locale). Undecodable bytes degrade to replacement
    characters, so a bad line can never kill the drain thread and deadlock
    the child on a full OS pipe buffer.
    """

    def __init__(
        self,
        level,
        logger: Logger,
        identifier=None,
        callback=None,
    ) -> None:
        """Initialize the pipe and start the drain thread.

        Args:
            level: Log level used when forwarding lines.
            logger: Logger that receives each drained line.
            identifier: Prefix prepended to every forwarded line.
            callback: Optional callable invoked with each stripped line
                before it is logged.
        """
        threading.Thread.__init__(self)
        self.daemon = True
        self.level = level
        self.fd_read, self.fd_write = os.pipe()
        self.identifier = identifier
        self.logger = logger
        self.callback = callback
        self.reader = os.fdopen(self.fd_read, "rb")
        self.start()

    def fileno(self):
        """Return the write end of the pipe for the subprocess.

        Returns:
            The file descriptor the child process should write to.
        """
        return self.fd_write

    def run(self) -> None:
        """Read lines until EOF and forward them one at a time.

        A single failing line (undecodable bytes, throwing callback,
        unserialisable payload) must not kill the drain thread: a wedged
        child would otherwise deadlock on stderr once the OS pipe buffer
        fills up.
        """
        for raw in iter(self.reader.readline, b""):
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                line = raw.decode(locale.getpreferredencoding(False), errors="replace")
            try:
                if self.callback:
                    self.callback(line.strip())
                self.logger.log(self.level, f"[{self.identifier}] {line.strip()}")
            except Exception:
                self.logger.exception(
                    f"[{self.identifier}] failed to forward a subprocess log line"
                )

        self.reader.close()

    def close(self) -> None:
        """Close the write end so the drain thread observes EOF.

        Call this on the parent side once the child has been terminated.
        """
        os.close(self.fd_write)
