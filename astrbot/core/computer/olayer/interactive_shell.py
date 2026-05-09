"""
Interactive Shell component protocol.

Provides stateful, bidirectional interaction with long-running shell processes.
This is distinct from ShellComponent which is designed for one-shot command execution.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class InteractiveSessionState(Enum):
    """State of an interactive shell session."""

    RUNNING = "running"
    """Process is running and waiting for input or producing output."""

    WAITING_INPUT = "waiting_input"
    """Process appears to be waiting for user input (prompt detected)."""

    OUTPUT_READY = "output_ready"
    """Output is available to read."""

    TERMINATED = "terminated"
    """Process has exited."""

    ERROR = "error"
    """An error occurred in the session."""


@dataclass
class InteractiveSession:
    """Represents an active interactive shell session."""

    session_id: str
    """Unique identifier for this session."""

    command: str
    """The original command that started this session."""

    pid: int
    """Process ID of the running shell process."""

    state: InteractiveSessionState
    """Current state of the session."""

    exit_code: int | None = None
    """Exit code if the process has terminated, otherwise None."""

    error_message: str | None = None
    """Error message if state is ERROR."""

    created_at: float | None = None
    """Timestamp when the session was created (time.time())."""

    last_activity: float | None = None
    """Timestamp of the last activity (send/read) on this session."""


class InteractiveShellComponent(Protocol):
    """Protocol for interactive shell operations.

    Unlike ShellComponent which executes commands in a fire-and-forget manner,
    InteractiveShellComponent maintains persistent sessions with running processes,
    allowing multi-turn bidirectional communication.
    """

    async def start(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        shell: bool = True,
    ) -> InteractiveSession:
        """Start an interactive shell session.

        Launches the given command as a persistent process and returns a session
        object that can be used for subsequent send/read operations.

        Args:
            command: The shell command to execute.
            cwd: Working directory for the process. Defaults to AstrBot root.
            env: Additional environment variables to set.
            shell: Whether to execute through the system shell.

        Returns:
            InteractiveSession with the assigned session_id and process info.
        """
        ...

    async def send(
        self,
        session_id: str,
        input_data: str,
        send_eof: bool = False,
    ) -> None:
        """Send input to an interactive session.

        Writes the given data to the session's stdin. A newline is automatically
        appended if the input does not end with one.

        Args:
            session_id: The session identifier returned by start().
            input_data: The text to send to the process.
            send_eof: If True, close stdin after sending (signals EOF).
        """
        ...

    async def read(
        self,
        session_id: str,
        timeout: float = 5.0,
        max_chars: int | None = None,
    ) -> str:
        """Read output from an interactive session.

        Reads available stdout/stderr from the session's process. This method
        blocks until output is available or the timeout expires.

        Args:
            session_id: The session identifier.
            timeout: Maximum seconds to wait for output.
            max_chars: Maximum characters to read, or None for unlimited.

        Returns:
            The output text from the process.
        """
        ...

    async def interact(
        self,
        session_id: str,
        input_data: str,
        timeout: float = 5.0,
        max_chars: int | None = None,
    ) -> str:
        """Send input and read output in one atomic operation.

        This is a convenience method equivalent to send() followed by read().

        Args:
            session_id: The session identifier.
            input_data: The text to send.
            timeout: Maximum seconds to wait for output after sending.
            max_chars: Maximum characters to read.

        Returns:
            The output text from the process after sending the input.
        """
        ...

    async def terminate(
        self,
        session_id: str,
        graceful: bool = True,
    ) -> InteractiveSession:
        """Terminate an interactive session.

        Args:
            session_id: The session identifier.
            graceful: If True, send SIGINT/CTRL+C first, then kill if needed.

        Returns:
            The final session state.
        """
        ...

    async def get_session(self, session_id: str) -> InteractiveSession | None:
        """Get information about a session.

        Args:
            session_id: The session identifier.

        Returns:
            The session info, or None if not found.
        """
        ...

    async def list_sessions(self) -> list[InteractiveSession]:
        """List all active interactive sessions.

        Returns:
            List of active sessions (excludes already cleaned up terminated sessions).
        """
        ...
