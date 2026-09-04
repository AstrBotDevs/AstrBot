"""Resource and path validation for untrusted ZIP archives."""

from __future__ import annotations

import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class ZipArchivePolicy:
    """Limits applied before extracting an untrusted ZIP archive.

    Args:
        max_entries: Maximum number of archive members.
        max_total_bytes: Maximum total uncompressed bytes.
        max_file_bytes: Maximum uncompressed bytes for one member.
        max_compression_ratio: Maximum uncompressed/compressed ratio.
    """

    max_entries: int
    max_total_bytes: int
    max_file_bytes: int
    max_compression_ratio: float


PLUGIN_ARCHIVE_POLICY = ZipArchivePolicy(
    max_entries=10_000,
    max_total_bytes=512 * 1024 * 1024,
    max_file_bytes=128 * 1024 * 1024,
    max_compression_ratio=100,
)
BACKUP_ARCHIVE_POLICY = ZipArchivePolicy(
    max_entries=10_000,
    max_total_bytes=4 * 1024 * 1024 * 1024,
    max_file_bytes=1024 * 1024 * 1024,
    max_compression_ratio=200,
)


def validate_zip_archive(
    archive: zipfile.ZipFile,
    *,
    policy: ZipArchivePolicy,
) -> None:
    """Validate paths and expanded sizes before archive extraction.

    Args:
        archive: Open ZIP archive.
        policy: Entry and expansion limits.

    Raises:
        ValueError: If a member is unsafe or exceeds a resource limit.
    """
    entries = archive.infolist()
    if len(entries) > policy.max_entries:
        raise ValueError("ZIP archive contains too many entries")
    total_bytes = 0
    for member in entries:
        normalized = member.filename.replace("\\", "/")
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe ZIP archive path: {member.filename}")
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError(f"ZIP archive symlinks are not allowed: {member.filename}")
        if member.is_dir():
            continue
        if member.file_size > policy.max_file_bytes:
            raise ValueError(f"ZIP member exceeds the byte limit: {member.filename}")
        total_bytes += member.file_size
        if total_bytes > policy.max_total_bytes:
            raise ValueError("ZIP archive exceeds the expanded byte limit")
        ratio = member.file_size / max(member.compress_size, 1)
        if ratio > policy.max_compression_ratio:
            raise ValueError(
                f"ZIP member exceeds the compression-ratio limit: {member.filename}"
            )
