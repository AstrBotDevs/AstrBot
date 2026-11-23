"""Text replacement shared by filesystem adapters without native edit support."""

from typing import Any

from astrbot.core.astr_agent_runtime.computer.olayer.filesystem import (
    FileSystemComponent,
)


async def edit_file_by_replacement(
    filesystem: FileSystemComponent,
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    encoding: str = "utf-8",
    *,
    coerce_content: bool = True,
    include_missing_path: bool = True,
) -> dict[str, Any]:
    """Read, replace, and write while preserving adapter error envelopes.

    The CUA SDK historically requires string content and omits the path for a
    missing match. Other adapters normalize content and include that path.
    """
    read_result = await filesystem.read_file(path, encoding=encoding)
    if not read_result.get("success"):
        return read_result
    content = read_result.get("content", "")
    if coerce_content:
        content = str(content)
    occurrences = content.count(old_string)
    if occurrences == 0:
        result = {
            "success": False,
            "error": "old string not found in file",
            "replacements": 0,
        }
        if include_missing_path:
            result["path"] = path
        return result
    updated = content.replace(old_string, new_string, -1 if replace_all else 1)
    write_result = await filesystem.write_file(path, updated, encoding=encoding)
    if not write_result.get("success"):
        return write_result
    return {
        "success": True,
        "path": path,
        "replacements": occurrences if replace_all else 1,
    }
