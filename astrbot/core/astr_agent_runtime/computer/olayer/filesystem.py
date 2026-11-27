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

    async def read_file(
        self,
        path: str,
        encoding: str = "utf-8",
        offset: int | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Read file content by line window"""
        ...

    async def search_files(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        after_context: int | None = None,
        before_context: int | None = None,
        *,
        max_results: int | None = None,
        max_output_bytes: int | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Search file contents with optional execution and output bounds.

        Args:
            pattern: Regular expression to search for.
            path: File or directory to search.
            glob: Optional file glob filter.
            after_context: Number of trailing context lines.
            before_context: Number of leading context lines.
            max_results: Maximum output groups, separated by ``--`` with context.
            max_output_bytes: Maximum UTF-8 bytes in returned content.
            timeout: Maximum search duration in seconds.

        Returns:
            Search status and content, with ``truncated`` when a bound is reached.
        """
        ...

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        encoding: str = "utf-8",
    ) -> dict[str, Any]:
        """Edit file content by string replacement"""
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
