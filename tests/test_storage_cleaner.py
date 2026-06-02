from pathlib import Path

from astrbot.core.utils.storage_cleaner import StorageCleaner


def _write_bytes(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_storage_cleaner_status_includes_logs_and_cache(tmp_path):
    data_dir = tmp_path / "data"
    temp_dir = data_dir / "temp"
    logs_dir = data_dir / "logs"

    _write_bytes(temp_dir / "audio" / "temp.wav", 128)
    _write_bytes(data_dir / "plugins.json", 64)
    _write_bytes(data_dir / "sandbox_skills_cache.json", 32)
    _write_bytes(logs_dir / "astrbot.log", 256)
    _write_bytes(logs_dir / "astrbot.2026-03-22.log", 128)

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

    assert status["logs"]["size_bytes"] == 384
    assert status["logs"]["file_count"] == 2
    assert status["cache"]["size_bytes"] == 224
    assert status["cache"]["file_count"] == 3
    assert status["total_bytes"] == 608


def test_storage_cleaner_cleanup_truncates_active_log_and_removes_cache(tmp_path):
    data_dir = tmp_path / "data"
    temp_dir = data_dir / "temp"
    logs_dir = data_dir / "logs"
    active_log = logs_dir / "astrbot.log"
    rotated_log = logs_dir / "astrbot.2026-03-22.log"
    trace_log = logs_dir / "astrbot.trace.log"
    temp_file = temp_dir / "nested" / "voice.wav"
    registry_cache = data_dir / "plugins_custom_abc.json"

    _write_bytes(active_log, 300)
    _write_bytes(rotated_log, 150)
    _write_bytes(trace_log, 90)
    _write_bytes(temp_file, 120)
    _write_bytes(registry_cache, 80)

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

    assert result["removed_bytes"] == 740
    assert result["processed_files"] == 5
    assert result["deleted_files"] == 3
    assert result["truncated_files"] == 2
    assert result["failed_files"] == 0
    assert active_log.exists()
    assert active_log.stat().st_size == 0
    assert trace_log.exists()
    assert trace_log.stat().st_size == 0
    assert not rotated_log.exists()
    assert not temp_file.exists()
    assert not registry_cache.exists()
    assert temp_dir.exists()
    assert not (temp_dir / "nested").exists()
    assert result["status"]["logs"]["size_bytes"] == 0
    assert result["status"]["cache"]["size_bytes"] == 0
