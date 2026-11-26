"""Dedicated new-SDK plugin covering EventState, Platform, and Session filters."""

from __future__ import annotations

import json

from astrbot_sdk import (
    DefaultSessionFilter,
    MessageEvent,
    Plugin,
    SenderSessionFilter,
    SessionFilter,
    on,
)
from astrbot_sdk.message_components import Plain
from astrbot_sdk.services import SendReceipt


class PassPrefixSessionFilter(SessionFilter):
    """Custom SessionFilter matching initiating wait_custom or 'PASS:' replies."""

    def filter(self, event: MessageEvent) -> str:
        """Compute session key sharing bucket across command trigger and PASS: reply."""
        text = event.text.strip()
        if text == "es wait_custom" or text.startswith("PASS:"):
            return f"pass-bucket:{event.umo.platform_id}"
        return f"ignore:{event.id}"


class SdkEventsSessionsPlugin(Plugin):
    """Exercise EventStateClient, PlatformClient, SendReceipt, and SessionFilters."""

    @on.command(
        "es act", description="Run EventStateClient, streaming, and PlatformClient"
    )
    async def es_act(self, event: MessageEvent):
        """Exercise set_call_llm, typing/react/get_group, streaming, and call_action."""
        await self.ctx.events.set_call_llm(event, False)
        await self.ctx.events.send_typing(event)
        await self.ctx.events.stop_typing(event)
        await self.ctx.events.react(event, "star")
        group = await self.ctx.events.get_group(event, group_id="es-grp")

        async def _ev_stream():
            yield "es-s1"
            yield Plain("es-s2")

        await self.ctx.events.send_streaming(event, _ev_stream(), use_fallback=True)
        await self.ctx.messages.send_streaming(event, _ev_stream(), use_fallback=False)
        receipt = await self.ctx.messages.send(event.umo, "es-proactive")
        raw = await self.ctx.platforms.call_action("webchat", "es_ping", val=9)
        yield event.reply(
            json.dumps(
                {
                    "group": group,
                    "receipt_ok": (
                        isinstance(receipt, SendReceipt)
                        and isinstance(receipt.message_id, str)
                    ),
                    "raw": raw,
                },
                sort_keys=True,
            )
        )

    @on.command("es wait_default", description="SessionWait with DefaultSessionFilter")
    async def es_wait_default(self, event: MessageEvent):
        """Exercise DefaultSessionFilter and SessionWait.ask."""
        async with self.ctx.sessions.wait(
            event,
            filter=DefaultSessionFilter(),
            timeout=10.0,
        ) as wait:
            nxt = await wait.ask("ask-default")
        yield event.reply(f"wait-default:{nxt.text}")

    @on.command("es wait_sender", description="SessionWait with SenderSessionFilter")
    async def es_wait_sender(self, event: MessageEvent):
        """Exercise SenderSessionFilter and SessionWait.next."""
        await self.ctx.messages.send(event.umo, "ask-sender")
        async with self.ctx.sessions.wait(
            event,
            filter=SenderSessionFilter(),
            timeout=10.0,
        ) as wait:
            nxt = await wait.next()
        yield event.reply(f"wait-sender:{nxt.text}")

    @on.command("es wait_custom", description="SessionWait with custom SessionFilter")
    async def es_wait_custom(self, event: MessageEvent):
        """Exercise custom SessionFilter subclass and timeout forwarding."""
        async with self.ctx.sessions.wait(
            event,
            filter=PassPrefixSessionFilter(),
            timeout=10.0,
        ) as wait:
            nxt = await wait.ask("ask-custom", timeout=10.0)
        yield event.reply(f"wait-custom:{nxt.text}")
