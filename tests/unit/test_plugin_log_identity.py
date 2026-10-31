"""Tests for the plugin identity stamped on queue log records.

The Dashboard log page builds its plugin filter from the distinct
``plugin_name`` values of the retained log records, so every record that the
page shows for a plugin has to carry that plugin's name.
"""

import logging
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from astrbot.core import log as log_module
from astrbot.core.log import LogBroker, LogManager
from astrbot.core.star import star_manager as star_manager_module
from astrbot.core.star.star_manager import PluginManager


@pytest.fixture(autouse=True)
def isolated_plugin_log_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the module-level state the log records are stamped from.

    Args:
        monkeypatch: Pytest fixture used to restore the state after the test.
    """
    monkeypatch.setattr(LogManager, "_plugin_logger_names", set())
    monkeypatch.setattr(LogManager, "_log_broker", None)
    monkeypatch.setattr(log_module, "_plugin_name_aliases", {}, raising=False)


def _publish_record(
    broker: LogBroker,
    pathname: Path | str,
    *,
    logger_name: str = "astrbot",
    message: str = "Plugin failed to load",
    extra: dict[str, Any] | None = None,
) -> dict:
    """Publish one log record through a logger that feeds ``broker``.

    Args:
        broker: Broker that receives the record.
        pathname: Source file recorded on the log record.
        logger_name: Name of the logger that handles the record.
        message: Message of the log record.
        extra: Extra attributes that the logging caller stamps on the record.

    Returns:
        The published queue entry.
    """
    logger = logging.Logger(logger_name)
    logger.propagate = False
    LogManager.set_queue_handler(logger, broker)
    record = logging.LogRecord(
        logger_name,
        logging.ERROR,
        str(pathname),
        12,
        message,
        (),
        None,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    logger.handle(record)
    return broker.log_cache[-1]


def _plugin_options(broker: LogBroker) -> set[str]:
    """Return the plugin names the Dashboard would list in its filter.

    Args:
        broker: Broker holding the retained log entries.

    Returns:
        Distinct plugin names of the retained plugin records.
    """
    return {
        entry["plugin_name"]
        for entry in broker.log_cache
        if entry["source"] == "plugin"
    }


def test_plugin_record_from_core_logger_keeps_plugin_name(tmp_path: Path) -> None:
    """Ensure plugin logs sent through the core logger stay filterable.

    Args:
        tmp_path: Temporary directory used to build a plugin store layout.
    """
    plugin_file = tmp_path / "data" / "plugins" / "astrbot_plugin_demo" / "main.py"
    plugin_file.parent.mkdir(parents=True)
    broker = LogBroker()

    entry = _publish_record(broker, plugin_file)

    assert entry["source"] == "plugin"
    assert entry["plugin_name"] == "astrbot_plugin_demo"
    # The Dashboard plugin filter lists these distinct names.
    assert _plugin_options(broker) == {"astrbot_plugin_demo"}


def test_nested_plugin_module_record_keeps_plugin_name(tmp_path: Path) -> None:
    """Ensure records from a plugin subpackage keep the plugin name.

    Args:
        tmp_path: Temporary directory used to build a plugin store layout.
    """
    plugin_file = (
        tmp_path / "data" / "plugins" / "astrbot_plugin_demo" / "utils" / "http.py"
    )
    plugin_file.parent.mkdir(parents=True)

    entry = _publish_record(LogBroker(), plugin_file)

    assert entry["source"] == "plugin"
    assert entry["plugin_name"] == "astrbot_plugin_demo"


def test_builtin_star_record_keeps_plugin_name(tmp_path: Path) -> None:
    """Ensure built-in plugin logs stay filterable too.

    Args:
        tmp_path: Temporary directory used to build an install layout.
    """
    plugin_file = tmp_path / "astrbot" / "builtin_stars" / "astrbot" / "main.py"
    plugin_file.parent.mkdir(parents=True)

    entry = _publish_record(LogBroker(), plugin_file)

    assert entry["source"] == "plugin"
    assert entry["plugin_name"] == "astrbot"


def test_core_record_stays_unattributed(tmp_path: Path) -> None:
    """Ensure the name derivation does not invent plugins for core logs.

    Args:
        tmp_path: Temporary directory used to build an install layout.
    """
    core_file = tmp_path / "astrbot" / "core" / "core_lifecycle.py"
    core_file.parent.mkdir(parents=True)

    entry = _publish_record(LogBroker(), core_file)

    assert entry["source"] == "core"
    assert entry["plugin_name"] is None


def test_plugin_directory_uses_the_registered_metadata_name(tmp_path: Path) -> None:
    """Ensure one plugin yields one filter entry when both names differ.

    The plugin directory is not necessarily the name in the plugin metadata, so
    a record attributed by its source file and a record attributed by the
    plugin's logger must resolve to the same identifier.

    Args:
        tmp_path: Temporary directory used to build a plugin store layout.
    """
    plugin_file = tmp_path / "data" / "plugins" / "astrbot_plugin_weather" / "main.py"
    plugin_file.parent.mkdir(parents=True)
    LogManager.register_plugin_name_alias("astrbot_plugin_weather", "weather")
    broker = LogBroker()

    from_source_file = _publish_record(broker, plugin_file)
    from_plugin_logger = _publish_record(
        broker,
        plugin_file,
        logger_name="astrbot.plugin.weather",
    )

    assert from_source_file["plugin_name"] == "weather"
    assert from_plugin_logger["plugin_name"] == "weather"
    assert _plugin_options(broker) == {"weather"}


class _StubContext:
    """Minimal plugin context for constructing a plugin manager in tests."""

    def get_all_stars(self) -> list[Any]:
        """Return the registered plugins.

        Returns:
            An empty plugin list.
        """
        return []


@pytest.mark.asyncio
async def test_failed_plugin_load_is_filterable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure a plugin that fails to load appears in the plugin filter.

    A plugin that cannot be imported never logs through its own logger: the
    loader reports the failure from core code. Those records must still be
    attributed to the plugin, otherwise the Dashboard cannot filter them.

    Args:
        tmp_path: Temporary directory used to build a plugin install layout.
        monkeypatch: Pytest fixture used to isolate paths and plugin state.
    """
    plugin_name = "astrbot_plugin_fix_quote_timestamp"
    plugin_root = tmp_path / "astrbot_root"
    plugin_store = plugin_root / "data" / "plugins"
    plugin_path = plugin_store / plugin_name
    plugin_path.mkdir(parents=True)
    (plugin_path / "metadata.yaml").write_text(
        yaml.dump(
            {
                "name": plugin_name,
                "author": "tester",
                "desc": "Plugin that fails on import",
                "version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )
    (plugin_path / "main.py").write_text(
        "raise RuntimeError('missing host dependency')\n",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(plugin_root))
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_plugin_path",
        lambda: str(plugin_store),
    )
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path / "config"),
    )
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_path",
        lambda: str(plugin_root),
    )

    async def global_get(key: str, default: Any = None) -> Any:
        del key
        return default

    async def sync_command_configs() -> None:
        return None

    monkeypatch.setattr(star_manager_module.sp, "global_get", global_get)
    monkeypatch.setattr(
        star_manager_module,
        "sync_command_configs",
        sync_command_configs,
    )

    manager = PluginManager(cast(Any, _StubContext()), cast(Any, {}))
    broker = LogBroker()
    logger = logging.Logger("astrbot")
    logger.propagate = False
    LogManager.set_queue_handler(logger, broker)
    monkeypatch.setattr(star_manager_module, "logger", logger)

    success, _ = await manager.load(specified_dir_name=plugin_name)

    assert success is False
    assert plugin_name in manager.failed_plugin_dict
    assert _plugin_options(broker) == {plugin_name}
