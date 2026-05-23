from pathlib import Path
from typing import Final

from astrbot.core.utils.storage_cleaner import StorageCleaner


def _write_bytes(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def _assert_file_size(path: Path, expected_size: int) -> None:
    assert path.exists(), f"Expected file {path} to exist"
    assert path.stat().st_size == expected_size, f"{path} size should be {expected_size}"


def _assert_not_exists(path: Path) -> None:
    assert not path.exists(), f"Expected file {path} to be removed"


def test_storage_cleaner_status_includes_logs_and_cache(tmp_path):
    # sizes used in this test
    TEMP_AUDIO_SIZE: Final[int] = 128
    PLUGINS_SIZE: Final[int] = 64
    SANDBOX_CACHE_SIZE: Final[int] = 32
    LOG_MAIN_SIZE: Final[int] = 256
    LOG_ROTATED_SIZE: Final[int] = 128

    data_dir = tmp_path / "data"
    temp_dir = data_dir / "temp"
    logs_dir = data_dir / "logs"

    _write_bytes(temp_dir / "audio" / "temp.wav", TEMP_AUDIO_SIZE)
    _write_bytes(data_dir / "plugins.json", PLUGINS_SIZE)
    _write_bytes(data_dir / "sandbox_skills_cache.json", SANDBOX_CACHE_SIZE)
    _write_bytes(logs_dir / "astrbot.log", LOG_MAIN_SIZE)
    _write_bytes(logs_dir / "astrbot.2026-03-22.log", LOG_ROTATED_SIZE)

    cleaner = StorageCleaner(
        {
            "log_file_enable": True,
            "log_file_path": "logs/astrbot.log",
            "trace_log_enable": False,
        },
        data_dir=data_dir,
        temp_dir=temp_dir,
    )

    status = cleaner.get_status()

    expected_logs = LOG_MAIN_SIZE + LOG_ROTATED_SIZE
    expected_cache = TEMP_AUDIO_SIZE + PLUGINS_SIZE + SANDBOX_CACHE_SIZE
    expected_total = expected_logs + expected_cache

    assert status["logs"]["size_bytes"] == expected_logs
    assert status["logs"]["file_count"] == 2
    assert status["cache"]["size_bytes"] == expected_cache
    assert status["cache"]["file_count"] == 3
    assert status["total_bytes"] == expected_total


def test_storage_cleaner_cleanup_truncates_active_log_and_removes_cache(tmp_path):
    # sizes used in this test
    ACTIVE_LOG_SIZE: Final[int] = 300
    ROTATED_LOG_SIZE: Final[int] = 150
    TRACE_LOG_SIZE: Final[int] = 90
    TEMP_FILE_SIZE: Final[int] = 120
    REGISTRY_CACHE_SIZE: Final[int] = 80

    data_dir = tmp_path / "data"
    temp_dir = data_dir / "temp"
    logs_dir = data_dir / "logs"
    active_log = logs_dir / "astrbot.log"
    rotated_log = logs_dir / "astrbot.2026-03-22.log"
    trace_log = logs_dir / "astrbot.trace.log"
    temp_file = temp_dir / "nested" / "voice.wav"
    registry_cache = data_dir / "plugins_custom_abc.json"

    _write_bytes(active_log, ACTIVE_LOG_SIZE)
    _write_bytes(rotated_log, ROTATED_LOG_SIZE)
    _write_bytes(trace_log, TRACE_LOG_SIZE)
    _write_bytes(temp_file, TEMP_FILE_SIZE)
    _write_bytes(registry_cache, REGISTRY_CACHE_SIZE)

    cleaner = StorageCleaner(
        {
            "log_file_enable": True,
            "log_file_path": "logs/astrbot.log",
            "trace_log_enable": True,
            "trace_log_path": "logs/astrbot.trace.log",
        },
        data_dir=data_dir,
        temp_dir=temp_dir,
    )

    result = cleaner.cleanup("all")

    expected_removed = (
        ACTIVE_LOG_SIZE + ROTATED_LOG_SIZE + TRACE_LOG_SIZE + TEMP_FILE_SIZE + REGISTRY_CACHE_SIZE
    )
    # sanity checks for counts that are implied by the inputs
    assert result["removed_bytes"] == expected_removed
    assert result["processed_files"] == 5
    assert result["deleted_files"] == 3
    assert result["truncated_files"] == 2
    assert result["failed_files"] == 0

    # file-system level assertions
    _assert_file_size(active_log, 0)
    _assert_file_size(trace_log, 0)
    _assert_not_exists(rotated_log)
    _assert_not_exists(temp_file)
    _assert_not_exists(registry_cache)
    assert temp_dir.exists()
    assert not (temp_dir / "nested").exists()

    # final status should reflect zeroed logs and cache
    assert result["status"]["logs"]["size_bytes"] == 0
    assert result["status"]["cache"]["size_bytes"] == 0
