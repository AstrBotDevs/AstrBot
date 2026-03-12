"""V4 sample plugin used by integration tests."""

from __future__ import annotations

from astrbot_sdk import (
    Context,
    MessageEvent,
    Star,
    on_command,
    on_message,
    provide_capability,
)
from astrbot_sdk.context import CancelToken


class HelloPlugin(Star):
    """Small but representative v4 plugin fixture."""

    @on_command("hello", aliases=["hi"], description="发送问候消息")
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        reply = await ctx.llm.chat(event.text)
        await event.reply(reply)

        chunks: list[str] = []
        async for chunk in ctx.llm.stream_chat("stream"):
            chunks.append(chunk)
        await event.reply("".join(chunks))

    @on_command("remember", description="保存一条记忆并回读")
    async def remember(self, event: MessageEvent, ctx: Context) -> None:
        await ctx.memory.save(
            "demo:last_message",
            {"user_id": event.user_id or "", "text": event.text},
        )
        remembered = await ctx.memory.get("demo:last_message") or {}
        await ctx.db.set("demo:last_session", event.session_id)
        keys = await ctx.db.list("demo:")
        await event.reply(
            f"Memory saved for {remembered.get('user_id', 'unknown')} with {len(keys)} keys"
        )

    @on_message(regex=r"^ping$")
    async def ping(self, event: MessageEvent) -> None:
        await event.reply("pong")

    @on_command("announce", description="发送一条富消息链")
    async def announce(self, event: MessageEvent, ctx: Context) -> None:
        await ctx.platform.send_chain(
            event.target or event.session_id,
            [
                {"type": "Plain", "text": "Demo "},
                {"type": "Image", "file": "https://example.com/demo.png"},
            ],
        )

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
        return {
            "echo": str(payload.get("text", "")),
            "plugin_id": ctx.plugin_id,
        }
