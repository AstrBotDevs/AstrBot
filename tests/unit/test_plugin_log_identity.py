"""Tests for the plugin identity stamped on queue log records.

The Dashboard log page builds its plugin filter from the distinct
``plugin_name`` values of the retained log records, so a record that is
attributed to a plugin by its source file must always carry that name.
"""

import logging
from pathlib import Path

import pytest

from astrbot.core.log import LogBroker, LogManager


def _publish_record_from(
    broker: LogBroker,
    monkeypatch: pytest.MonkeyPatch,
    pathname: Path,
) -> dict:
    """Publish one record logged through the core logger from ``pathname``.

    Args:
        broker: Broker that receives the record.
        monkeypatch: Pytest fixture used to isolate LogManager class state.
        pathname: Source file that emitted the log.

    Returns:
        The published queue entry.
    """
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())
    logger = logging.Logger("astrbot")
    logger.propagate = False
    LogManager.set_queue_handler(logger, broker)
    # Plugin code that logs through ``astrbot.core.logger`` (or through
    # ``astrbot.api.logger`` before the plugin is registered) emits records on
    # the shared logger, so only the source file identifies the plugin.
    record = logging.LogRecord(
        "astrbot",
        logging.ERROR,
        str(pathname),
        12,
        "Plugin failed to load",
        (),
        None,
    )
    logger.handle(record)
    return broker.log_cache[-1]


def test_plugin_record_from_core_logger_keeps_plugin_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure plugin logs sent through the core logger stay filterable.

    Args:
        tmp_path: Temporary directory used to build a plugin store layout.
        monkeypatch: Pytest fixture used to isolate LogManager class state.
    """
    plugin_file = tmp_path / "data" / "plugins" / "astrbot_plugin_demo" / "main.py"
    plugin_file.parent.mkdir(parents=True)
    broker = LogBroker()

    entry = _publish_record_from(broker, monkeypatch, plugin_file)

    assert entry["source"] == "plugin"
    assert entry["plugin_name"] == "astrbot_plugin_demo"
    # The Dashboard plugin filter lists these distinct names.
    plugin_options = {
        item["plugin_name"] for item in broker.log_cache if item["source"] == "plugin"
    }
    assert plugin_options == {"astrbot_plugin_demo"}


def test_nested_plugin_module_record_keeps_plugin_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure records from a plugin subpackage keep the plugin name.

    Args:
        tmp_path: Temporary directory used to build a plugin store layout.
        monkeypatch: Pytest fixture used to isolate LogManager class state.
    """
    plugin_file = (
        tmp_path / "data" / "plugins" / "astrbot_plugin_demo" / "utils" / "http.py"
    )
    plugin_file.parent.mkdir(parents=True)

    entry = _publish_record_from(LogBroker(), monkeypatch, plugin_file)

    assert entry["source"] == "plugin"
    assert entry["plugin_name"] == "astrbot_plugin_demo"


def test_builtin_star_record_keeps_plugin_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure built-in plugin logs stay filterable too.

    Args:
        tmp_path: Temporary directory used to build an install layout.
        monkeypatch: Pytest fixture used to isolate LogManager class state.
    """
    plugin_file = tmp_path / "astrbot" / "builtin_stars" / "astrbot" / "main.py"
    plugin_file.parent.mkdir(parents=True)

    entry = _publish_record_from(LogBroker(), monkeypatch, plugin_file)

    assert entry["source"] == "plugin"
    assert entry["plugin_name"] == "astrbot"


def test_core_record_stays_unattributed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure the name derivation does not invent plugins for core logs.

    Args:
        tmp_path: Temporary directory used to build an install layout.
        monkeypatch: Pytest fixture used to isolate LogManager class state.
    """
    core_file = tmp_path / "astrbot" / "core" / "core_lifecycle.py"
    core_file.parent.mkdir(parents=True)

    entry = _publish_record_from(LogBroker(), monkeypatch, core_file)

    assert entry["source"] == "core"
    assert entry["plugin_name"] is None
