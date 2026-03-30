from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from astrbot.core.computer.olayer import (
    BrowserComponent,
    FileSystemComponent,
    PythonComponent,
    ShellComponent,
)

if TYPE_CHECKING:
    from astrbot.core.agent.tool import FunctionTool


class ComputerBooter(abc.ABC):
    @property
    @abc.abstractmethod
    def fs(self) -> FileSystemComponent:
        raise NotImplementedError("Subclass must implement fs property")

    @property
    @abc.abstractmethod
    def python(self) -> PythonComponent:
        raise NotImplementedError("Subclass must implement python property")

    @property
    @abc.abstractmethod
    def shell(self) -> ShellComponent:
        raise NotImplementedError("Subclass must implement shell property")

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

    @abc.abstractmethod
    async def boot(self, session_id: str) -> None:
        raise NotImplementedError("Subclass must implement boot method")

    @abc.abstractmethod
    async def shutdown(self) -> None:
        raise NotImplementedError("Subclass must implement shutdown method")

    async def upload_file(self, path: str, file_name: str) -> dict:
        """Upload file to the computer.

        Should return a dict with `success` (bool) and `file_path` (str) keys.
        """
        raise NotImplementedError("Subclass must implement upload_file method")

    async def download_file(self, remote_path: str, local_path: str) -> None:
        """Download file from the computer."""
        raise NotImplementedError("Subclass must implement download_file method")

    @abc.abstractmethod
    async def available(self) -> bool:
        """Check if the computer is available."""
        raise NotImplementedError("Subclass must implement available method")

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
