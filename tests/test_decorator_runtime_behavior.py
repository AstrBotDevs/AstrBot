from __future__ import annotations

import asyncio
import json
from pathlib import Path
from textwrap import dedent

import pytest

from astrbot_sdk._internal.testing_support import MockCapabilityRouter, MockPeer
from astrbot_sdk.context import CancelToken
from astrbot_sdk.errors import AstrBotError, ErrorCodes
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.loader import load_plugin, load_plugin_spec, validate_plugin_spec
from astrbot_sdk.testing import PluginHarness


def _write_plugin(
    plugin_dir: Path,
    *,
    name: str,
    class_name: str,
    source: str,
) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.yaml").write_text(
        dedent(
            f"""
            _schema_version: 2
            name: {name}
            author: tests
            version: 1.0.0
            desc: decorator runtime behavior tests

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


def _message_event_payload(
    text: str,
    *,
    session_id: str = "demo:private:user-1",
    platform: str = "demo",
    user_id: str = "user-1",
    group_id: str | None = None,
    is_admin: bool = False,
) -> dict[str, object]:
    return {
        "type": "message",
        "event_type": "message",
        "text": text,
        "session_id": session_id,
        "user_id": user_id,
        "group_id": group_id,
        "platform": platform,
        "platform_id": platform,
        "message_type": "group" if group_id else "private",
        "self_id": f"{platform}-bot",
        "sender_name": user_id,
        "is_admin": is_admin,
        "raw": {"event_type": "message"},
    }


def _schedule_event_payload(
    *,
    plugin_id: str,
    handler_id: str,
    trigger_kind: str,
    interval_seconds: int | None = None,
    cron: str | None = None,
) -> dict[str, object]:
    return {
        "type": "schedule",
        "event_type": "schedule",
        "text": "",
        "session_id": "",
        "user_id": "",
        "group_id": None,
        "platform": "",
        "platform_id": "",
        "message_type": "other",
        "self_id": "scheduler",
        "sender_name": "scheduler",
        "raw": {"event_type": "schedule"},
        "schedule": {
            "schedule_id": f"{plugin_id}:{handler_id}",
            "plugin_id": plugin_id,
            "handler_id": handler_id,
            "trigger_kind": trigger_kind,
            "interval_seconds": interval_seconds,
            "cron": cron,
            "scheduled_at": "2026-03-26T10:00:00+00:00",
        },
    }


def _load_dispatcher(
    plugin_dir: Path,
) -> tuple[str, object, MockCapabilityRouter, HandlerDispatcher]:
    plugin = load_plugin_spec(plugin_dir)
    validate_plugin_spec(plugin)
    loaded = load_plugin(plugin)
    router = MockCapabilityRouter()
    peer = MockPeer(router)
    dispatcher = HandlerDispatcher(
        plugin_id=plugin.name,
        peer=peer,
        handlers=loaded.handlers,
    )
    return plugin.name, loaded, router, dispatcher


async def _invoke_dispatcher_handler(
    dispatcher: HandlerDispatcher,
    *,
    handler_id: str,
    event_payload: dict[str, object],
    request_id: str,
) -> dict[str, object]:
    return await dispatcher.invoke(
        InvokeMessage(
            id=request_id,
            capability="handler.invoke",
            input={
                "handler_id": handler_id,
                "event": dict(event_payload),
                "args": {},
            },
        ),
        CancelToken(),
    )


@pytest.mark.asyncio
async def test_trigger_decorators_dispatch_through_real_plugin_runtime(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "trigger_runtime_plugin"
    _write_plugin(
        plugin_dir,
        name="trigger_runtime_plugin",
        class_name="TriggerRuntimePlugin",
        source="""
        from astrbot_sdk import Context, MessageEvent, ScheduleContext, Star
        from astrbot_sdk.decorators import on_command, on_event, on_message, on_schedule


        class TriggerRuntimePlugin(Star):
            @on_command(["hello", "repeat"], aliases=["say"])
            async def hello(self, event: MessageEvent, text: str, ctx: Context) -> None:
                del ctx
                await event.reply(f"command:{text}")

            @on_message(keywords=["help", "帮助"])
            async def help_handler(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("keyword-help")

            @on_message(regex=r"order-(?P<code>\\d+)")
            async def regex_handler(
                self,
                event: MessageEvent,
                code: str,
                ctx: Context,
            ) -> None:
                del ctx
                await event.reply(f"regex:{code}")

            @on_message(keywords=["weather"], platforms=["qq"], message_types=["private"])
            async def weather_handler(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("weather-private")

            @on_event("group_member_join")
            async def join_handler(self, event: MessageEvent, ctx: Context) -> None:
                await ctx.platform.send(event.session_id, f"join:{event.user_id}")

            @on_schedule(interval_seconds=30)
            async def interval_job(self, ctx: Context, schedule: ScheduleContext) -> None:
                await ctx.platform.send(
                    "scheduler:private:watcher",
                    f"interval:{schedule.interval_seconds}",
                )

            @on_schedule(cron="0 8 * * *")
            async def cron_job(self, ctx: Context, schedule: ScheduleContext) -> None:
                await ctx.platform.send(
                    "scheduler:private:watcher",
                    f"cron:{schedule.cron}",
                )
        """,
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        repeat_records = await harness.dispatch_text("repeat once more")
        alias_records = await harness.dispatch_text("say hello-again")
        keyword_records = await harness.dispatch_text("please help me")
        regex_records = await harness.dispatch_text("order-2048")
        weather_records = await harness.dispatch_text("weather Shanghai", platform="qq")

        with pytest.raises(AstrBotError, match="未找到匹配的 handler"):
            await harness.dispatch_text("weather Shanghai", platform="wechat")

        join_records = await harness.dispatch_event(
            {
                "type": "group_member_join",
                "event_type": "group_member_join",
                "text": "",
                "session_id": "qq:group:room-9",
                "user_id": "member-7",
                "group_id": "room-9",
                "platform": "qq",
                "platform_id": "qq",
                "message_type": "group",
                "self_id": "qq-bot",
                "sender_name": "member-7",
                "raw": {"event_type": "group_member_join"},
            }
        )

        assert harness.loaded_plugin is not None
        handler_ids = {
            handler.descriptor.id.rsplit(".", 1)[-1]: handler.descriptor.id
            for handler in harness.loaded_plugin.handlers
        }
        interval_records = await harness.dispatch_event(
            _schedule_event_payload(
                plugin_id="trigger_runtime_plugin",
                handler_id=handler_ids["interval_job"],
                trigger_kind="interval",
                interval_seconds=30,
            )
        )
        cron_records = await harness.dispatch_event(
            _schedule_event_payload(
                plugin_id="trigger_runtime_plugin",
                handler_id=handler_ids["cron_job"],
                trigger_kind="cron",
                cron="0 8 * * *",
            )
        )

    assert [record.text for record in repeat_records] == ["command:once more"]
    assert [record.text for record in alias_records] == ["command:hello-again"]
    assert [record.text for record in keyword_records] == ["keyword-help"]
    assert [record.text for record in regex_records] == ["regex:2048"]
    assert [record.text for record in weather_records] == ["weather-private"]
    assert [record.text for record in join_records] == ["join:member-7"]
    assert [record.text for record in interval_records] == ["interval:30"]
    assert [record.text for record in cron_records] == ["cron:0 8 * * *"]


@pytest.mark.asyncio
async def test_filter_and_permission_decorators_gate_real_dispatch(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "filter_permission_runtime_plugin"
    _write_plugin(
        plugin_dir,
        name="filter_permission_runtime_plugin",
        class_name="FilterPermissionRuntimePlugin",
        source="""
        from astrbot_sdk import Context, MessageEvent, Star
        from astrbot_sdk.decorators import (
            admin_only,
            group_only,
            message_types,
            on_command,
            platforms,
            private_only,
            require_admin,
            require_permission,
        )


        class FilterPermissionRuntimePlugin(Star):
            @on_command("require-admin")
            @require_admin
            async def require_admin_command(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("require-admin")

            @on_command("admin-only")
            @admin_only
            async def admin_only_command(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("admin-only")

            @on_command("member-role")
            @require_permission("member")
            async def member_role_command(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("member-role")

            @on_command("qq-only")
            @platforms("qq")
            async def qq_only_command(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("qq-only")

            @on_command("group-type")
            @message_types("group")
            async def group_type_command(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("group-type")

            @on_command("group-only")
            @group_only()
            async def group_only_command(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("group-only")

            @on_command("private-only")
            @private_only()
            async def private_only_command(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("private-only")
        """,
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        with pytest.raises(AstrBotError, match="未找到匹配的 handler"):
            await harness.dispatch_text("require-admin")

        admin_payload = harness.build_event_payload(text="require-admin")
        admin_payload["is_admin"] = True
        require_admin_records = await harness.dispatch_event(admin_payload)

        alias_admin_payload = harness.build_event_payload(text="admin-only")
        alias_admin_payload["is_admin"] = True
        admin_only_records = await harness.dispatch_event(alias_admin_payload)

        member_records = await harness.dispatch_text("member-role")
        qq_only_records = await harness.dispatch_text("qq-only", platform="qq")
        group_type_records = await harness.dispatch_text(
            "group-type",
            session_id="demo:group:room-7",
            group_id="room-7",
        )
        group_only_records = await harness.dispatch_text(
            "group-only",
            session_id="demo:group:room-7",
            group_id="room-7",
        )
        private_only_records = await harness.dispatch_text("private-only")

        with pytest.raises(AstrBotError, match="未找到匹配的 handler"):
            await harness.dispatch_text("qq-only", platform="wechat")

        with pytest.raises(AstrBotError, match="未找到匹配的 handler"):
            await harness.dispatch_text("group-type")

        with pytest.raises(AstrBotError, match="未找到匹配的 handler"):
            await harness.dispatch_text("group-only")

        with pytest.raises(AstrBotError, match="未找到匹配的 handler"):
            await harness.dispatch_text(
                "private-only",
                session_id="demo:group:room-7",
                group_id="room-7",
            )

    assert [record.text for record in require_admin_records] == ["require-admin"]
    assert [record.text for record in admin_only_records] == ["admin-only"]
    assert [record.text for record in member_records] == ["member-role"]
    assert [record.text for record in qq_only_records] == ["qq-only"]
    assert [record.text for record in group_type_records] == ["group-type"]
    assert [record.text for record in group_only_records] == ["group-only"]
    assert [record.text for record in private_only_records] == ["private-only"]


@pytest.mark.asyncio
async def test_limiter_and_priority_decorators_apply_runtime_behavior(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "limiter_priority_runtime_plugin"
    _write_plugin(
        plugin_dir,
        name="limiter_priority_runtime_plugin",
        class_name="LimiterPriorityRuntimePlugin",
        source="""
        from astrbot_sdk import Context, MessageEvent, Star
        from astrbot_sdk.decorators import cooldown, on_command, priority, rate_limit


        class LimiterPriorityRuntimePlugin(Star):
            @on_command("burst")
            @rate_limit(1, 60, message="too fast")
            async def burst(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("burst-ok")

            @on_command("skill")
            @cooldown(30, behavior="error", message="cooling {remaining_seconds}s")
            async def skill(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("skill-ok")

            @on_command("chain")
            @priority(10)
            async def high_priority(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("high")
                event.stop_event()

            @on_command("chain")
            @priority(1)
            async def low_priority(self, event: MessageEvent, ctx: Context) -> None:
                del ctx
                await event.reply("low")
        """,
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        first_burst_records = await harness.dispatch_text("burst")
        second_burst_records = await harness.dispatch_text("burst")
        first_skill_records = await harness.dispatch_text("skill")
        with pytest.raises(AstrBotError) as exc_info:
            await harness.dispatch_text("skill")
        chain_records = await harness.dispatch_text("chain")

    assert [record.text for record in first_burst_records] == ["burst-ok"]
    assert [record.text for record in second_burst_records] == ["too fast"]
    assert [record.text for record in first_skill_records] == ["skill-ok"]
    assert exc_info.value.code == ErrorCodes.COOLDOWN_ACTIVE
    assert exc_info.value.hint == "cooling 30s"
    assert [record.text for record in chain_records] == ["high"]


@pytest.mark.asyncio
async def test_conversation_command_reject_mode_uses_real_dispatcher_waiter_flow(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "conversation_runtime_plugin"
    _write_plugin(
        plugin_dir,
        name="conversation_runtime_plugin",
        class_name="ConversationRuntimePlugin",
        source="""
        from astrbot_sdk import Context, ConversationSession, MessageEvent, Star
        from astrbot_sdk.decorators import conversation_command


        class ConversationRuntimePlugin(Star):
            @conversation_command(
                "survey",
                timeout=30,
                mode="reject",
                busy_message="busy now",
            )
            async def survey(
                self,
                event: MessageEvent,
                ctx: Context,
                conversation: ConversationSession,
            ) -> None:
                del event, ctx
                answer = await conversation.ask("name?")
                await conversation.reply(f"name:{answer.text}")
                conversation.end()
        """,
    )

    plugin_id, loaded, router, dispatcher = _load_dispatcher(plugin_dir)
    handler_id = next(
        handler.descriptor.id
        for handler in loaded.handlers
        if handler.descriptor.id.endswith(".survey")
    )

    first_summary = await _invoke_dispatcher_handler(
        dispatcher,
        handler_id=handler_id,
        event_payload=_message_event_payload(
            "survey",
            session_id="demo:private:survey-user",
        ),
        request_id="survey-1",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    second_summary = await _invoke_dispatcher_handler(
        dispatcher,
        handler_id=handler_id,
        event_payload=_message_event_payload(
            "survey",
            session_id="demo:private:survey-user",
        ),
        request_id="survey-2",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    waiter_summary = await dispatcher.invoke(
        InvokeMessage(
            id="survey-waiter",
            capability="handler.invoke",
            input={
                "handler_id": "__sdk_session_waiter__",
                "event": _message_event_payload(
                    "Alice",
                    session_id="demo:private:survey-user",
                ),
                "args": {},
            },
        ),
        CancelToken(),
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert plugin_id == "conversation_runtime_plugin"
    assert first_summary["stop"] is True
    assert second_summary["stop"] is True
    assert waiter_summary["sent_message"] is False
    assert [record.text for record in router.platform_sink.records] == [
        "name?",
        "busy now",
        "name:Alice",
    ]


@pytest.mark.asyncio
async def test_register_llm_tool_and_register_agent_flow_through_runtime_capabilities(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "tool_agent_runtime_plugin"
    _write_plugin(
        plugin_dir,
        name="tool_agent_runtime_plugin",
        class_name="ToolAgentRuntimePlugin",
        source="""
        from astrbot_sdk import Context, MessageEvent, Star
        from astrbot_sdk.decorators import register_agent, register_llm_tool
        from astrbot_sdk.llm.agents import BaseAgentRunner
        from astrbot_sdk.llm.entities import ProviderRequest


        class ToolAgentRuntimePlugin(Star):
            @register_llm_tool()
            async def get_weather(
                self,
                event: MessageEvent,
                ctx: Context,
                city: str,
                unit: str = "celsius",
            ):
                '''Get weather for a city.'''
                return {
                    "city": city,
                    "unit": unit,
                    "plugin": ctx.plugin_id,
                    "session": event.session_id,
                }


        @register_agent(
            "helper_agent",
            description="Agent metadata for runtime registry",
            tool_names=["get_weather"],
        )
        class HelperAgent(BaseAgentRunner):
            async def run(self, ctx: Context, request: ProviderRequest):
                return {"plugin": ctx.plugin_id, "prompt": request.prompt}
        """,
    )

    harness = PluginHarness.from_plugin_dir(plugin_dir)
    await harness.start()
    try:
        assert harness.lifecycle_context is not None
        assert harness.capability_dispatcher is not None

        registered_tools = await harness.lifecycle_context.get_llm_tool_manager().list_registered()
        active_tools = await harness.lifecycle_context.get_llm_tool_manager().list_active()

        assert [tool.name for tool in registered_tools] == ["get_weather"]
        assert [tool.name for tool in active_tools] == ["get_weather"]
        assert registered_tools[0].description == "Get weather for a city."
        assert registered_tools[0].parameters_schema == {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "unit": {"type": "string"},
            },
            "required": ["city"],
        }

        tool_result = await harness.capability_dispatcher.invoke(
            InvokeMessage(
                id="tool-run-1",
                capability="internal.llm_tool.execute",
                input={
                    "plugin_id": "tool_agent_runtime_plugin",
                    "tool_name": "get_weather",
                    "tool_args": {"city": "Paris"},
                    "event": harness.build_event_payload(
                        text="tool",
                        session_id="demo:private:tool-session",
                    ),
                },
            ),
            CancelToken(),
        )
        assert json.loads(str(tool_result["content"])) == {
            "city": "Paris",
            "unit": "celsius",
            "plugin": "tool_agent_runtime_plugin",
            "session": "demo:private:tool-session",
        }

        no_tool_loop = await harness.lifecycle_context.tool_loop_agent(prompt="forecast")
        assert "tools=get_weather" in no_tool_loop.text

        assert await harness.lifecycle_context.deactivate_llm_tool("get_weather") is True
        without_active_tool = await harness.lifecycle_context.tool_loop_agent(
            prompt="forecast"
        )
        assert "tools=get_weather" not in without_active_tool.text

        assert await harness.lifecycle_context.activate_llm_tool("get_weather") is True
        with_active_tool = await harness.lifecycle_context.tool_loop_agent(
            prompt="forecast"
        )
        assert "tools=get_weather" in with_active_tool.text

        agent_list = await harness.lifecycle_context._proxy.call("agent.registry.list", {})
        agent_get = await harness.lifecycle_context._proxy.call(
            "agent.registry.get",
            {"name": "helper_agent"},
        )

        assert agent_list == {
            "agents": [
                {
                    "name": "helper_agent",
                    "description": "Agent metadata for runtime registry",
                    "tool_names": ["get_weather"],
                    "runner_class": "main.HelperAgent",
                }
            ]
        }
        assert agent_get == {
            "agent": {
                "name": "helper_agent",
                "description": "Agent metadata for runtime registry",
                "tool_names": ["get_weather"],
                "runner_class": "main.HelperAgent",
            }
        }
    finally:
        await harness.stop()
