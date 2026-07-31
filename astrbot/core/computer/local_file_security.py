"""Race-resistant file opening for restricted Local computer tools."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import Literal


def open_file_in_allowed_roots(
    path: str,
    allowed_roots: tuple[Path, ...],
    *,
    access: Literal["read", "write", "edit"],
    create_parents: bool = False,
) -> int:
    """Open a regular file without following attacker-controlled path links.

    Args:
        path: Absolute normalized file path selected by the caller.
        allowed_roots: Trusted directories that may contain the file.
        access: Whether the descriptor is used for reading, writing, or editing.
        create_parents: Whether missing parent directories and the final file may
            be created.

    Returns:
        An open file descriptor owned by the caller.

    Raises:
        FileNotFoundError: If a required path component does not exist.
        IsADirectoryError: If the final path is a directory.
        PermissionError: If the path leaves the allowed roots, contains a symbolic
            link, is not a regular file, or aliases a multiply linked file.
        RuntimeError: If descriptor-relative no-follow access is unavailable.
        ValueError: If an unsupported access mode is requested.
    """
    if (
        os.name == "nt"
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "pread")
        or os.open not in os.supports_dir_fd
        or os.mkdir not in os.supports_dir_fd
    ):
        raise RuntimeError(
            "Race-resistant restricted file access is unavailable on this platform."
        )

    candidate = Path(path)
    if not candidate.is_absolute():
        raise PermissionError(f"Restricted file path must be absolute: {path}.")

    root_matches: list[tuple[Path, Path]] = []
    for root in allowed_roots:
        try:
            root_matches.append((root, candidate.relative_to(root)))
        except ValueError:
            continue
    if not root_matches:
        raise PermissionError(
            f"Access denied: path is outside restricted roots: {path}."
        )

    root, relative_path = max(root_matches, key=lambda item: len(item[0].parts))
    parts = relative_path.parts
    if not parts:
        raise IsADirectoryError(path)
    if any(part in {"", ".", ".."} for part in parts):
        raise PermissionError(f"Access denied: unsafe restricted path: {path}.")

    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        directory_fd = os.open(root, directory_flags)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise PermissionError(
                f"Access denied: restricted root changed or is a symbolic link: {root}."
            ) from exc
        raise

    try:
        for component in parts[:-1]:
            try:
                next_directory_fd = os.open(
                    component,
                    directory_flags,
                    dir_fd=directory_fd,
                )
            except FileNotFoundError:
                if not create_parents:
                    raise
                try:
                    os.mkdir(component, mode=0o755, dir_fd=directory_fd)
                except FileExistsError:
                    pass
                try:
                    next_directory_fd = os.open(
                        component,
                        directory_flags,
                        dir_fd=directory_fd,
                    )
                except OSError as exc:
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                        raise PermissionError(
                            "Access denied: restricted path changed or contains a "
                            f"symbolic link: {path}."
                        ) from exc
                    raise
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise PermissionError(
                        "Access denied: restricted path changed or contains a "
                        f"symbolic link: {path}."
                    ) from exc
                raise
            os.close(directory_fd)
            directory_fd = next_directory_fd

        if access == "read":
            file_flags = os.O_RDONLY
        elif access == "write":
            file_flags = os.O_WRONLY
        elif access == "edit":
            file_flags = os.O_RDWR
        else:
            raise ValueError(f"Unsupported restricted file access mode: {access}.")
        file_flags |= (
            os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        )

        final_name = parts[-1]
        try:
            file_fd = os.open(final_name, file_flags, dir_fd=directory_fd)
        except FileNotFoundError:
            if not create_parents:
                raise
            try:
                file_fd = os.open(
                    final_name,
                    file_flags | os.O_CREAT | os.O_EXCL,
                    0o666,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                try:
                    file_fd = os.open(final_name, file_flags, dir_fd=directory_fd)
                except OSError as exc:
                    if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                        raise PermissionError(
                            "Access denied: restricted path changed or contains a "
                            f"symbolic link: {path}."
                        ) from exc
                    raise
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise PermissionError(
                    "Access denied: restricted path changed or contains a "
                    f"symbolic link: {path}."
                ) from exc
            raise

        try:
            file_stat = os.fstat(file_fd)
        except OSError:
            os.close(file_fd)
            raise
        if not stat.S_ISREG(file_stat.st_mode):
            os.close(file_fd)
            if stat.S_ISDIR(file_stat.st_mode):
                raise IsADirectoryError(path)
            raise PermissionError(
                f"Access denied: restricted path is not a regular file: {path}."
            )
        if file_stat.st_nlink > 1:
            os.close(file_fd)
            raise PermissionError(
                "Access denied: file has multiple hard links and may alias content "
                f"outside allowed directories. Link count: {file_stat.st_nlink}. "
                f"Blocked path: {path}."
            )
        return file_fd
    finally:
        os.close(directory_fd)
