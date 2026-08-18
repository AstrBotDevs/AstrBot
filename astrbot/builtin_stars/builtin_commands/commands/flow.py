from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.streaming_override import STREAMING_OVERRIDE_KEY


class FlowCommands:
    """Session-level streaming override: on / off / unset / status."""

    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def status(self, event: AstrMessageEvent) -> None:
        umo = event.unified_msg_origin
        override = await self.context.preferences.session_get(
            umo,
            STREAMING_OVERRIDE_KEY,
            None,
        )
        global_value = bool(
            self.context.config.get(umo=umo)
            .get("provider_settings", {})
            .get("streaming_response", False)
        )
        if override is None:
            mode = "unset (follow global)"
            effective = "on" if global_value else "off"
        else:
            mode = "on" if override else "off"
            effective = mode
        event.set_result(
            MessageEventResult().message(
                f"Session streaming override is {mode}. Effective mode: {effective}."
            )
        )

    async def set_override(self, event: AstrMessageEvent, enabled: bool) -> None:
        await self.context.preferences.session_put(
            event.unified_msg_origin,
            STREAMING_OVERRIDE_KEY,
            enabled,
        )
        status = "on" if enabled else "off"
        event.set_result(
            MessageEventResult().message(f"Session streaming override is now {status}.")
        )

    async def unset(self, event: AstrMessageEvent) -> None:
        await self.context.preferences.session_remove(
            event.unified_msg_origin,
            STREAMING_OVERRIDE_KEY,
        )
        event.set_result(
            MessageEventResult().message(
                "Session streaming override removed; following global config."
            )
        )
