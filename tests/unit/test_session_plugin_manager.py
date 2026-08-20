from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import PluginRegistry, StarMetadata


@pytest.mark.asyncio
async def test_filter_handlers_respects_enabled_plugins():
    event = SimpleNamespace(unified_msg_origin="umo")
    handlers = [
        SimpleNamespace(handler_module_path="module.a", handler_name="ha"),
        SimpleNamespace(handler_module_path="module.b", handler_name="hb"),
    ]
    preferences = SimpleNamespace(
        get_async=AsyncMock(
            return_value={
                "umo": {
                    "enabled_plugins": ["plugin-a"],
                    "disabled_plugins": [],
                }
            }
        )
    )

    plugins = PluginRegistry()
    plugins.publish(StarMetadata(name="plugin-a", module_path="module.a"))
    plugins.publish(StarMetadata(name="plugin-b", module_path="module.b"))

    filtered = await SessionPluginManager(
        preferences, plugins
    ).filter_handlers_by_session(event, handlers)

    assert filtered == [handlers[0]]
