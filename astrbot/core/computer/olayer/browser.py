"""
Browser automation component
"""

from typing import Any, Protocol


class BrowserComponent(Protocol):
    """Browser operations component"""

    async def exec(
        self,
        cmd: str,
        timeout: int = 30,
        description: str | None = None,
        tags: str | None = None,
        learn: bool = False,
        include_trace: bool = False,
    ) -> dict[str, Any]:
        """Execute a browser automation command"""
        ...

    async def exec_batch(
        self,
        commands: list[str],
        timeout: int = 60,
        stop_on_error: bool = True,
        description: str | None = None,
        tags: str | None = None,
        learn: bool = False,
        include_trace: bool = False,
    ) -> dict[str, Any]:
        """Execute a browser automation command batch"""
        ...

    async def run_skill(
        self,
        skill_key: str,
        timeout: int = 60,
        stop_on_error: bool = True,
        include_trace: bool = False,
        description: str | None = None,
        tags: str | None = None,
    ) -> dict[str, Any]:
        """Run a browser skill by skill key"""
        ...
