"""Tests for the plugin-aware logger exposed by ``astrbot.api``."""

import logging
from unittest.mock import MagicMock

import pytest

import astrbot.api as api
from astrbot.core.log import LogManager
from astrbot.core.star.star import StarMetadata, star_map


def test_plugin_logger_cache_refreshes_after_plugin_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure a cached logger follows the latest plugin metadata name.

    Args:
        monkeypatch: Pytest fixture used to isolate the plugin registry change.
    """
    module_path = "data.plugins.cache_refresh.main"
    caller_module = "data.plugins.cache_refresh.helpers"
    monkeypatch.setitem(
        star_map,
        module_path,
        StarMetadata(name="old_name", module_path=module_path),
    )
    api._logger_cache.pop(caller_module, None)

    try:
        old_logger = api._resolve_caller_logger(caller_module)
        star_map[module_path] = StarMetadata(
            name="new_name",
            module_path=module_path,
        )
        new_logger = api._resolve_caller_logger(caller_module)

        assert old_logger.name == "astrbot.plugin.old_name"
        assert new_logger.name == "astrbot.plugin.new_name"
    finally:
        api._logger_cache.pop(caller_module, None)


def test_global_level_sync_handles_mock_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure global level syncing always passes a valid logging level.

    Args:
        monkeypatch: Pytest fixture used to isolate LogManager class state.
    """
    plugin_name = "mock_level_sync"
    plugin_logger = logging.getLogger(f"astrbot.plugin.{plugin_name}")
    previous_level = plugin_logger.level
    global_logger = MagicMock()
    global_logger.level = MagicMock()
    monkeypatch.setattr(LogManager, "_plugin_logger_names", {plugin_name})
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", {})

    try:
        LogManager.configure_logger(global_logger, {"log_level": "WARNING"})

        assert plugin_logger.level == logging.WARNING
    finally:
        plugin_logger.setLevel(previous_level)
