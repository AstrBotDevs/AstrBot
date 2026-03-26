from __future__ import annotations

import asyncio
import json
from pathlib import Path
from textwrap import dedent

import pytest

from astrbot_sdk import AstrBotError, PluginMetadata, StarMetadata
from astrbot_sdk.context import CancelToken
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.testing import PluginHarness


def _write_plugin(
    plugin_dir: Path,
    *,
    name: str,
    class_name: str,
    source: str,
    description: str = "star lifecycle runtime tests",
    display_name: str | None = None,
    support_platforms: list[str] | None = None,
    astrbot_version: str | None = None,
    config_schema: dict[str, object] | None = None,
    config_payload: dict[str, object] | None = None,
) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest_lines = [
        "_schema_version: 2",
        f"name: {name}",
    ]
    if isinstance(display_name, str):
        manifest_lines.append(f"display_name: {display_name}")
    manifest_lines.extend(
        [
            "author: tests",
            "version: 1.0.0",
            f"desc: {description}",
        ]
    )
    if isinstance(astrbot_version, str):
        manifest_lines.append(f'astrbot_version: "{astrbot_version}"')
    manifest_lines.extend(
        [
            "runtime:",
            '  python: "3.12"',
            "",
            "components:",
            f"  - class: main:{class_name}",
        ]
    )
    if support_platforms:
        manifest_lines.append("")
        manifest_lines.append("support_platforms:")
        manifest_lines.extend(f"  - {platform}" for platform in support_platforms)

    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(manifest_lines) + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(dedent(source).lstrip(), encoding="utf-8")

    if config_schema is not None:
        (plugin_dir / "_conf_schema.json").write_text(
            json.dumps(config_schema, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if config_payload is not None:
        config_dir = plugin_dir / "data" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / f"{name}_config.json").write_text(
            json.dumps(config_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@pytest.mark.asyncio
async def test_star_lifecycle_runtime_uses_context_metadata_db_and_cleanup(
    tmp_path: Path,
) -> None:
    assert PluginMetadata is StarMetadata

    plugin_dir = tmp_path / "lifecycle_plugin"
    _write_plugin(
        plugin_dir,
        name="lifecycle_plugin",
        class_name="LifecycleRuntimePlugin",
        display_name="Lifecycle Plugin",
        support_platforms=["aiocqhttp", "telegram"],
        astrbot_version=">=4.13.0,<5.0.0",
        config_schema={
            "api_key": {
                "type": "string",
                "description": "api key",
                "default": "",
            },
            "timeout": {
                "type": "int",
                "description": "request timeout",
                "default": 30,
            },
            "max_retries": {
                "type": "int",
                "description": "retry count",
                "default": 3,
            },
            "debug": {
                "type": "bool",
                "description": "debug mode",
                "default": False,
            },
        },
        config_payload={
            "api_key": "secret-key",
            "timeout": 7,
        },
        source="""
        import asyncio

        from astrbot_sdk import Context, MessageEvent, PluginMetadata, Star, StarMetadata
        from astrbot_sdk.decorators import on_command


        class LifecycleRuntimePlugin(Star):
            def __init__(self) -> None:
                self.order = []
                self.cache = {}
                self.lifecycle_state = "new"
                self.config_snapshot = {}
                self.current_metadata = None
                self.dependency_metadata = None
                self.rendered_text = ""
                self.rendered_html = ""
                self.background_started = asyncio.Event()
                self.background_cancelled = False
                self._background_task = None

            async def initialize(self) -> None:
                self.order.append("initialize")
                self.cache["initialized"] = True
                self.lifecycle_state = "initialized"

            async def on_start(self, ctx: Context) -> None:
                await super().on_start(ctx)
                assert self.context is ctx
                self.order.append("on_start")
                self.config_snapshot = await ctx.metadata.get_plugin_config() or {}
                self.current_metadata = await ctx.metadata.get_current_plugin()
                self.dependency_metadata = await ctx.metadata.get_plugin("dependency_plugin")
                await ctx.db.set("config_timeout", self.config_snapshot.get("timeout"))
                await self.put_kv_data("startup_state", "running")
                self.rendered_text = await self.text_to_image(
                    self.current_metadata.name if self.current_metadata else "unknown"
                )
                self.rendered_html = await self.html_render(
                    "startup",
                    {
                        "plugin": (
                            self.current_metadata.display_name
                            if self.current_metadata
                            else ""
                        )
                    },
                )
                await ctx.register_llm_tool(
                    name="echo_tool",
                    parameters_schema={
                        "type": "object",
                        "properties": {"payload": {"type": "string"}},
                    },
                    desc="Echo lifecycle tool",
                    func_obj=self.echo_tool,
                )
                self._background_task = await ctx.register_task(
                    self.background_probe(),
                    "lifecycle background",
                )

            async def background_probe(self) -> None:
                assert self.context is not None
                await self.put_kv_data("background_plugin_id", self.context.plugin_id)
                self.background_started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    self.background_cancelled = True
                    raise

            async def echo_tool(self, payload: str, ctx: Context) -> str:
                assert self.context is ctx
                await ctx.db.set("tool_payload", payload)
                return f"tool:{payload}:{ctx.plugin_id}"

            @on_command("state")
            async def state(self, event: MessageEvent, ctx: Context) -> None:
                assert self.context is ctx
                visits = await self.get_kv_data("visits", 0)
                await self.put_kv_data("visits", visits + 1)
                current: StarMetadata | None = await ctx.metadata.get_current_plugin()
                dependency: PluginMetadata | None = await ctx.metadata.get_plugin(
                    "dependency_plugin"
                )
                await event.reply(
                    f"{current.name if current else 'missing'}:"
                    f"{dependency.version if dependency else 'missing'}:"
                    f"{visits + 1}:{ctx.plugin_id}:{self.config_snapshot.get('timeout')}"
                )

            async def on_stop(self, ctx: Context) -> None:
                assert self.context is ctx
                self.order.append("on_stop_before_super")
                await self.put_kv_data("shutdown_state", "stopping")
                if self._background_task is not None:
                    self._background_task.cancel()
                    try:
                        await self._background_task
                    except asyncio.CancelledError:
                        pass
                await ctx.unregister_llm_tool("echo_tool")
                await super().on_stop(ctx)
                self.order.append("on_stop_after_super")

            async def terminate(self) -> None:
                self.order.append("terminate")
                self.cache.clear()
                self.lifecycle_state = "stopped"
        """,
    )

    harness = PluginHarness.from_plugin_dir(plugin_dir)
    harness.router.upsert_plugin(
        metadata={
            "name": "dependency_plugin",
            "display_name": "Dependency Plugin",
            "description": "dependency metadata",
            "author": "tests",
            "version": "9.9.9",
            "support_platforms": ["discord"],
        },
        config={"token": "dependency-token"},
    )

    plugin = None
    try:
        await harness.start()
        assert harness.loaded_plugin is not None
        assert harness.capability_dispatcher is not None
        assert harness.lifecycle_context is not None
        plugin = harness.loaded_plugin.instances[0]

        await asyncio.wait_for(plugin.background_started.wait(), timeout=0.2)

        assert plugin.context is None
        assert plugin.order == ["initialize", "on_start"]
        assert plugin.cache == {"initialized": True}
        assert plugin.lifecycle_state == "initialized"
        assert plugin.config_snapshot == {
            "api_key": "secret-key",
            "timeout": 7,
            "max_retries": 3,
            "debug": False,
        }
        assert plugin.current_metadata is not None
        assert plugin.current_metadata.name == "lifecycle_plugin"
        assert plugin.current_metadata.display_name == "Lifecycle Plugin"
        assert plugin.current_metadata.support_platforms == [
            "aiocqhttp",
            "telegram",
        ]
        assert plugin.current_metadata.astrbot_version == ">=4.13.0,<5.0.0"
        assert plugin.dependency_metadata is not None
        assert plugin.dependency_metadata.name == "dependency_plugin"
        assert plugin.dependency_metadata.version == "9.9.9"
        assert plugin.rendered_text == "mock://text_to_image/lifecycle_plugin"
        assert plugin.rendered_html == "mock://html_render/startup"

        assert harness.router.db_store["lifecycle_plugin:config_timeout"] == 7
        assert harness.router.db_store["lifecycle_plugin:startup_state"] == "running"
        assert (
            harness.router.db_store["lifecycle_plugin:background_plugin_id"]
            == "lifecycle_plugin"
        )

        tools = await harness.lifecycle_context.get_llm_tool_manager().list_registered()
        assert [tool.name for tool in tools] == ["echo_tool"]

        tool_result = await harness.capability_dispatcher.invoke(
            InvokeMessage(
                id="tool-001",
                capability="internal.llm_tool.execute",
                input={
                    "plugin_id": "lifecycle_plugin",
                    "tool_name": "echo_tool",
                    "tool_args": {"payload": "hello"},
                    "event": harness.build_event_payload(text="tool invocation"),
                },
            ),
            CancelToken(),
        )
        assert tool_result == {
            "content": "tool:hello:lifecycle_plugin",
            "success": True,
        }
        assert harness.router.db_store["lifecycle_plugin:tool_payload"] == "hello"
        assert plugin.context is None

        records = await harness.dispatch_text("state")
        assert [item.text for item in records] == [
            "lifecycle_plugin:9.9.9:1:lifecycle_plugin:7"
        ]
        assert harness.router.db_store["lifecycle_plugin:visits"] == 1
        assert plugin.context is None
    finally:
        await harness.stop()

    assert plugin is not None
    assert plugin.order == [
        "initialize",
        "on_start",
        "on_stop_before_super",
        "terminate",
        "on_stop_after_super",
    ]
    assert plugin.background_cancelled is True
    assert plugin.cache == {}
    assert plugin.lifecycle_state == "stopped"
    assert plugin.context is None
    assert harness.router.db_store["lifecycle_plugin:shutdown_state"] == "stopping"
    assert harness.router._plugins["lifecycle_plugin"].llm_tools == {}


@pytest.mark.asyncio
async def test_star_custom_on_error_and_handler_local_error_handling_behave_at_runtime(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "error_runtime_plugin"
    _write_plugin(
        plugin_dir,
        name="error_runtime_plugin",
        class_name="ErrorRuntimePlugin",
        source="""
        from astrbot_sdk import AstrBotError, Context, MessageEvent, Star
        from astrbot_sdk.decorators import on_command


        class ErrorRuntimePlugin(Star):
            @on_command("caught")
            async def caught(self, event: MessageEvent, ctx: Context) -> None:
                try:
                    raise ValueError("bad arg")
                except ValueError as error:
                    await ctx.db.set("caught_error", str(error))
                    await event.reply(f"参数错误: {error}")

            @on_command("custom_value")
            async def custom_value(self, event: MessageEvent, ctx: Context) -> None:
                del event, ctx
                raise ValueError("bad custom")

            @on_command("custom_astr")
            async def custom_astr(self, event: MessageEvent, ctx: Context) -> None:
                del event, ctx
                raise AstrBotError.capability_not_found("unknown_capability")

            async def on_error(self, error: Exception, event, ctx) -> None:
                await ctx.db.set("on_error_type", type(error).__name__)
                if isinstance(error, AstrBotError):
                    await event.reply(error.hint or error.message)
                elif isinstance(error, ValueError):
                    await event.reply(f"参数错误：{error}")
                else:
                    await event.reply(f"发生错误: {type(error).__name__}")
        """,
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        records = await harness.dispatch_text("caught")
        assert [item.text for item in records] == ["参数错误: bad arg"]
        assert harness.router.db_store["error_runtime_plugin:caught_error"] == "bad arg"

        with pytest.raises(RuntimeError, match="bad custom"):
            await harness.dispatch_text("custom_value")
        assert harness.sent_messages[-1].text == "参数错误：bad custom"
        assert harness.router.db_store["error_runtime_plugin:on_error_type"] == "ValueError"

        with pytest.raises(AstrBotError, match="未找到能力：unknown_capability"):
            await harness.dispatch_text("custom_astr")
        assert (
            harness.sent_messages[-1].text
            == "请确认 AstrBot Core 是否已注册该 capability"
        )
        assert (
            harness.router.db_store["error_runtime_plugin:on_error_type"]
            == "AstrBotError"
        )


@pytest.mark.asyncio
async def test_star_default_on_error_replies_through_real_handler_dispatch(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "default_error_plugin"
    _write_plugin(
        plugin_dir,
        name="default_error_plugin",
        class_name="DefaultErrorPlugin",
        source="""
        from astrbot_sdk import AstrBotError, Context, MessageEvent, Star
        from astrbot_sdk.decorators import on_command


        class DefaultErrorPlugin(Star):
            @on_command("invalid")
            async def invalid(self, event: MessageEvent, ctx: Context) -> None:
                del event, ctx
                raise AstrBotError.invalid_input(
                    "bad payload",
                    hint="check payload",
                    docs_url="https://example.com/docs",
                    details={"b": 2, "a": 1},
                )

            @on_command("unknown")
            async def unknown(self, event: MessageEvent, ctx: Context) -> None:
                del event, ctx
                raise RuntimeError("boom")
        """,
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        with pytest.raises(AstrBotError, match="bad payload"):
            await harness.dispatch_text("invalid")
        assert harness.sent_messages[-1].text is not None
        assert "check payload" in harness.sent_messages[-1].text
        assert "https://example.com/docs" in harness.sent_messages[-1].text
        assert '"a": 1' in harness.sent_messages[-1].text
        assert '"b": 2' in harness.sent_messages[-1].text

        with pytest.raises(RuntimeError, match="boom"):
            await harness.dispatch_text("unknown")
        assert harness.sent_messages[-1].text == "出了点问题，请联系插件作者"
