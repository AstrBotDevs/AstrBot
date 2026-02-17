import os
import time
from pathlib import Path

from astrbot.core.utils.temp_dir_cleaner import TempDirCleaner, parse_size_to_bytes


def test_parse_size_to_bytes():
    assert parse_size_to_bytes("1024") == 1024 * 1024**2
    assert parse_size_to_bytes(2048) == 2048 * 1024**2
    assert parse_size_to_bytes("0.5") == int(0.5 * 1024**2)
    assert parse_size_to_bytes(0) == 0
    assert parse_size_to_bytes("invalid") == 0


def _write_file(path: Path, size: int, mtime: float) -> None:
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))


def test_cleanup_once_releases_30_percent_and_prefers_old_files(tmp_path):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    base_time = time.time() - 1000
    file_old = temp_dir / "old.bin"
    file_mid = temp_dir / "mid.bin"
    file_new = temp_dir / "new.bin"
    _write_file(file_old, 400, base_time)
    _write_file(file_mid, 300, base_time + 10)
    _write_file(file_new, 300, base_time + 20)

    cleaner = TempDirCleaner(max_size_getter=lambda: "0.0008", temp_dir=temp_dir)
    cleaner.cleanup_once()

    remaining_size = sum(f.stat().st_size for f in temp_dir.rglob("*") if f.is_file())
    assert remaining_size <= 600
    assert not file_old.exists()
    assert file_mid.exists()
    assert file_new.exists()


def test_cleanup_once_noop_when_below_limit(tmp_path):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / "a.bin"
    _write_file(file_path, 100, time.time())

    cleaner = TempDirCleaner(max_size_getter=lambda: "1", temp_dir=temp_dir)
    cleaner.cleanup_once()

    assert file_path.exists()
