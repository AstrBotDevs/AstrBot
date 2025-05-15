import threading
import os
from logging import Logger


class LogPipe(threading.Thread):
    def __init__(
        self,
        level,
        logger: Logger,
        identifier=None,
        callback=None,
    ):
        threading.Thread.__init__(self)
        self.daemon = True
        self.level = level
        self.fd_read, self.fd_write = os.pipe()
        self.identifier = identifier
        self.logger = logger
        self.callback = callback
        self.reader = os.fdopen(self.fd_read)
        self.start()

    def fileno(self):
        return self.fd_write

    def run(self):
        for line in iter(self.reader.readline, ""):
            if self.callback:
                self.callback(line.strip())
            self.logger.log(self.level, f"[{self.identifier}] {line.strip()}")

        self.reader.close()

    def close(self):
        os.close(self.fd_write)
