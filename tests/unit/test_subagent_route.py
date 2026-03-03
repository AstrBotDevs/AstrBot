from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from quart import Quart

from astrbot.core.agent.tool import FunctionTool
from astrbot.dashboard.routes.route import RouteContext
from astrbot.dashboard.routes.subagent import SubAgentRoute


class _FakeConfig(dict):
    def save_config(self) -> None:
        self["_saved"] = True


@pytest.fixture
def subagent_app():
    app = Quart(__name__)
    astrbot_config = _FakeConfig(
        {
            "subagent_orchestrator": {
                "enable": True,
                "agents": [
                    {
                        "name": "writer",
                        "system_prompt": "legacy prompt",
                    }
                ],
            }
        }
    )
    lifecycle = MagicMock()
    lifecycle.astrbot_config = astrbot_config
    lifecycle.subagent_orchestrator = MagicMock()
    lifecycle.subagent_orchestrator.reload_from_config = AsyncMock(
        return_value=["WARN: reload"]
    )
    lifecycle.subagent_orchestrator.list_tasks = AsyncMock(return_value=[])
    lifecycle.subagent_orchestrator.retry_task = AsyncMock(return_value=True)
    lifecycle.subagent_orchestrator.cancel_task = AsyncMock(return_value=True)

    normal_tool = FunctionTool(
        name="tool_a",
        description="A",
        parameters={"type": "object", "properties": {}},
        handler=None,
    )
    hidden_tool = FunctionTool(
        name="tool_b",
        description="B",
        parameters={"type": "object", "properties": {}},
        handler=None,
    )
    hidden_tool.handler_module_path = "core.subagent_orchestrator"
    lifecycle.provider_manager.llm_tools.func_list = [normal_tool, hidden_tool]

    route_ctx = RouteContext(config=MagicMock(), app=app)
    SubAgentRoute(route_ctx, lifecycle)
    return app, lifecycle, astrbot_config


@pytest.mark.asyncio
async def test_get_subagent_config_returns_compatible_shape(subagent_app):
    app, _, _ = subagent_app
    async with app.test_app():
        client = app.test_client()
        resp = await client.get("/api/subagent/config")
        body = await resp.get_json()
    assert resp.status_code == 200
    assert body["status"] == "ok"
    assert "agents" in body["data"]
    assert body["data"]["agents"][0]["system_prompt"] == "legacy prompt"
    assert "compat_warnings" in body["data"]


@pytest.mark.asyncio
async def test_post_subagent_config_returns_diagnostics_and_compat_warnings(subagent_app):
    app, lifecycle, astrbot_config = subagent_app
    payload = {
        "enable": True,
        "agents": [
            {
                "name": "writer",
                "system_prompt": "legacy prompt",
            }
        ],
    }
    async with app.test_app():
        client = app.test_client()
        resp = await client.post("/api/subagent/config", json=payload)
        body = await resp.get_json()

    assert resp.status_code == 200
    assert body["status"] == "ok"
    assert "diagnostics" in body["data"]
    assert "compat_warnings" in body["data"]
    assert any("legacy field" in item for item in body["data"]["compat_warnings"])
    assert astrbot_config.get("_saved") is True
    lifecycle.subagent_orchestrator.reload_from_config.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_subagent_tasks_clamps_limit(subagent_app):
    app, lifecycle, _ = subagent_app
    async with app.test_app():
        client = app.test_client()
        resp = await client.get("/api/subagent/tasks?limit=0")
        body = await resp.get_json()
    assert resp.status_code == 200
    assert body["status"] == "ok"
    lifecycle.subagent_orchestrator.list_tasks.assert_awaited_once_with(
        status=None, limit=1
    )


@pytest.mark.asyncio
async def test_subagent_task_actions(subagent_app):
    app, lifecycle, _ = subagent_app
    async with app.test_app():
        client = app.test_client()
        retry_resp = await client.post("/api/subagent/tasks/task-1/retry")
        cancel_resp = await client.post("/api/subagent/tasks/task-1/cancel")
        retry_body = await retry_resp.get_json()
        cancel_body = await cancel_resp.get_json()
    assert retry_resp.status_code == 200
    assert cancel_resp.status_code == 200
    assert retry_body["status"] == "ok"
    assert cancel_body["status"] == "ok"
    lifecycle.subagent_orchestrator.retry_task.assert_awaited_once_with("task-1")
    lifecycle.subagent_orchestrator.cancel_task.assert_awaited_once_with("task-1")
