"""Plugin construction preserves registration and logger ownership."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

from astrbot.core.star import base
from astrbot.core.star.star import StarMetadata


def test_subclasses_register_once_and_replace_the_loaded_class(monkeypatch) -> None:
    registry = []
    metadata = {}
    monkeypatch.setattr(base, "star_registry", registry)
    monkeypatch.setattr(base, "star_map", metadata)
    first = type("FirstPlugin", (base.Star,), {"__module__": "task25.plugin"})
    second = type("ReloadedPlugin", (base.Star,), {"__module__": "task25.plugin"})
    assert len(registry) == 1
    assert registry[0] is metadata["task25.plugin"]
    assert metadata["task25.plugin"].star_cls_type is second
    assert metadata["task25.plugin"].star_cls_type is not first


def test_plugin_uses_registered_name_and_retains_context(monkeypatch) -> None:
    monkeypatch.setattr(base, "star_registry", [])
    monkeypatch.setattr(base, "star_map", {})
    plugin_type = type("Plugin", (base.Star,), {"__module__": "task25.logger"})
    base.star_map[plugin_type.__module__] = StarMetadata(name="registered-plugin")
    plugin_logger = logging.getLogger("task25.plugin")
    get_logger = Mock(return_value=plugin_logger)
    monkeypatch.setattr(base.LogManager, "get_plugin_logger", get_logger)
    context = SimpleNamespace()
    plugin = plugin_type(context)
    assert plugin.context is context
    assert plugin.logger is plugin_logger
    get_logger.assert_called_once_with("registered-plugin")
