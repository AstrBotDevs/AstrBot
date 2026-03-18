# ruff: noqa: E402
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from textwrap import dedent

import pytest

from astrbot_sdk.context import CancelToken
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.testing import MockContext, PluginHarness


def _write_p1_4_plugin(tmp_path: Path) -> Path:
    plugin_dir = tmp_path / "p1_4_compat_plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "requirements.txt").write_text("", encoding="utf-8")
    (plugin_dir / "plugin.yaml").write_text(
        dedent(
            """
            name: p1_4_compat_plugin
            author: sdk-tests
            desc: P1.4 compatibility plugin
            version: 1.0.0
            astrbot_version: ">=1.0.0"
            support_platforms:
              - mock
              - qq
            runtime:
              python: "3.11"
            components:
              - class: main:CompatPlugin
            """
        ).strip(),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        dedent(
            """
            import asyncio

            from astrbot_sdk import Context, MessageEvent, Star, StarTools, on_command


            class CompatPlugin(Star):
                async def initialize(self) -> None:
                    meta = await self.context.metadata.get_current_plugin()
                    await self.put_kv_data("started", self.plugin_id)
                    await self.put_kv_data(
                        "meta_platforms",
                        ",".join(meta.support_platforms),
                    )
                    await self.put_kv_data(
                        "meta_version",
                        meta.astrbot_version or "",
                    )
                    await StarTools.send_message(
                        "mock-platform:private:init-user",
                        "boot",
                    )

                async def terminate(self) -> None:
                    await self.put_kv_data("stopped", self.plugin_id)

                async def _record_context(self, key: str) -> None:
                    await asyncio.sleep(0)
                    await self.put_kv_data(
                        key,
                        self.context.plugin_id if self.context else "missing",
                    )

                async def dynamic_note(
                    self,
                    event: MessageEvent | None = None,
                    ctx: Context | None = None,
                    word: str = "",
                ) -> dict[str, str]:
                    return {
                        "plugin_id": self.plugin_id,
                        "ctx_plugin": ctx.plugin_id if ctx else "",
                        "ctx_matches": str(self.context is ctx),
                        "star_tools_matches": str(StarTools._context is ctx),
                        "session": event.session_id if event else "",
                        "word": word,
                    }

                @on_command("compat")
                async def compat(self, event: MessageEvent, ctx: Context) -> None:
                    await self.put_kv_data(
                        "handler_ctx",
                        ctx.plugin_id if self.context is ctx else "mismatch",
                    )
                    await self.put_kv_data(
                        "startools_ctx",
                        ctx.plugin_id if StarTools._context is ctx else "mismatch",
                    )
                    asyncio.create_task(self._record_context("task_ctx"))
                    await ctx.register_task(
                        self._record_context("registered_task_ctx"),
                        "inherit runtime context",
                    )
                    meta = await ctx.metadata.get_current_plugin()
                    await self.put_kv_data(
                        "handler_platforms",
                        ",".join(meta.support_platforms),
                    )
                    await self.put_kv_data(
                        "handler_version",
                        meta.astrbot_version or "",
                    )
                    await StarTools.send_message(event.session_id, "compat-message")
                    await StarTools.send_message_by_id(
                        "private",
                        "user-2",
                        "by-id",
                        platform="mock-platform",
                    )
                    await event.reply("compat-ok")

                @on_command("isolate")
                async def isolate(
                    self,
                    event: MessageEvent,
                    ctx: Context,
                    tag: str,
                ) -> None:
                    await asyncio.sleep(0.01)
                    await event.reply(
                        f"isolate:{tag}:{self.context is ctx}:{ctx.plugin_id}"
                    )

                @on_command("toolreg")
                async def toolreg(self, event: MessageEvent, ctx: Context) -> None:
                    await StarTools.register_llm_tool(
                        "note_tool",
                        {
                            "type": "object",
                            "properties": {"word": {"type": "string"}},
                        },
                        "dynamic note tool",
                        self.dynamic_note,
                        active=True,
                    )
                    tool = await ctx.get_llm_tool_manager().get("note_tool")
                    await event.reply(f"toolreg:{tool is not None}")

                @on_command("toolrm")
                async def toolrm(self, event: MessageEvent) -> None:
                    removed = await StarTools.unregister_llm_tool("note_tool")
                    await event.reply(f"toolrm:{removed}")
            """
        ).strip(),
        encoding="utf-8",
    )
    return plugin_dir


async def _wait_for_db_value(
    ctx, key: str, expected: str, timeout: float = 1.0
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await ctx.db.get(key) == expected:
            return
        await asyncio.sleep(0)
    assert await ctx.db.get(key) == expected


def _record_text(item) -> str | None:
    if item.text is not None:
        return item.text
    chain = item.chain or []
    if len(chain) != 1:
        return None
    chunk = chain[0]
    data = chunk.get("data")
    if str(chunk.get("type", "")).lower() != "text" or not isinstance(data, dict):
        return None
    text = data.get("text")
    return text if isinstance(text, str) else None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mock_context_p1_4_metadata_and_send_helpers() -> None:
    ctx = MockContext(
        plugin_id="sdk-demo",
        plugin_metadata={
            "support_platforms": ["mock", "qq"],
            "astrbot_version": ">=1.0.0",
        },
    )

    meta = await ctx.metadata.get_current_plugin()
    assert meta is not None
    assert meta.support_platforms == ["mock", "qq"]
    assert meta.astrbot_version == ">=1.0.0"

    await ctx.send_message("mock-platform:private:user-1", "hello compat")
    assert ctx.sent_messages[-1].session_id == "mock-platform:private:user-1"
    assert _record_text(ctx.sent_messages[-1]) == "hello compat"

    await ctx.send_message_by_id(
        "private",
        "user-2",
        "hello by id",
        platform="mock-platform",
    )
    assert ctx.sent_messages[-1].session_id == "mock-platform:private:user-2"
    assert _record_text(ctx.sent_messages[-1]) == "hello by id"

    with pytest.raises(AstrBotError, match="explicit platform"):
        await ctx.send_message_by_id("private", "user-3", "bad", platform="")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plugin_harness_p1_4_star_context_kv_and_startools(
    tmp_path: Path,
) -> None:
    plugin_dir = _write_p1_4_plugin(tmp_path)
    harness = PluginHarness.from_plugin_dir(plugin_dir)
    await harness.start()

    assert harness.lifecycle_context is not None
    assert await harness.lifecycle_context.db.get("started") == "p1_4_compat_plugin"
    assert await harness.lifecycle_context.db.get("meta_platforms") == "mock,qq"
    assert await harness.lifecycle_context.db.get("meta_version") == ">=1.0.0"
    assert any(
        item.session_id == "mock-platform:private:init-user"
        and _record_text(item) == "boot"
        for item in harness.sent_messages
    )

    await harness.dispatch_text("compat")
    await _wait_for_db_value(
        harness.lifecycle_context,
        "handler_ctx",
        "p1_4_compat_plugin",
    )
    await _wait_for_db_value(
        harness.lifecycle_context,
        "startools_ctx",
        "p1_4_compat_plugin",
    )
    await _wait_for_db_value(
        harness.lifecycle_context, "task_ctx", "p1_4_compat_plugin"
    )
    await _wait_for_db_value(
        harness.lifecycle_context,
        "registered_task_ctx",
        "p1_4_compat_plugin",
    )
    assert await harness.lifecycle_context.db.get("handler_platforms") == "mock,qq"
    assert await harness.lifecycle_context.db.get("handler_version") == ">=1.0.0"
    assert any(
        item.session_id == "local-session" and _record_text(item) == "compat-message"
        for item in harness.sent_messages
    )
    assert any(
        item.session_id == "mock-platform:private:user-2"
        and _record_text(item) == "by-id"
        for item in harness.sent_messages
    )
    assert any(
        item.session_id == "local-session" and _record_text(item) == "compat-ok"
        for item in harness.sent_messages
    )

    alpha, beta = await asyncio.gather(
        harness.dispatch_text("isolate alpha", session_id="session-alpha"),
        harness.dispatch_text("isolate beta", session_id="session-beta"),
    )
    alpha_texts = [text for item in alpha if (text := _record_text(item)) is not None]
    beta_texts = [text for item in beta if (text := _record_text(item)) is not None]
    assert "isolate:alpha:True:p1_4_compat_plugin" in alpha_texts
    assert "isolate:beta:True:p1_4_compat_plugin" in beta_texts

    await harness.stop()
    assert await harness.lifecycle_context.db.get("stopped") == "p1_4_compat_plugin"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_plugin_harness_p1_4_dynamic_llm_tool_register_and_unregister(
    tmp_path: Path,
) -> None:
    plugin_dir = _write_p1_4_plugin(tmp_path)
    harness = PluginHarness.from_plugin_dir(plugin_dir)
    await harness.start()

    assert harness.capability_dispatcher is not None
    assert harness.lifecycle_context is not None

    replies = await harness.dispatch_text("toolreg")
    assert any(_record_text(item) == "toolreg:True" for item in replies)

    manager = harness.lifecycle_context.get_llm_tool_manager()
    tool = await manager.get("note_tool")
    assert tool is not None
    assert tool.handler_ref == "__dynamic_llm_tool__:note_tool"

    output = await harness.capability_dispatcher.invoke(
        InvokeMessage(
            id="tool-1",
            capability="internal.llm_tool.execute",
            input={
                "plugin_id": "p1_4_compat_plugin",
                "tool_name": "note_tool",
                "handler_ref": tool.handler_ref,
                "tool_args": {"word": "hello"},
                "event": {"session_id": "tool-session", "text": "tool event"},
            },
        ),
        CancelToken(),
    )
    payload = json.loads(str(output["content"]))
    assert payload == {
        "plugin_id": "p1_4_compat_plugin",
        "ctx_plugin": "p1_4_compat_plugin",
        "ctx_matches": "True",
        "star_tools_matches": "True",
        "session": "tool-session",
        "word": "hello",
    }

    replies = await harness.dispatch_text("toolrm")
    assert any(_record_text(item) == "toolrm:True" for item in replies)
    assert await manager.get("note_tool") is None

    with pytest.raises(LookupError, match="llm tool not found"):
        await harness.capability_dispatcher.invoke(
            InvokeMessage(
                id="tool-2",
                capability="internal.llm_tool.execute",
                input={
                    "plugin_id": "p1_4_compat_plugin",
                    "tool_name": "note_tool",
                    "handler_ref": "__dynamic_llm_tool__:note_tool",
                    "tool_args": {"word": "again"},
                    "event": {"session_id": "tool-session", "text": "tool event"},
                },
            ),
            CancelToken(),
        )

    await harness.stop()
