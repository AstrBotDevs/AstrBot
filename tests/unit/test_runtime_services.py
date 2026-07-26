"""Tests for explicit runtime-service construction."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import astrbot.core.runtime_services as runtime_services


def test_factory_does_not_start_preferences_before_other_resources(
    monkeypatch, tmp_path
):
    """A failed factory call must not leak SharedPreferences' scheduler."""

    config = MagicMock()
    config.get.return_value = ""
    preferences_factory = MagicMock()

    class BrokenToolImageCache:
        CACHE_DIR_NAME = "tool_images"

        def __init__(self, _cache_dir) -> None:
            raise OSError("cache directory is unavailable")

    monkeypatch.setattr(runtime_services, "AstrBotConfig", lambda: config)
    monkeypatch.setattr(runtime_services, "SQLiteDatabase", MagicMock())
    monkeypatch.setattr(
        runtime_services.LogManager,
        "GetLogger",
        MagicMock(),
    )
    monkeypatch.setattr(
        runtime_services.LogManager,
        "configure_logger",
        MagicMock(),
    )
    monkeypatch.setattr(
        runtime_services.LogManager,
        "configure_trace_logger",
        MagicMock(),
    )
    monkeypatch.setattr(runtime_services, "ToolImageCache", BrokenToolImageCache)
    monkeypatch.setattr(runtime_services, "SharedPreferences", preferences_factory)
    monkeypatch.setattr(
        runtime_services, "get_astrbot_temp_path", lambda: str(tmp_path)
    )

    with pytest.raises(OSError, match="cache directory is unavailable"):
        runtime_services.create_runtime_services()

    preferences_factory.assert_not_called()


def test_factory_initializes_astrbot_logger(tmp_path: Path) -> None:
    """The factory routes normal AstrBot logs to the process console."""
    root = tmp_path / "runtime-root"
    environment = {
        **os.environ,
        "ASTRBOT_ROOT": str(root),
    }
    code = """
from astrbot import logger

import astrbot.core.runtime_services as runtime_services


class StopAfterLoggerSetup:
    CACHE_DIR_NAME = "tool_images"

    def __init__(self, _cache_dir) -> None:
        raise RuntimeError("stop after logger setup")


runtime_services.AstrBotConfig = lambda: {
    "log_level": "INFO",
    "log_file_enable": False,
    "trace_log_enable": False,
}
runtime_services.SQLiteDatabase = lambda _path: object()
runtime_services.WebChatQueueManager = lambda: object()
runtime_services.ComputerRuntime = lambda: object()
runtime_services.ToolImageCache = StopAfterLoggerSetup

try:
    runtime_services.create_runtime_services()
except RuntimeError as exc:
    assert str(exc) == "stop after logger setup"
else:
    raise AssertionError("factory unexpectedly completed")

logger.info("runtime-service-log-is-visible")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "runtime-service-log-is-visible" in result.stdout
