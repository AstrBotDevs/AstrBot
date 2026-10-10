"""Handle-based restricted file access without Windows reparse-point traversal."""

import msvcrt
import os
from pathlib import Path
from typing import Literal

import win32con
import win32file


def open_windows_file_in_allowed_roots(
    path: str,
    allowed_roots: tuple[Path, ...],
    *,
    access: Literal["read", "write", "edit"],
    create_parents: bool = False,
) -> int:
    """Pin every ancestor against replacement before opening the final file.

    Args:
        path: Absolute path already normalized by the file tool.
        allowed_roots: Trusted roots for this operation.
        access: Read, write, or edit access, without implicit truncation.
        create_parents: Whether missing directories and the file may be created.

    Returns:
        A binary CRT descriptor owned by the caller.

    Raises:
        PermissionError: On an unauthorized path, reparse point, or hard link.
        OSError: If Windows rejects the file access.
        ValueError: If the access mode is invalid.
    """
    candidate = Path(path)
    matches = [root for root in allowed_roots if candidate.is_relative_to(root)]
    if (
        not candidate.is_absolute()
        or not matches
        or candidate.drive.startswith("\\\\")
        or any(part != part.rstrip(" .") or ":" in part for part in candidate.parts[1:])
    ):
        raise PermissionError(f"Path is outside supported local sandbox roots: {path}")
    root = max(matches, key=lambda p: len(p.parts))
    if candidate == root:
        raise IsADirectoryError(path)
    desired = {
        "read": win32con.GENERIC_READ,
        "write": win32con.GENERIC_WRITE,
        "edit": win32con.GENERIC_READ | win32con.GENERIC_WRITE,
    }
    if access not in desired:
        raise ValueError(f"Unsupported restricted access: {access}")
    pinned = []
    final = None
    current = Path(candidate.anchor)
    try:
        # Omitting FILE_SHARE_DELETE prevents renames/junction replacement while
        # descending. OPEN_REPARSE_POINT opens the link itself for inspection.
        for component in ("", *candidate.parts[1:-1]):
            current /= component
            if create_parents and current.is_relative_to(root):
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
            handle = win32file.CreateFile(
                str(current),
                0x80,  # FILE_READ_ATTRIBUTES
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
                None,
                win32con.OPEN_EXISTING,
                win32con.FILE_FLAG_BACKUP_SEMANTICS | 0x00200000,
                None,
            )
            pinned.append(handle)
            attributes = win32file.GetFileInformationByHandle(handle)[0]
            if (
                attributes & win32con.FILE_ATTRIBUTE_REPARSE_POINT
                or not attributes & win32con.FILE_ATTRIBUTE_DIRECTORY
            ):
                raise PermissionError(
                    f"Restricted path contains a reparse point: {current}"
                )
        final = win32file.CreateFile(
            str(candidate),
            desired[access],
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE,
            None,
            win32con.OPEN_ALWAYS if create_parents else win32con.OPEN_EXISTING,
            win32file.FILE_FLAG_OPEN_REPARSE_POINT
            | win32con.FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        info = win32file.GetFileInformationByHandle(final)
        if (
            info[0]
            & (
                win32con.FILE_ATTRIBUTE_REPARSE_POINT
                | win32con.FILE_ATTRIBUTE_DIRECTORY
            )
            or info[7] > 1
        ):
            raise PermissionError(
                f"Restricted file is a directory, reparse point, or hard link: {candidate}"
            )
        flags = {"read": os.O_RDONLY, "write": os.O_WRONLY, "edit": os.O_RDWR}[access]
        fd = msvcrt.open_osfhandle(int(final), flags | os.O_BINARY)
        final.Detach()
        final = None
        return fd
    finally:
        if final is not None:
            final.Close()
        for handle in reversed(pinned):
            handle.Close()
