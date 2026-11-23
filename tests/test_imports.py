"""Public startup imports and runtime contracts for the current architecture."""

import inspect
import json

import pytest


def test_public_config_round_trip_keeps_storage_metadata_private(tmp_path) -> None:
    from astrbot.api import AstrBotConfig

    path = tmp_path / "plugin.json"
    defaults = {"title": "original", "choices": ["first"]}
    config = AstrBotConfig(str(path), default_config=defaults)
    config["title"] = "updated"
    config["choices"].append("second")
    config.save_config()

    stored = json.loads(path.read_text(encoding="utf-8-sig"))
    reloaded = AstrBotConfig(str(path), default_config=defaults)
    assert stored["title"] == reloaded["title"] == "updated"
    assert stored["choices"] == reloaded["choices"] == ["first", "second"]
    assert defaults == {"title": "original", "choices": ["first"]}
    assert "config_path" not in stored
    assert "default_config" not in stored


def test_native_runtime_implements_the_shared_runtime_contract() -> None:
    from astrbot.core.agent.runtime import AgentRuntime
    from astrbot.core.agent.tool_executor import BaseFunctionToolExecutor
    from astrbot.core.astr_agent_runtime import AstrAgentRuntime
    from astrbot.core.astr_agent_runtime.runtime import AstrAgentRuntime as Runtime
    from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor

    assert AstrAgentRuntime is Runtime
    assert issubclass(Runtime, AgentRuntime)
    assert issubclass(FunctionToolExecutor, BaseFunctionToolExecutor)


def test_platform_remains_abstract() -> None:
    from astrbot.core.platform.platform import Platform

    assert inspect.isabstract(Platform)
    with pytest.raises(TypeError, match="abstract"):
        Platform({}, {})


def test_public_chat_router_keeps_session_and_thread_http_contracts() -> None:
    from fastapi import FastAPI

    from astrbot.dashboard.api.chat import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    paths = app.openapi()["paths"]
    assert {"get", "patch", "delete"}.issubset(
        paths["/api/v1/chat/sessions/{session_id}"]
    )
    assert "post" in paths["/api/v1/chat/threads"]
    assert "post" in paths["/api/v1/chat/threads/{thread_id}/messages"]
    assert "get" in paths["/api/v1/chat/runs/{run_id}/stream"]


@pytest.mark.parametrize(
    ("path", "mode"),
    [("/api/v1/live-chat/ws", "live"), ("/api/v1/unified-chat/ws", None)],
)
def test_public_live_chat_router_keeps_both_websocket_modes(path, mode) -> None:
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from astrbot.dashboard.api.live_chat import router

    async def exchange(*, token, force_ct, receive_json, send_json, close):
        message = await receive_json()
        await send_json({"token": token, "mode": force_ct, "message": message})
        await close()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.services = SimpleNamespace(
        live_chat=SimpleNamespace(run_websocket_session=exchange)
    )
    with (
        TestClient(app) as client,
        client.websocket_connect(path + "?token=fixture-token") as websocket,
    ):
        websocket.send_json({"text": "hello"})
        assert websocket.receive_json() == {
            "token": "fixture-token",
            "mode": mode,
            "message": {"text": "hello"},
        }
