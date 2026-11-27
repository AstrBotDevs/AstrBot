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
from astrbot.core.star.star import StarMetadata
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


@pytest.mark.asyncio
async def test_plugin_teardown_forgets_the_directory_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure a removed plugin no longer owns the log identity of its directory.

    A plugin directory can be reused. Once the previous plugin is unloaded or
    removed, its alias has to go too, otherwise records from the next plugin in
    the same directory would be attributed to the previous plugin's name.

    Args:
        tmp_path: Temporary directory used to build a plugin store layout.
        monkeypatch: Pytest fixture used to isolate paths and plugin state.
    """
    dir_name = "astrbot_plugin_weather"
    module_path = f"data.plugins.{dir_name}.main"
    plugin_file = tmp_path / "data" / "plugins" / dir_name / "main.py"
    plugin_file.parent.mkdir(parents=True)
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_plugin_path",
        lambda: str(tmp_path / "data" / "plugins"),
    )
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_config_path",
        lambda: str(tmp_path / "config"),
    )
    monkeypatch.setattr(
        star_manager_module,
        "get_astrbot_path",
        lambda: str(tmp_path),
    )
    monkeypatch.setattr(star_manager_module, "star_map", {})
    monkeypatch.setattr(star_manager_module, "star_registry", [])
    manager = PluginManager(cast(Any, _StubContext()), cast(Any, {}))
    metadata = StarMetadata(
        name="weather",
        root_dir_name=dir_name,
        module_path=module_path,
    )
    star_manager_module.star_map[module_path] = metadata
    star_manager_module.star_registry.append(metadata)
    broker = LogBroker()
    LogManager.register_plugin_name_alias(dir_name, "weather")

    await manager._unbind_plugin("weather", module_path)
    after_unload = _publish_record(broker, plugin_file)

    # The install and failed-load teardown drops the alias the same way.
    LogManager.register_plugin_name_alias(dir_name, "weather")
    manager._cleanup_plugin_state(dir_name)
    after_cleanup = _publish_record(broker, plugin_file)

    # The plugin is not loaded anymore, so the directory name is the identifier.
    assert after_unload["plugin_name"] == dir_name
    assert after_cleanup["plugin_name"] == dir_name
    assert _plugin_options(broker) == {dir_name}


def test_reused_plugin_directory_uses_the_new_metadata_name(tmp_path: Path) -> None:
    """Ensure a replacement plugin is attributed to its own metadata name.

    The alias only describes the plugin that currently occupies the directory,
    so unloading the previous plugin and registering the next one has to leave
    the new name as the only identifier of that directory.

    Args:
        tmp_path: Temporary directory used to build a plugin store layout.
    """
    dir_name = "astrbot_plugin_weather"
    plugin_file = tmp_path / "data" / "plugins" / dir_name / "main.py"
    plugin_file.parent.mkdir(parents=True)
    LogManager.register_plugin_name_alias(dir_name, "weather")

    # The old plugin is uninstalled and a different plugin takes its place.
    LogManager.forget_plugin_name_alias(dir_name)
    LogManager.register_plugin_name_alias(dir_name, "forecast")

    entry = _publish_record(LogBroker(), plugin_file)

    assert entry["plugin_name"] == "forecast"


def test_registering_twice_and_forgetting_once_leaves_no_alias(
    tmp_path: Path,
) -> None:
    """Ensure one forget clears a directory that was registered twice.

    The alias map holds at most one name per directory, so a plugin that
    registers twice leaves a single entry and forgetting the directory once
    removes it completely instead of exposing the older name.

    Args:
        tmp_path: Temporary directory used to build a plugin store layout.
    """
    dir_name = "astrbot_plugin_weather"
    plugin_file = tmp_path / "data" / "plugins" / dir_name / "main.py"
    plugin_file.parent.mkdir(parents=True)
    LogManager.register_plugin_name_alias(dir_name, "weather")
    LogManager.register_plugin_name_alias(dir_name, "forecast")
    assert log_module._plugin_name_aliases == {dir_name: "forecast"}

    LogManager.forget_plugin_name_alias(dir_name)

    assert log_module._plugin_name_aliases == {}
    entry = _publish_record(LogBroker(), plugin_file)
    assert entry["plugin_name"] == dir_name
