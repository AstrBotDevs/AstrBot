# OneBot plugin API

OneBot events and actions are available through a stable, typed facade. The
facade is event-bound and never exposes a NapCat adapter, websocket, token, or
raw `call_action` method.

```python
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.onebot import (
    OneBotActionTimeout,
    OneBotCapabilityUnavailable,
    OneBotMessageEvent,
)


@filter.command("delete")
async def delete_(self, event: AstrMessageEvent):
    onebot_event = self.context.onebot.event(event)
    if not isinstance(onebot_event, OneBotMessageEvent):
        return
    client = self.context.onebot.for_event(event)
    if client is None or not self.context.onebot.supports(
        event, "onebot.v11", "delete"
    ):
        return
    try:
        await client.messages.delete(message_id=onebot_event.message_id or "")
    except OneBotCapabilityUnavailable, OneBotActionTimeout:
        return
```

`OneBotEvent.payload` preserves unknown upstream fields and is read-only.
Message segments that AstrBot does not know are represented as
`OneBotSegment(type="unknown", data=...)` rather than invalidating the event.
IDs in the DTOs are always strings.

Standard actions are grouped under `messages`, `directory`, `groups`,
`requests`, and `history`. NapCat/QQ extensions (likes, pokes, notices, online
files, flash transfer, custom faces, and AI actions) are under `client.qq`.
Check `supports(event, capability, action)` before using an optional action.

Capability failures, validation errors, transport failures, and timeouts use
the stable `OneBotError` subclasses. Handle them explicitly when a failed or
unknown execution state matters. Do not use `event.bot`, `event.client`, or
arbitrary raw actions.

Standard actions are versioned as `onebot.v11`; NapCat-only actions are
versioned as `napcat.qq`. A capability probe is advisory, so still handle a
capability/action exception if the adapter disconnects between the probe and
the call.
