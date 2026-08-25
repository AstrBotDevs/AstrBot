"""Tests for catalog-owned plugin logger routing and preferences."""

import json
import logging
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

import astrbot.api as api
from astrbot.core.log import LogManager
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.plugin_catalog import PluginCatalog
from astrbot.core.star.star import StarMetadata


def _metadata(name: str, module_path: str) -> StarMetadata:
    return StarMetadata(
        name=name,
        module_path=module_path,
        root_dir_name=module_path.split(".")[-2],
    )


def test_live_catalog_routes_sdk_logger_and_unpublish_restores_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SDK module logging is routed only while its catalog owns the module."""
    package_name = "data.plugins.logger_plugin"
    module_name = f"{package_name}.helpers"
    package = ModuleType(package_name)
    module = ModuleType(module_name)
    monkeypatch.setitem(sys.modules, package_name, package)
    monkeypatch.setitem(sys.modules, module_name, module)
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", {})

    catalog = PluginCatalog(RuntimeCatalogs())
    metadata = _metadata("logger-plugin", f"{package_name}.main")
    catalog.publish_plugin(metadata)

    assert (
        api._resolve_caller_logger(module_name).name == "astrbot.plugin.logger-plugin"
    )

    catalog.unpublish(metadata.module_path)

    assert api._resolve_caller_logger(module_name).name == "astrbot"


def test_staged_catalog_never_marks_live_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload staging must not steal SDK logger routing from live code."""
    package_name = "data.plugins.staged_logger"
    module_name = f"{package_name}.helpers"
    package = ModuleType(package_name)
    module = ModuleType(module_name)
    monkeypatch.setitem(sys.modules, package_name, package)
    monkeypatch.setitem(sys.modules, module_name, module)

    staged = PluginCatalog(RuntimeCatalogs(), live_logging=False)
    staged.publish_plugin(_metadata("staged-plugin", f"{package_name}.main"))

    assert not hasattr(module, "__astrbot_plugin_logger_name__")
    assert api._resolve_caller_logger(module_name).name == "astrbot"


def test_plugin_log_level_is_persisted_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An override atomically replaces the persisted preference file."""
    config_path = tmp_path / "plugin_log_levels.json"
    monkeypatch.setattr(
        LogManager,
        "_plugin_log_levels_path",
        MagicMock(return_value=config_path),
    )
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", {})
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())

    LogManager.set_plugin_log_level("atomic-plugin", "warning")

    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "atomic-plugin": "WARNING"
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_invalid_plugin_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the supported logging levels can be persisted."""
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", {})

    with pytest.raises(ValueError, match="Invalid plugin log level"):
        LogManager.set_plugin_log_level("example", "VERBOSE")


def test_configure_logger_syncs_console_and_root_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Terminal and root loggers follow the configured log_level."""
    previous_console_sink = LogManager._console_sink_id
    previous_configured = LogManager._configured
    root_logger = logging.getLogger()
    previous_root_level = root_logger.level
    previous_noisy_levels = {
        name: logging.getLogger(name).level for name in LogManager._NOISY_LOGGER_LEVELS
    }
    global_logger = logging.Logger("console-level-sync")

    try:
        monkeypatch.setattr(LogManager, "_configured", False)
        monkeypatch.setattr(LogManager, "_console_sink_id", None)
        LogManager._setup_loguru()
        LogManager.configure_logger(global_logger, {"log_level": "WARNING"})

        assert global_logger.level == logging.WARNING
        assert logging.getLogger().level == logging.WARNING
        assert LogManager._console_sink_id is not None
    finally:
        if LogManager._console_sink_id not in {None, previous_console_sink}:
            LogManager._remove_sink(LogManager._console_sink_id)
        LogManager._console_sink_id = previous_console_sink
        LogManager._configured = previous_configured
        root_logger.setLevel(previous_root_level)
        for name, noisy_level in previous_noisy_levels.items():
            logging.getLogger(name).setLevel(noisy_level)


def test_global_level_sync_updates_plugins_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plugin that follows global config changes with the core logger."""
    plugin_name = "global-level-plugin"
    plugin_logger = logging.getLogger(f"astrbot.plugin.{plugin_name}")
    previous_level = plugin_logger.level
    global_logger = logging.Logger("global-level-sync")
    monkeypatch.setattr(LogManager, "_plugin_logger_names", {plugin_name})
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", {})

    try:
        LogManager.configure_logger(global_logger, {"log_level": "WARNING"})
        assert plugin_logger.level == logging.WARNING
    finally:
        plugin_logger.setLevel(previous_level)


def test_plugin_log_level_write_failure_preserves_previous_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed replacement leaves both disk and memory preferences intact."""
    config_path = tmp_path / "plugin_log_levels.json"
    config_path.write_text('{"existing-plugin": "INFO"}', encoding="utf-8")
    previous_overrides = {"existing-plugin": "INFO"}
    monkeypatch.setattr(
        LogManager,
        "_plugin_log_levels_path",
        MagicMock(return_value=config_path),
    )
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", previous_overrides)
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())

    with (
        patch.object(Path, "replace", side_effect=OSError("replace failed")),
        pytest.raises(OSError, match="replace failed"),
    ):
        LogManager.set_plugin_log_level("new-plugin", "ERROR")

    assert json.loads(config_path.read_text(encoding="utf-8")) == previous_overrides
    assert LogManager._plugin_level_overrides is previous_overrides
    assert not list(tmp_path.glob("*.tmp"))
