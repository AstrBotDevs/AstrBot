from __future__ import annotations

from typing import TYPE_CHECKING

from ..olayer import (
    BrowserComponent,
    FileSystemComponent,
    PythonComponent,
    ShellComponent,
)

if TYPE_CHECKING:
    from astrbot.core.agent.tool import FunctionTool


class ComputerBooter:
    @property
    def fs(self) -> FileSystemComponent: ...

    @property
    def python(self) -> PythonComponent: ...

    @property
    def shell(self) -> ShellComponent: ...

    @property
    def capabilities(self) -> tuple[str, ...] | None:
        """Sandbox capabilities (e.g. ('python', 'shell', 'filesystem', 'browser')).

        Returns None if the booter doesn't support capability introspection
        (backward-compatible default).  Subclasses override after boot.
        """
        return None

    @property
    def browser(self) -> BrowserComponent | None:
        return None

    async def boot(self, session_id: str) -> None: ...

    async def shutdown(self) -> None: ...

    async def upload_file(self, path: str, file_name: str) -> dict:
        """Upload file to the computer.

        Should return a dict with `success` (bool) and `file_path` (str) keys.
        """
        ...

    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Download file from the computer."""
        ...

    async def available(self) -> bool:
        """Check if the computer is available."""
        ...

    @classmethod
    def get_default_tools(cls) -> list[FunctionTool]:
        """Conservative full tool list (no instance needed, pre-boot)."""
        return []

    def get_tools(self) -> list[FunctionTool]:
        """Capability-filtered tool list (post-boot).
        Defaults to get_default_tools()."""
        return self.__class__.get_default_tools()

    @classmethod
    def get_system_prompt_parts(cls) -> list[str]:
        """Booter-specific system prompt fragments (static text, no instance needed)."""
        return []
