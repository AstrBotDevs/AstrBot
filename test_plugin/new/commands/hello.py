"""V4 sample plugin used by integration tests.

This fixture intentionally exercises the currently supported public v4 API:
- top-level decorators: on_command/on_message/on_event/on_schedule/require_admin
- Context clients: llm, memory, db, platform
- MessageEvent helpers: reply/plain_result/target/to_payload
- plugin-provided capabilities: normal + stream
"""

from __future__ import annotations

import asyncio

from astrbot_sdk import (
    Context,
    MessageEvent,
    Star,
    on_command,
    on_event,
    on_message,
    on_schedule,
    provide_capability,
    require_admin,
)
from astrbot_sdk.context import CancelToken


class HelloPlugin(Star):
    """Representative v4 plugin fixture."""

    @on_command("hello", aliases=["hi"], description="发送问候消息")
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        reply = await ctx.llm.chat(event.text)
        await event.reply(reply)

        chunks: list[str] = []
        async for chunk in ctx.llm.stream_chat("stream"):
            chunks.append(chunk)
        await event.reply("".join(chunks))

    @on_command("raw", description="调用 llm.chat_raw 并返回结构化信息")
    async def raw(self, event: MessageEvent, ctx: Context):
        response = await ctx.llm.chat_raw(
            event.text,
            system="be concise",
            history=[{"role": "user", "content": "history"}],
        )
        payload = event.to_payload()
        ctx.logger.info("raw handler for {}", payload.get("session_id"))
        return event.plain_result(
            f"raw={response.text}|finish={response.finish_reason}|"
            f"cancelled={ctx.cancel_token.cancelled}"
        )

    @on_command("remember", description="覆盖 memory/db 全量基本操作")
    async def remember(self, event: MessageEvent, ctx: Context):
        await ctx.memory.save(
            "demo:last_message",
            {"user_id": event.user_id or "", "text": event.text},
            source="fixture",
        )
        remembered = await ctx.memory.get("demo:last_message") or {}
        searched = await ctx.memory.search("fixture")
        await ctx.memory.delete("demo:last_message")

        await ctx.db.set("demo:last_session", event.session_id)
        session_value = await ctx.db.get("demo:last_session")
        keys = await ctx.db.list("demo:")
        await ctx.db.delete("demo:last_session")

        return event.plain_result(
            f"remembered={remembered.get('user_id', 'unknown')}|"
            f"searched={len(searched)}|session={session_value}|keys={len(keys)}"
        )

    @on_command("platforms", description="覆盖 platform 相关 API")
    async def platforms(self, event: MessageEvent, ctx: Context) -> None:
        target = event.target or event.session_id
        members = await ctx.platform.get_members(target)
        await ctx.platform.send_image(target, "https://example.com/demo.png")
        await ctx.platform.send(
            target,
            f"members={len(members)} first={members[0]['user_id'] if members else 'none'}",
        )

    @on_command("announce", description="发送一条富消息链")
    async def announce(self, event: MessageEvent, ctx: Context) -> None:
        await ctx.platform.send_chain(
            event.target or event.session_id,
            [
                {"type": "Plain", "text": "Demo "},
                {"type": "Image", "file": "https://example.com/demo.png"},
            ],
        )

    @require_admin
    @on_command("secure", description="测试 require_admin")
    async def secure(self, event: MessageEvent):
        return event.plain_result(f"secure:{event.user_id or 'unknown'}")

    @on_message(regex=r"^ping$", keywords=["ping"], platforms=["test"])
    async def ping(self, event: MessageEvent):
        return event.plain_result("pong")

    @on_event("group_join")
    async def on_group_join(self, event: MessageEvent, ctx: Context) -> None:
        ctx.logger.info("event handler observed {}", event.text)

    @on_schedule(interval_seconds=60)
    async def heartbeat(self, ctx: Context) -> None:
        await ctx.db.set("demo:last_schedule", {"status": "ok"})

    @provide_capability(
        "demo.echo",
        description="回显输入文本",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "echo": {"type": "string"},
                "plugin_id": {"type": "string"},
            },
            "required": ["echo", "plugin_id"],
        },
    )
    async def echo_capability(
        self,
        payload: dict[str, object],
        ctx: Context,
        cancel_token: CancelToken,
    ) -> dict[str, str]:
        cancel_token.raise_if_cancelled()
        await ctx.db.set(
            "demo:capability_echo",
            {"text": str(payload.get("text", ""))},
        )
        stored = await ctx.db.get("demo:capability_echo") or {}
        return {
            "echo": str(stored.get("text", "")),
            "plugin_id": ctx.plugin_id,
        }

    @provide_capability(
        "demo.stream",
        description="流式回显输入文本",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "object"},
                }
            },
            "required": ["items"],
        },
        supports_stream=True,
        cancelable=True,
    )
    async def stream_capability(
        self,
        payload: dict[str, object],
        ctx: Context,
        cancel_token: CancelToken,
    ):
        text = str(payload.get("text", ""))
        await ctx.db.set("demo:last_stream", {"text": text})
        for char in text:
            cancel_token.raise_if_cancelled()
            await asyncio.sleep(0)
            yield {"text": char}
