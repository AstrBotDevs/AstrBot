"""Tests for untrusted ZIP validation."""

from __future__ import annotations

import io
import zipfile

import pytest

from astrbot.core.utils.archive_limits import ZipArchivePolicy, validate_zip_archive


POLICY = ZipArchivePolicy(
    max_entries=2,
    max_total_bytes=16,
    max_file_bytes=12,
    max_compression_ratio=20,
)


def _archive(entries: dict[str, bytes]) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


def test_safe_archive_is_accepted() -> None:
    with _archive({"plugin/main.py": b"content"}) as archive:
        validate_zip_archive(archive, policy=POLICY)


def test_parent_path_is_rejected() -> None:
    with _archive({"../escape": b"x"}) as archive:
        with pytest.raises(ValueError, match="Unsafe"):
            validate_zip_archive(archive, policy=POLICY)


def test_entry_count_is_bounded() -> None:
    with _archive({"a": b"1", "b": b"2", "c": b"3"}) as archive:
        with pytest.raises(ValueError, match="too many"):
            validate_zip_archive(archive, policy=POLICY)


def test_single_and_total_size_are_bounded() -> None:
    with _archive({"a": b"x" * 13}) as archive:
        with pytest.raises(ValueError, match="member exceeds"):
            validate_zip_archive(archive, policy=POLICY)
    with _archive({"a": b"x" * 9, "b": b"y" * 9}) as archive:
        with pytest.raises(ValueError, match="expanded byte"):
            validate_zip_archive(archive, policy=POLICY)
