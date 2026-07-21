"""Tests for the plugin-aware logger exposed by ``astrbot.api``."""

import logging
from unittest.mock import MagicMock

import pytest

import astrbot.api as api
from astrbot.core.log import LogBroker, LogManager, LogQueueHandler
from astrbot.core.star import Star
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
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())
    monkeypatch.setattr(LogManager, "_plugin_level_overrides", {})
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


def test_legacy_plugin_without_super_uses_dedicated_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure the historical API logger works without ``Star.__init__``.

    Args:
        monkeypatch: Pytest fixture used to isolate logger and registry state.
    """
    module_path = "data.plugins.legacy_logger.main"
    namespace = {
        "__name__": module_path,
        "Star": Star,
        "logger": api.logger,
    }
    exec(
        "class LegacyPlugin(Star):\n"
        "    def __init__(self, context):\n"
        "        self.context = context\n"
        "    def logger_state(self):\n"
        "        return (\n"
        "            logger.name,\n"
        "            logger.getEffectiveLevel(),\n"
        "            logger.isEnabledFor(20),\n"
        "            logger.isEnabledFor(30),\n"
        "        )\n",
        namespace,
    )
    star_map[module_path].name = "legacy_logger"
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())
    monkeypatch.setattr(LogManager, "_log_broker", None)
    monkeypatch.setattr(
        LogManager,
        "_plugin_level_overrides",
        {"legacy_logger": "WARNING"},
    )
    api._logger_cache.pop(module_path, None)

    try:
        plugin = namespace["LegacyPlugin"](object())

        assert plugin.logger_state() == (
            "astrbot.plugin.legacy_logger",
            logging.WARNING,
            False,
            True,
        )
        assert "legacy_logger" in LogManager._plugin_logger_names
    finally:
        api._logger_cache.pop(module_path, None)


def test_queue_handler_only_scans_plugins_for_global_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure registering a plugin logger does not rescan every plugin.

    Args:
        monkeypatch: Pytest fixture used to isolate LogManager class state.
    """
    broker = LogBroker()
    existing_name = "queue_handler_existing"
    existing_logger = logging.getLogger(f"astrbot.plugin.{existing_name}")
    previous_handlers = existing_logger.handlers.copy()
    previous_filters = existing_logger.filters.copy()
    existing_logger.handlers.clear()
    existing_logger.filters.clear()
    plugin_logger = logging.Logger("astrbot.plugin.queue_handler_new")
    global_logger = logging.Logger("astrbot")
    monkeypatch.setattr(LogManager, "_plugin_logger_names", {existing_name})
    monkeypatch.setattr(LogManager, "_log_broker", None)

    try:
        LogManager.set_queue_handler(plugin_logger, broker)

        assert any(
            isinstance(handler, LogQueueHandler) for handler in plugin_logger.handlers
        )
        assert not any(
            isinstance(handler, LogQueueHandler) for handler in existing_logger.handlers
        )

        LogManager.set_queue_handler(global_logger, broker)

        assert any(
            isinstance(handler, LogQueueHandler) for handler in global_logger.handlers
        )
        assert any(
            isinstance(handler, LogQueueHandler) for handler in existing_logger.handlers
        )
    finally:
        existing_logger.handlers[:] = previous_handlers
        existing_logger.filters[:] = previous_filters
