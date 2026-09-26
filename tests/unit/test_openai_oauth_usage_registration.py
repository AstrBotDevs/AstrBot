import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.provider.register import llm_tools
from astrbot.core.star.star_handler import star_handlers_registry


def test_core_quota_command_and_tool_registration():
    tools = [t for t in llm_tools.func_list if t.name == "codex_oauth_usage"]
    assert len(tools) == 1
    assert tools[0].parameters.get("properties", {}) == {}
    # The loader fills handler_module_path when binding the runtime instance.
    assert tools[0].handler.__module__ == "astrbot.builtin_stars.astrbot.main"
    handlers = star_handlers_registry.get_handlers_by_module_name(
        "astrbot.builtin_stars.astrbot.main"
    )
    matches = [
        h
        for h in handlers
        if any(
            getattr(f, "command_name", None) == "codex_oauth_usage"
            for f in h.event_filters
        )
    ]
    assert len(matches) == 1
    assert any(
        f.__class__.__name__ == "PermissionTypeFilter" for f in matches[0].event_filters
    )


@pytest.mark.asyncio
async def test_core_command_and_tool_share_profile_scoped_service():
    main = Main(SimpleNamespace())
    result = {
        "status": "success",
        "windows": [
            {"used_percent": 30, "remaining_percent": 70, "window_seconds": 604800}
        ],
    }
    main.oauth_usage_service.run = AsyncMock(return_value=result)
    event = SimpleNamespace(stop_event=Mock(), plain_result=lambda text: text)
    output = [r async for r in main.codex_oauth_usage_command(event)]
    assert len(output) == 1 and "已用 30%，剩余 70%" in output[0]
    event.stop_event.assert_called_once()
    assert json.loads(await main.codex_oauth_usage(event)) == result
    await main.terminate()
    assert main.oauth_usage_service.closed
