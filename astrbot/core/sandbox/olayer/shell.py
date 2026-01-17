"""
Shell component
"""

from typing import Any, Protocol


class ShellComponent(Protocol):
    """Shell operations component"""

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 30,
        shell: bool = True,
        background: bool = False,
    ) -> dict[str, Any]:
        """Execute shell command"""
        ...
