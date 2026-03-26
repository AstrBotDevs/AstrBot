from __future__ import annotations

import asyncio
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace

import pytest

from astrbot_sdk._internal.testing_support import MockCapabilityRouter, MockPeer
from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.conversation import (
    ConversationClosed,
    ConversationReplaced,
    ConversationSession,
)
from astrbot_sdk.decorators import ConversationMeta
from astrbot_sdk.errors import AstrBotError, ErrorCodes
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.protocol.descriptors import CommandTrigger, HandlerDescriptor
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.runtime.loader import LoadedHandler
from astrbot_sdk.star import Star
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
        "\n".join(
            [
                "_schema_version: 2",
                f"name: {name}",
                "author: tests",
                "version: 1.0.0",
                "desc: error handling runtime tests",
                "runtime:",
                '  python: "3.12"',
                "",
                "components:",
                f"  - class: main:{class_name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "main.py").write_text(dedent(source).lstrip(), encoding="utf-8")


def _event_payload(
    text: str,
    *,
    session_id: str = "demo:private:user-1",
) -> dict[str, object]:
    return {
        "text": text,
        "session_id": session_id,
        "user_id": "user-1",
        "group_id": None,
        "platform": "demo",
        "platform_id": "demo",
        "message_type": "private",
        "raw": {"event_type": "message"},
    }


async def _invoke_handler(
    dispatcher: HandlerDispatcher,
    *,
    handler_id: str,
    text: str,
    request_id: str,
    session_id: str = "demo:private:user-1",
) -> dict[str, object]:
    return await dispatcher.invoke(
        SimpleNamespace(
            id=request_id,
            input={
                "handler_id": handler_id,
                "event": _event_payload(text, session_id=session_id),
                "args": {},
            },
        ),
        CancelToken(),
    )


@pytest.mark.asyncio
async def test_error_handling_runtime_basic_pattern_and_custom_on_error(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "error_runtime_plugin"
    _write_plugin(
        plugin_dir,
        name="error_runtime_plugin",
        class_name="ErrorRuntimePlugin",
        source="""
        from astrbot_sdk import Context, MessageEvent, Star
        from astrbot_sdk.decorators import on_command
        from astrbot_sdk.errors import AstrBotError


        class ErrorRuntimePlugin(Star):
            @on_command("basic")
            async def basic(self, event: MessageEvent, ctx: Context) -> None:
                try:
                    await ctx._proxy.call("unknown.capability", {})
                except AstrBotError as error:
                    await ctx.db.set("basic_error_code", error.code)
                    ctx.logger.error("basic failed: {}", error)
                    await event.reply(error.hint or error.message)

            @on_command("unexpected")
            async def unexpected(self, event: MessageEvent, ctx: Context) -> None:
                del event, ctx
                raise ValueError("boom")

            async def on_error(self, error: Exception, event, ctx) -> None:
                await ctx.db.set("last_on_error_type", type(error).__name__)
                if isinstance(error, AstrBotError):
                    await event.reply(error.hint or error.message)
                elif isinstance(error, ValueError):
                    ctx.logger.exception("unexpected runtime error")
                    await event.reply(f"参数错误: {error}")
                else:
                    await event.reply("发生未知错误，请联系管理员")
        """,
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        records = await harness.dispatch_text("basic")
        assert [item.text for item in records] == [
            "请确认 AstrBot Core 是否已注册该 capability"
        ]
        assert (
            harness.router.db_store["error_runtime_plugin:basic_error_code"]
            == ErrorCodes.CAPABILITY_NOT_FOUND
        )

        with pytest.raises(RuntimeError, match="boom"):
            await harness.dispatch_text("unexpected")

        assert harness.sent_messages[-1].text == "参数错误: boom"
        assert (
            harness.router.db_store["error_runtime_plugin:last_on_error_type"]
            == "ValueError"
        )


@pytest.mark.asyncio
async def test_error_handling_runtime_limiter_errors_surface_real_metadata_and_replies(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "limiter_error_plugin"
    _write_plugin(
        plugin_dir,
        name="limiter_error_plugin",
        class_name="LimiterErrorPlugin",
        source="""
        from astrbot_sdk import Context, MessageEvent, Star
        from astrbot_sdk.decorators import cooldown, on_command, rate_limit
        from astrbot_sdk.errors import AstrBotError, ErrorCodes


        class LimiterErrorPlugin(Star):
            @rate_limit(
                1,
                60,
                behavior="error",
                message="操作过于频繁，请 {remaining_seconds}s 后再试",
            )
            @on_command("rate")
            async def rate(self, event: MessageEvent, ctx: Context) -> None:
                await event.reply("rate ok")

            @cooldown(
                30,
                behavior="error",
                message="命令冷却中，请 {remaining_seconds}s 后再试",
            )
            @on_command("cool")
            async def cool(self, event: MessageEvent, ctx: Context) -> None:
                await event.reply("cool ok")

            async def on_error(self, error: Exception, event, ctx) -> None:
                if isinstance(error, AstrBotError):
                    await ctx.db.set(f"last:{error.code}", error.details or {})
                    if error.code == ErrorCodes.RATE_LIMITED:
                        retry_after = int(error.details.get("remaining_seconds", 0))
                        await event.reply(f"rate:{retry_after}")
                    elif error.code == ErrorCodes.COOLDOWN_ACTIVE:
                        remaining = int(error.details.get("remaining_seconds", 0))
                        await event.reply(f"cool:{remaining}")
                    else:
                        await event.reply(error.hint or error.message)
        """,
    )

    async with PluginHarness.from_plugin_dir(plugin_dir) as harness:
        first_rate = await harness.dispatch_text("rate")
        assert [item.text for item in first_rate] == ["rate ok"]

        with pytest.raises(AstrBotError) as rate_exc:
            await harness.dispatch_text("rate")

        assert rate_exc.value.code == ErrorCodes.RATE_LIMITED
        assert harness.sent_messages[-1].text is not None
        assert harness.sent_messages[-1].text.startswith("rate:")
        rate_details = harness.router.db_store["limiter_error_plugin:last:rate_limited"]
        assert rate_details["handler_id"].endswith(".rate")
        assert rate_details["remaining_seconds"] > 0

        first_cool = await harness.dispatch_text("cool")
        assert [item.text for item in first_cool] == ["cool ok"]

        with pytest.raises(AstrBotError) as cool_exc:
            await harness.dispatch_text("cool")

        assert cool_exc.value.code == ErrorCodes.COOLDOWN_ACTIVE
        assert harness.sent_messages[-1].text is not None
        assert harness.sent_messages[-1].text.startswith("cool:")
        cooldown_details = harness.router.db_store[
            "limiter_error_plugin:last:cooldown_active"
        ]
        assert cooldown_details["handler_id"].endswith(".cool")
        assert cooldown_details["remaining_seconds"] > 0


@pytest.mark.asyncio
async def test_error_handling_runtime_conversation_replaced_and_closed_are_observable() -> (
    None
):
    peer = MockPeer(MockCapabilityRouter())

    class ConversationOwner(Star):
        async def survey(
            self,
            event: MessageEvent,
            conversation: ConversationSession,
            ctx: Context,
        ) -> None:
            was_replaced = False
            try:
                answer = await conversation.ask("问题?")
                await ctx.db.set("answer", answer.text)
                await event.reply(f"收到:{answer.text}")
            except ConversationReplaced:
                was_replaced = True
                await ctx.db.set("replaced", True)
                await event.reply("已切换到新对话")
            finally:
                if was_replaced:
                    try:
                        await conversation.reply("stale")
                    except ConversationClosed:
                        await ctx.db.set("stale_closed", True)

    owner = ConversationOwner()
    handler_id = "conversation_error_plugin:test.survey"
    dispatcher = HandlerDispatcher(
        plugin_id="conversation_error_plugin",
        peer=peer,
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id=handler_id,
                    trigger=CommandTrigger(command="survey"),
                ),
                callable=owner.survey,
                owner=owner,
                plugin_id="conversation_error_plugin",
                conversation=ConversationMeta(
                    timeout=60,
                    mode="replace",
                    busy_message=None,
                    grace_period=0.05,
                ),
            )
        ],
    )

    first = await _invoke_handler(
        dispatcher,
        handler_id=handler_id,
        text="survey",
        request_id="survey-1",
    )
    assert first == {"sent_message": False, "stop": True, "call_llm": False}

    await asyncio.sleep(0)
    await asyncio.sleep(0)
    second = await _invoke_handler(
        dispatcher,
        handler_id=handler_id,
        text="survey",
        request_id="survey-2",
    )
    assert second == {"sent_message": False, "stop": True, "call_llm": False}

    waiter_result = await dispatcher.invoke(
        SimpleNamespace(
            id="survey-waiter",
            input={
                "handler_id": "__sdk_session_waiter__",
                "event": _event_payload("42"),
                "args": {},
            },
        ),
        CancelToken(),
    )
    assert waiter_result["sent_message"] is False
    assert waiter_result["call_llm"] is False

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    sent_texts = [item.text for item in peer._router.platform_sink.records]  # noqa: SLF001
    assert sent_texts.count("问题?") == 2
    assert "已切换到新对话" in sent_texts
    assert "收到:42" in sent_texts
    assert peer._router.db_store["conversation_error_plugin:replaced"] is True  # noqa: SLF001
    assert peer._router.db_store["conversation_error_plugin:stale_closed"] is True  # noqa: SLF001
    assert peer._router.db_store["conversation_error_plugin:answer"] == "42"  # noqa: SLF001


@pytest.mark.asyncio
async def test_error_handling_runtime_on_error_failure_does_not_recurse() -> None:
    peer = MockPeer(MockCapabilityRouter())

    class OnErrorFailureOwner(Star):
        async def explode(self, event: MessageEvent, ctx: Context) -> None:
            del event, ctx
            raise ValueError("boom")

        async def on_error(self, error: Exception, event, ctx) -> None:
            del event
            count = await ctx.db.get("on_error_calls")
            if count is None:
                count = 0
            await ctx.db.set("on_error_calls", count + 1)
            raise RuntimeError(f"on_error failed: {error}")

    owner = OnErrorFailureOwner()
    handler_id = "on_error_failure_plugin:test.explode"
    dispatcher = HandlerDispatcher(
        plugin_id="on_error_failure_plugin",
        peer=peer,
        handlers=[
            LoadedHandler(
                descriptor=HandlerDescriptor(
                    id=handler_id,
                    trigger=CommandTrigger(command="explode"),
                ),
                callable=owner.explode,
                owner=owner,
                plugin_id="on_error_failure_plugin",
            )
        ],
    )

    with pytest.raises(RuntimeError, match="on_error failed: boom"):
        await _invoke_handler(
            dispatcher,
            handler_id=handler_id,
            text="explode",
            request_id="explode-1",
        )

    assert peer._router.platform_sink.records == []  # noqa: SLF001
    assert peer._router.db_store["on_error_failure_plugin:on_error_calls"] == 1  # noqa: SLF001
