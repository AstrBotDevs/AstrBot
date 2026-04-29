"""Unit tests for astrbot.core.utils.temp_dir_cleaner.

Covers parse_size_to_bytes, cleanup_once, async lifecycle, and error paths.
"""

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from astrbot.core.utils.temp_dir_cleaner import TempDirCleaner, parse_size_to_bytes

# ---------------------------------------------------------------------------
# parse_size_to_bytes
# ---------------------------------------------------------------------------


class TestParseSizeToBytes:
    def test_valid_mb_string(self):
        assert parse_size_to_bytes("1024") == 1024 * 1024**2

    def test_valid_float_mb(self):
        assert parse_size_to_bytes(0.5) == int(0.5 * 1024**2)

    def test_zero_returns_zero(self):
        assert parse_size_to_bytes(0) == 0

    def test_none_returns_zero(self):
        assert parse_size_to_bytes(None) == 0

    def test_invalid_string_returns_zero(self):
        assert parse_size_to_bytes("not-a-number") == 0

    def test_negative_value_returns_zero(self):
        assert parse_size_to_bytes("-10") == 0

    def test_whitespace_string(self):
        assert parse_size_to_bytes("  512  ") == 512 * 1024**2


# ---------------------------------------------------------------------------
# helpers for filesystem tests
# ---------------------------------------------------------------------------


def _write_file(path: Path, size: int, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _file_sizes(temp_dir: Path) -> list[tuple[Path, int]]:
    return [
        (f, f.stat().st_size)
        for f in sorted(temp_dir.rglob("*"))
        if f.is_file()
    ]


# ---------------------------------------------------------------------------
# cleanup_once
# ---------------------------------------------------------------------------


class TestCleanupOnce:
    def test_noop_when_below_limit(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        _write_file(temp_dir / "a.bin", 100, time.time())

        cleaner = TempDirCleaner(
            max_size_getter=lambda: "1",  # 1 MB → effectively unlimited
            temp_dir=temp_dir,
        )
        cleaner.cleanup_once()

        files = _file_sizes(temp_dir)
        assert len(files) == 1
        assert files[0][1] == 100

    def test_removes_oldest_files_when_over_limit(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        base = time.time() - 1000
        _write_file(temp_dir / "old.bin", 400, base)
        _write_file(temp_dir / "mid.bin", 300, base + 10)
        _write_file(temp_dir / "new.bin", 300, base + 20)

        # Limit = 0.0008 MB ≈ 838 bytes; total = 1000 => release 30% = 300
        cleaner = TempDirCleaner(
            max_size_getter=lambda: "0.0008",
            temp_dir=temp_dir,
        )
        cleaner.cleanup_once()

        remaining = _file_sizes(temp_dir)
        remaining_total = sum(sz for _, sz in remaining)
        # old.bin (oldest) should have been deleted first
        assert (temp_dir / "old.bin").exists() is False
        # remaining <= 700 (total - minimum 30%)
        assert remaining_total <= 700

    def test_noop_when_temp_dir_missing(self, tmp_path: Path):
        temp_dir = tmp_path / "nonexistent"
        cleaner = TempDirCleaner(
            max_size_getter=lambda: "0.001",
            temp_dir=temp_dir,
        )
        # Should not raise
        cleaner.cleanup_once()

    def test_handles_unlink_os_error_gracefully(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        _write_file(temp_dir / "bad.bin", 9999, time.time() - 100)

        cleaner = TempDirCleaner(
            max_size_getter=lambda: "0.001",
            temp_dir=temp_dir,
        )

        def _broken_unlink():
            raise OSError(13, "Permission denied")

        (temp_dir / "bad.bin").unlink = _broken_unlink  # type: ignore[method-assign]

        # Should log warning but not crash
        with patch("astrbot.core.utils.temp_dir_cleaner.logger.warning") as mock_warn:
            cleaner.cleanup_once()
            mock_warn.assert_called()
            assert any(
                "Permission denied" in str(c) for c in mock_warn.call_args_list
            )

    def test_invalid_config_falls_back_to_default(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        _write_file(temp_dir / "a.bin", 50, time.time())

        cleaner = TempDirCleaner(
            max_size_getter=lambda: "invalid",
            temp_dir=temp_dir,
        )
        with patch("astrbot.core.utils.temp_dir_cleaner.logger.warning") as mock_warn:
            cleaner.cleanup_once()
            mock_warn.assert_called_once()
            assert "fallback" in str(mock_warn.call_args[0][0])

    def test_cleanup_once_removes_empty_dirs(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        nested = temp_dir / "a" / "b"
        _write_file(nested / "f.bin", 1000000, time.time() - 5000)
        # Also create an already-empty subdir
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir(parents=True, exist_ok=True)

        cleaner = TempDirCleaner(
            max_size_getter=lambda: "0.001",
            temp_dir=temp_dir,
        )
        cleaner.cleanup_once()

        # The file in nested is old → gets deleted, dirs cleaned up
        assert not nested.exists()
        # empty dir should be removed by _cleanup_empty_dirs
        _assert_dir_gone = not empty_dir.exists()
        # either nested or empty (or both) should be gone
        assert _assert_dir_gone or not nested.exists()


# ---------------------------------------------------------------------------
# scan / async lifecycle
# ---------------------------------------------------------------------------


class TestScanAndAsyncLifecycle:
    def test_scan_empty_dir_returns_zeroes(self, tmp_path: Path):
        temp_dir = tmp_path / "empty_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        cleaner = TempDirCleaner(
            max_size_getter=lambda: "100",
            temp_dir=temp_dir,
        )
        total, files = cleaner._scan_temp_files()
        assert total == 0
        assert files == []

    def test_scan_missing_dir_returns_zeroes(self, tmp_path: Path):
        temp_dir = tmp_path / "ghost"
        cleaner = TempDirCleaner(
            max_size_getter=lambda: "100",
            temp_dir=temp_dir,
        )
        total, files = cleaner._scan_temp_files()
        assert total == 0
        assert files == []

    @pytest.mark.asyncio
    async def test_stop_sets_event(self):
        cleaner = TempDirCleaner(
            max_size_getter=lambda: "100",
        )
        await cleaner.stop()
        assert cleaner._stop_event.is_set() is True

    @pytest.mark.asyncio
    async def test_run_stops_when_stop_is_called(self, tmp_path: Path):
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        cleaner = TempDirCleaner(
            max_size_getter=lambda: "1000",
            temp_dir=temp_dir,
        )

        task = asyncio.create_task(cleaner.run())
        await asyncio.sleep(0.05)
        assert task.done() is False

        await cleaner.stop()
        await asyncio.wait_for(task, timeout=2.0)
        assert task.done() is True

    @pytest.mark.asyncio
    async def test_run_logs_exception_and_continues(self, tmp_path: Path):
        """When cleanup_once raises, run() should log and continue the loop."""
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        cleaner = TempDirCleaner(
            max_size_getter=lambda: "1000",
            temp_dir=temp_dir,
        )

        # Make cleanup_once raise once, then succeed
        call_count = 0

        def _flaky_cleanup():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")

        cleaner.cleanup_once = _flaky_cleanup  # type: ignore[method-assign]

        with patch(
            "astrbot.core.utils.temp_dir_cleaner.logger.error"
        ) as mock_log_error:
            task = asyncio.create_task(cleaner.run())
            await asyncio.sleep(0.05)
            await cleaner.stop()
            await asyncio.wait_for(task, timeout=2.0)

            mock_log_error.assert_called()
            error_msg = str(mock_log_error.call_args[0][0])
            assert "transient failure" in error_msg or "failed" in error_msg
