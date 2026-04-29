"""Unit tests for astrbot.core.utils.storage_cleaner.

Uses tmp_path for filesystem-level assertions.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from astrbot.core.utils.storage_cleaner import StorageCleaner

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_file(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def _assert_exists(path: Path, expected_size: int | None = None) -> None:
    assert path.exists(), f"Expected {path} to exist"
    if expected_size is not None:
        assert path.stat().st_size == expected_size


def _assert_missing(path: Path) -> None:
    assert not path.exists(), f"Expected {path} to be removed"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStorageCleanerStatus:
    def test_get_status_reports_logs_and_cache(self, tmp_path: Path):
        data = tmp_path / "data"
        temp = data / "temp"
        logs = data / "logs"

        _make_file(temp / "x.wav", 100)
        _make_file(data / "plugins.json", 50)
        _make_file(logs / "astrbot.log", 200)
        _make_file(logs / "astrbot.2026-01-01.log", 80)

        cleaner = StorageCleaner(
            {"log_file_enable": True, "log_file_path": "logs/astrbot.log"},
            data_dir=data,
            temp_dir=temp,
        )

        status = cleaner.get_status()

        assert status["logs"]["size_bytes"] == 280  # 200 + 80
        assert status["logs"]["file_count"] == 2
        assert status["cache"]["size_bytes"] == 150  # 100 + 50
        assert status["cache"]["file_count"] == 2
        assert status["total_bytes"] == 430

    def test_get_status_when_dirs_missing(self, tmp_path: Path):
        data = tmp_path / "data"
        cleaner = StorageCleaner(
            {"log_file_enable": False},
            data_dir=data,
            temp_dir=data / "temp",
        )
        status = cleaner.get_status()
        assert status["logs"]["size_bytes"] == 0
        assert status["logs"]["file_count"] == 0
        assert status["cache"]["size_bytes"] == 0
        assert status["total_bytes"] == 0

    def test_get_status_includes_cache_extra_files(self, tmp_path: Path):
        data = tmp_path / "data"
        temp = data / "temp"
        logs = data / "logs"
        _make_file(logs / "astrbot.log", 10)
        _make_file(temp / "a.bin", 10)

        _make_file(data / "plugins_custom_foo.json", 20)
        _make_file(data / "sandbox_skills_cache.json", 30)

        cleaner = StorageCleaner(
            {"log_file_enable": True},
            data_dir=data,
            temp_dir=temp,
        )
        status = cleaner.get_status()
        assert status["cache"]["file_count"] >= 3  # temp + custom* + sandbox
        assert status["cache"]["size_bytes"] >= 60


class TestStorageCleanerCleanup:
    def test_cleanup_all_removes_logs_and_cache(self, tmp_path: Path):
        data = tmp_path / "data"
        temp = data / "temp"
        logs = data / "logs"

        active_log = logs / "astrbot.log"
        rotated_log = logs / "astrbot.2026-03-01.log"
        _make_file(active_log, 100)
        _make_file(rotated_log, 50)
        _make_file(temp / "t.bin", 200)

        cleaner = StorageCleaner(
            {"log_file_enable": True, "log_file_path": "logs/astrbot.log"},
            data_dir=data,
            temp_dir=temp,
        )
        result = cleaner.cleanup("all")

        # Active log → truncated
        _assert_exists(active_log, 0)
        # Rotated log → deleted
        _assert_missing(rotated_log)
        # Temp cache → deleted
        _assert_missing(temp / "t.bin")

        assert result["removed_bytes"] == 350
        assert result["processed_files"] == 3
        assert result["deleted_files"] == 2
        assert result["truncated_files"] == 1

    def test_cleanup_logs_target_only(self, tmp_path: Path):
        data = tmp_path / "data"
        logs = data / "logs"
        temp = data / "temp"

        _make_file(logs / "astrbot.log", 80)
        _make_file(temp / "c.bin", 999)

        cleaner = StorageCleaner(
            {"log_file_enable": True, "log_file_path": "logs/astrbot.log"},
            data_dir=data,
            temp_dir=temp,
        )
        result = cleaner.cleanup("logs")

        _assert_exists(logs / "astrbot.log", 0)
        # temp should be untouched
        _assert_exists(temp / "c.bin", 999)
        assert result["removed_bytes"] == 80

    def test_cleanup_cache_target_only(self, tmp_path: Path):
        data = tmp_path / "data"
        logs = data / "logs"
        temp = data / "temp"

        _make_file(logs / "astrbot.log", 80)
        _make_file(temp / "c.bin", 200)

        cleaner = StorageCleaner(
            {"log_file_enable": True, "log_file_path": "logs/astrbot.log"},
            data_dir=data,
            temp_dir=temp,
        )
        result = cleaner.cleanup("cache")

        _assert_exists(logs / "astrbot.log", 80)  # untouched
        _assert_missing(temp / "c.bin")
        assert result["removed_bytes"] == 200

    def test_cleanup_invalid_target_raises(self, tmp_path: Path):
        cleaner = StorageCleaner({}, data_dir=tmp_path, temp_dir=tmp_path)
        with pytest.raises(ValueError, match="Unsupported cleanup target"):
            cleaner.cleanup("invalid")

    def test_cleanup_with_no_config(self, tmp_path: Path):
        """All config options off; no active log files, so everything gets deleted."""
        data = tmp_path / "data"
        _make_file(data / "logs" / "astrbot.log", 50)

        cleaner = StorageCleaner(
            {"log_file_enable": False},
            data_dir=data,
            temp_dir=data / "temp",
        )
        result = cleaner.cleanup("logs")
        # With log_file_enable=False, astrbot.log is NOT in active_log_files,
        # so it gets deleted, not truncated.
        _assert_missing(data / "logs" / "astrbot.log")
        assert result["deleted_files"] == 1
        assert result["truncated_files"] == 0


class TestStorageCleanerEdgeCases:
    def test_cleanup_removes_empty_temp_dirs(self, tmp_path: Path):
        data = tmp_path / "data"
        temp = data / "temp"
        nested = temp / "sub" / "nested"
        _make_file(nested / "f.bin", 100)

        cleaner = StorageCleaner(
            {},
            data_dir=data,
            temp_dir=temp,
        )
        cleaner.cleanup("cache")

        assert not nested.exists()
        assert temp.exists()  # root temp should be recreated by _cleanup_target

    def test_cleanup_skips_inexistent_file(self, tmp_path: Path):
        data = tmp_path / "data"
        cleaner = StorageCleaner(
            {"log_file_enable": False},
            data_dir=data,
            temp_dir=data / "temp",
        )
        # No files at all – should not crash.
        result = cleaner.cleanup("all")
        assert result["failed_files"] == 0

    def test_cleanup_handles_stat_os_error(self, tmp_path: Path):
        data = tmp_path / "data"
        logs = data / "logs"
        _make_file(logs / "astrbot.log", 100)

        cleaner = StorageCleaner(
            {"log_file_enable": True, "log_file_path": "logs/astrbot.log"},
            data_dir=data,
            temp_dir=data / "temp",
        )

        original_stat = (logs / "astrbot.log").stat

        def _broken_stat():
            raise OSError(13, "Permission denied")

        (logs / "astrbot.log").stat = _broken_stat  # type: ignore[method-assign]

        result = cleaner.cleanup("logs")
        assert result["failed_files"] == 1

        (logs / "astrbot.log").stat = original_stat

    def test_cleanup_handles_unlink_os_error(self, tmp_path: Path):
        data = tmp_path / "data"
        logs = data / "logs"
        _make_file(logs / "astrbot.log", 100)

        cleaner = StorageCleaner(
            {"log_file_enable": False},
            data_dir=data,
            temp_dir=data / "temp",
        )

        original_unlink = (logs / "astrbot.log").unlink

        def _broken_unlink():
            raise OSError(13, "Permission denied")

        (logs / "astrbot.log").unlink = _broken_unlink  # type: ignore[method-assign]

        result = cleaner.cleanup("logs")
        assert result["failed_files"] == 1

        (logs / "astrbot.log").unlink = original_unlink
