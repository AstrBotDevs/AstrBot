"""
File system component
"""

from typing import Any, Protocol


class FileSystemComponent(Protocol):
    async def create_file(
        self, path: str, content: str = "", mode: int = 0o644
    ) -> dict[str, Any]:
        """Create a file with the specified content"""
        ...

    async def read_file(self, path: str, encoding: str = "utf-8") -> dict[str, Any]:
        """Read file content"""
        ...

    async def write_file(
        self, path: str, content: str, mode: str = "w", encoding: str = "utf-8"
    ) -> dict[str, Any]:
        """Write content to file"""
        ...

    async def delete_file(self, path: str) -> dict[str, Any]:
        """Delete file or directory"""
        ...

    async def list_dir(
        self, path: str = ".", show_hidden: bool = False
    ) -> dict[str, Any]:
        """List directory contents"""
        ...
