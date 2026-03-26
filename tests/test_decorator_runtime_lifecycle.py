from __future__ import annotations

import asyncio
from pathlib import Path
from textwrap import dedent

import pytest

from astrbot_sdk.testing import PluginHarness


async def _wait_until(predicate, *, timeout: float = 0.2) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("timed out waiting for condition")


def _write_plugin(
    plugin_dir: Path,
    *,
    name: str,
    class_name: str,
    source: str,
    reserved: bool = False,
) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        dedent(
            f"""
            _schema_version: 2
            name: {name}
            author: tests
            version: 1.0.0
            desc: decorator runtime tests
            reserved: {"true" if reserved else "false"}

            runtime:
              python: "3.12"

            components:
              - class: main:{class_name}
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(dedent(source).lstrip(), encoding="utf-8")


@pytest.mark.asyncio
async def test_http_api_decorator_registers_and_unregisters_route(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "http_api_plugin"
    _write_plugin(
        plugin_dir,
        name="http_api_plugin",
        class_name="HttpApiPlugin",
        source="""
        from astrbot_sdk import Star, http_api, provide_capability


        class HttpApiPlugin(Star):
            @http_api(route="/decorated", methods=["GET", "POST"], description="Decorated API")
            @provide_capability("http_api_plugin.handle_http", description="Handle decorated HTTP route")
            async def handle_http(self, request_id: str, payload: dict, cancel_token):
                return {"status": 200, "body": {"request_id": request_id, "payload": payload}}
        """,
    )

    harness = PluginHarness.from_plugin_dir(plugin_dir)
    await harness.start()
    try:
        assert harness.lifecycle_context is not None
        apis = await harness.lifecycle_context.http.list_apis()
        assert apis == [
            {
                "route": "/decorated",
                "methods": ["GET", "POST"],
                "handler_capability": "http_api_plugin.handle_http",
                "description": "Decorated API",
                "plugin_id": "http_api_plugin",
            }
        ]
    finally:
        await harness.stop()

    assert harness.router.http_api_store == []


@pytest.mark.asyncio
async def test_validate_config_decorator_rejects_invalid_config(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "validate_config_plugin"
    _write_plugin(
        plugin_dir,
        name="validate_config_plugin",
        class_name="ValidateConfigPlugin",
        source="""
        from pydantic import BaseModel

        from astrbot_sdk import Context, Star, validate_config


        class PluginConfig(BaseModel):
            api_key: str


        class ValidateConfigPlugin(Star):
            @validate_config(model=PluginConfig)
            async def on_start(self, ctx: Context) -> None:
                del ctx
        """,
    )

    harness = PluginHarness.from_plugin_dir(plugin_dir)
    with pytest.raises(Exception, match="api_key"):
        await harness.start()


@pytest.mark.asyncio
async def test_on_provider_change_decorator_registers_and_unsubscribes(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "provider_change_plugin"
    _write_plugin(
        plugin_dir,
        name="provider_change_plugin",
        class_name="ProviderChangePlugin",
        reserved=True,
        source="""
        from astrbot_sdk import Star, on_provider_change


        class ProviderChangePlugin(Star):
            def __init__(self) -> None:
                self.events = []

            @on_provider_change(provider_types=["embedding"])
            async def handle_change(self, provider_id: str, provider_type, umo: str | None) -> None:
                self.events.append((provider_id, getattr(provider_type, "value", str(provider_type)), umo))
        """,
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        assert harness.loaded_plugin is not None
        plugin = harness.loaded_plugin.instances[0]
        await _wait_until(
            lambda: len(harness.router._provider_change_subscriptions) == 1
        )
        harness.router.emit_provider_change("embed-a", "embedding", "session:1")
        harness.router.emit_provider_change("rerank-a", "rerank", "session:2")
        await asyncio.sleep(0.05)

        assert plugin.events == [("embed-a", "embedding", "session:1")]
        assert harness.router._provider_change_subscriptions

    assert not harness.router._provider_change_subscriptions


@pytest.mark.asyncio
async def test_background_task_decorator_auto_starts_and_cancels(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "background_task_plugin"
    _write_plugin(
        plugin_dir,
        name="background_task_plugin",
        class_name="BackgroundTaskPlugin",
        source="""
        import asyncio

        from astrbot_sdk import Context, Star, background_task


        class BackgroundTaskPlugin(Star):
            def __init__(self) -> None:
                self.started = asyncio.Event()
                self.cancelled = False

            @background_task(description="decorated background task")
            async def sync_data(self, ctx: Context) -> None:
                del ctx
                self.started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise
        """,
    )

    harness = PluginHarness.from_plugin_dir(plugin_dir)
    await harness.start()
    assert harness.loaded_plugin is not None
    plugin = harness.loaded_plugin.instances[0]
    await asyncio.wait_for(plugin.started.wait(), timeout=0.2)
    await harness.stop()

    assert plugin.cancelled is True


@pytest.mark.asyncio
async def test_register_skill_decorator_registers_and_unregisters(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "skill_plugin"
    _write_plugin(
        plugin_dir,
        name="skill_plugin",
        class_name="SkillPlugin",
        source="""
        from astrbot_sdk import Star, register_skill


        @register_skill(name="demo_skill", path="skills/demo.py", description="Demo skill")
        class SkillPlugin(Star):
            pass
        """,
    )

    harness = PluginHarness.from_plugin_dir(plugin_dir)
    await harness.start()
    try:
        assert harness.lifecycle_context is not None
        skills = await harness.lifecycle_context.skills.list()
        assert len(skills) == 1
        assert skills[0].name == "demo_skill"
        assert skills[0].path == "skills/demo.py"
        assert skills[0].description == "Demo skill"
    finally:
        await harness.stop()

    plugin = harness.router._plugins["skill_plugin"]
    assert plugin.skills == {}


@pytest.mark.asyncio
async def test_mcp_server_decorator_registers_global_server_with_ack(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "mcp_server_plugin"
    _write_plugin(
        plugin_dir,
        name="mcp_server_plugin",
        class_name="MCPServerPlugin",
        source="""
        from astrbot_sdk import Star, acknowledge_global_mcp_risk, mcp_server


        @acknowledge_global_mcp_risk
        @mcp_server(
            name="decorated-global",
            scope="global",
            config={"mock_tools": ["inspect"]},
            timeout=0.1,
        )
        class MCPServerPlugin(Star):
            pass
        """,
    )

    harness = PluginHarness.from_plugin_dir(plugin_dir)
    await harness.start()
    try:
        assert harness.lifecycle_context is not None
        servers = await harness.lifecycle_context.mcp.list_global_servers()
        assert [server.name for server in servers] == ["decorated-global"]
    finally:
        await harness.stop()

    assert harness.router._mcp_global_servers == {}
