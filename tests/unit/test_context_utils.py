from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.pipeline.context_utils import call_event_hook
from astrbot.core.star.star_handler import EventType


@pytest.mark.asyncio
async def test_call_event_hook_skips_session_disabled_plugin():
    event = MagicMock()
    event.plugins_name = ["*"]
    event.unified_msg_origin = "test_platform:private:session123"
    event.is_stopped.return_value = False

    handler = MagicMock()
    handler.handler_name = "on_llm_request"
    handler.handler_module_path = "test_plugin"
    handler.handler = AsyncMock()

    with patch(
        "astrbot.core.pipeline.context_utils.star_handlers_registry.get_handlers_by_event_type",
        return_value=[handler],
    ), patch(
        "astrbot.core.pipeline.context_utils.star_map"
    ) as mock_star_map, patch(
        "astrbot.core.pipeline.context_utils.SessionPluginManager.get_session_plugin_config",
        new=AsyncMock(return_value={"disabled_plugins": ["astrbot_plugin_memorix"]}),
    ):
        mock_plugin = MagicMock()
        mock_plugin.name = "astrbot_plugin_memorix"
        mock_plugin.reserved = False
        mock_star_map.get.return_value = mock_plugin

        stopped = await call_event_hook(event, EventType.OnLLMRequestEvent)

    assert stopped is False
    handler.handler.assert_not_awaited()
