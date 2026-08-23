from astrbot.api import star
from astrbot.api.event import AstrMessageEvent

from .reply import reply_i18n


class FlowCommands:
    """Session-level streaming override: enable / disable / unset / status."""

    def __init__(self, context: star.PluginContext) -> None:
        self.context = context

    async def status(self, event: AstrMessageEvent) -> None:
        umo = event.unified_msg_origin
        override = await self.context.preferences.streaming_override(umo)
        global_value = bool(
            self.context.config.get(umo=umo)
            .get("provider_settings", {})
            .get("streaming_response", False)
        )
        if override is None:
            mode = await self.context.i18n.t(event, "flow.mode.unset")
            effective_key = (
                "flow.effective.on" if global_value else "flow.effective.off"
            )
        else:
            mode = await self.context.i18n.t(
                event,
                "flow.mode.on" if override else "flow.mode.off",
            )
            effective_key = "flow.effective.on" if override else "flow.effective.off"
        effective = await self.context.i18n.t(event, effective_key)
        await reply_i18n(
            self.context,
            event,
            "flow.status.body",
            mode=mode,
            effective=effective,
        )

    async def set_override(self, event: AstrMessageEvent, enabled: bool) -> None:
        await self.context.preferences.set_streaming_override(
            event.unified_msg_origin,
            enabled,
        )
        await reply_i18n(
            self.context,
            event,
            "flow.set.on" if enabled else "flow.set.off",
        )

    async def unset(self, event: AstrMessageEvent) -> None:
        await self.context.preferences.clear_streaming_override(
            event.unified_msg_origin,
        )
        await reply_i18n(self.context, event, "flow.unset.ok")
