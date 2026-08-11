"""Core persistence stage for inbound group message history."""

from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..context import PipelineContext
from ..stage import Stage


class GroupMessageHistoryStage(Stage):
    """Persist enabled group history before any plugin handles the event."""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.execution_context = ctx.execution_context

    async def process(self, event: AstrMessageEvent) -> None:
        await self.execution_context.persist_inbound_group_message(event)
