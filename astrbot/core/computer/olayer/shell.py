"""
Shell component
"""

from collections.abc import AsyncIterator
from typing import Any, Protocol


class ShellComponent(Protocol):
    """Shell operations component"""

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 300,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        """Execute shell command"""
        ...

    async def exec_stream(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 300,
        shell: bool = True,
        background: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute shell command and stream stdout/stderr events."""
        ...
