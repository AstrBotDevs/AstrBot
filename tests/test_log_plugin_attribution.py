"""Tests for attributing framework logs to the plugin they report on."""

import logging

from astrbot.core.log import (
    PLUGIN_LOGGER_PREFIX,
    LogBroker,
    LogQueueHandler,
    _RecordEnricherFilter,
)


def _build_record(
    *,
    logger_name: str = "astrbot",
    pathname: str = "/app/astrbot/core/star/star_manager.py",
    plugin_name: str | None = None,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=logger_name,
        level=logging.ERROR,
        pathname=pathname,
        lineno=42,
        msg="plugin failed to load",
        args=(),
        exc_info=None,
    )
    if plugin_name is not None:
        record.plugin_name = plugin_name
    return record


def test_enricher_attributes_explicit_plugin_name_to_core_logs():
    """Core logs about a plugin are tagged and attributed to that plugin."""
    record = _build_record(plugin_name="demo_plugin")

    assert _RecordEnricherFilter().filter(record)

    assert record.plugin_name == "demo_plugin"
    assert record.source == "plugin"
    assert record.plugin_tag == "[demo_plugin]"


def test_enricher_prefers_plugin_logger_name_over_explicit_name():
    """A dedicated plugin logger keeps its own name even with an explicit one."""
    record = _build_record(
        logger_name=f"{PLUGIN_LOGGER_PREFIX}from_logger",
        plugin_name="explicit",
    )

    assert _RecordEnricherFilter().filter(record)

    assert record.plugin_name == "from_logger"
    assert record.source == "plugin"
    assert record.plugin_tag == "[from_logger]"


def test_enricher_falls_back_to_core_for_unattributed_logs():
    """Unattributed framework logs stay on the core source as before."""
    record = _build_record()

    assert _RecordEnricherFilter().filter(record)

    assert record.plugin_name is None
    assert record.source == "core"
    assert record.plugin_tag == "[Core]"


def test_queue_handler_publishes_explicit_plugin_attribution():
    """The WebUI log stream receives the attribution used by its plugin filter."""
    broker = LogBroker()
    handler = LogQueueHandler(broker)
    handler.setFormatter(logging.Formatter("%(plugin_tag)s %(message)s"))
    record = _build_record(plugin_name="demo_plugin")
    _RecordEnricherFilter().filter(record)

    handler.emit(record)

    entry = broker.log_cache[-1]
    assert entry["plugin_name"] == "demo_plugin"
    assert entry["source"] == "plugin"
    assert "[demo_plugin]" in entry["data"]
