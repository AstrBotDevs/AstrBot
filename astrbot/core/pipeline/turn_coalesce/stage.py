"""Hand should_run_llm fragments to TurnWindowManager after allow-list checks."""

from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..context import PipelineContext
from ..stage import Stage


class TurnCoalesceStage(Stage):
    """Non-blocking handoff for optional DM coalescing and waiter intercept."""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        raw = ctx.astrbot_config.get("inbound_coalesce") or {}
        self.enable = bool(raw.get("enable", False))
        self.private = bool(raw.get("private", True))
        self.group = False
        self.wait_seconds = float(raw.get("wait_seconds", 2.0))
        self.max_total_seconds = float(raw.get("max_total_seconds", 12.0))
        self.max_typing_wait = float(raw.get("max_typing_wait", 30.0))

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None:
        manager = getattr(self.ctx.execution_context, "turn_window_manager", None)
        if manager is None:
            return

        if event.get_extra("onebot_post_type") in {"notice", "request"}:
            if hasattr(manager, "set_max_typing_wait"):
                manager.set_max_typing_wait(self.max_typing_wait)
            message_id = (
                event.get_extra("napcat_message_id")
                or getattr(event.message_obj, "message_id", "")
                or ""
            )
            if message_id:
                manager.recall(str(message_id))
            return

        registry = getattr(self.ctx.execution_context, "session_waiter_registry", None)
        if registry is not None and await registry.dispatch(event):
            event.stop_event()
            return

        if hasattr(manager, "set_max_typing_wait"):
            manager.set_max_typing_wait(self.max_typing_wait)

        if event.get_extra("route_kind") == "turn_flush":
            return

        if event.get_extra("should_run_command"):
            manager.discard(event)
            return

        if not self.enable or not self.private or not event.is_private_chat():
            return
        if not event.get_extra("should_run_llm"):
            return

        manager.accept(
            event,
            wait_seconds=self.wait_seconds,
            max_total_seconds=self.max_total_seconds,
        )
        event.set_extra("skip_empty_completion", True)
        event.stop_event()
