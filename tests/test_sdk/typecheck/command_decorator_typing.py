from __future__ import annotations

from typing import Any, Callable, Coroutine, assert_type

from pydantic import BaseModel

from astrbot_sdk import (
    Context,
    MessageEvent,
    PlatformFilter,
    admin_only,
    conversation_command,
    custom_filter,
    on_command,
    platforms,
    priority,
)


class EchoInput(BaseModel):
    text: str


UnboundHandler = Callable[
    ["DemoPlugin", MessageEvent, EchoInput, Context],
    Coroutine[Any, Any, None],
]
BoundHandler = Callable[[MessageEvent, EchoInput, Context], Coroutine[Any, Any, None]]


class DemoPlugin:
    @on_command("echo")
    async def echo(
        self,
        event: MessageEvent,
        params: EchoInput,
        ctx: Context,
    ) -> None:
        return None

    @priority(10)
    @admin_only
    @platforms("qq")
    @custom_filter(PlatformFilter(["qq"]))
    @on_command("echo-admin")
    async def echo_admin(
        self,
        event: MessageEvent,
        params: EchoInput,
        ctx: Context,
    ) -> None:
        return None

    @conversation_command("chat")
    async def chat(
        self,
        event: MessageEvent,
        params: EchoInput,
        ctx: Context,
    ) -> None:
        return None


assert_type(DemoPlugin.echo, UnboundHandler)
assert_type(DemoPlugin.echo_admin, UnboundHandler)
assert_type(DemoPlugin.chat, UnboundHandler)

plugin = DemoPlugin()

assert_type(plugin.echo, BoundHandler)
assert_type(plugin.echo_admin, BoundHandler)
assert_type(plugin.chat, BoundHandler)
