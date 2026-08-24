from collections.abc import AsyncGenerator

from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.command_ids import BUILTIN_COMMANDS_MODULE
from astrbot.core.star.session_llm_manager import SessionServiceManager

from ..context import PipelineContext
from ..stage import Stage

SESSION_DISABLED_PASSTHROUGH_HANDLERS = frozenset(
    {
        f"{BUILTIN_COMMANDS_MODULE}_bot_status",
        f"{BUILTIN_COMMANDS_MODULE}_bot_enable",
    }
)


def allows_disabled_session(event: AstrMessageEvent) -> bool:
    """Return whether an activated handler may run while the session is off."""
    handlers = event.get_extra("activated_handlers") or ()
    return any(
        getattr(handler, "handler_full_name", "")
        in SESSION_DISABLED_PASSTHROUGH_HANDLERS
        for handler in handlers
    )


class SessionStatusCheckStage(Stage):
    """检查会话是否整体启用"""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.conv_mgr = ctx.execution_context.conversation_manager
        if ctx.preferences is None:
            raise RuntimeError("SessionStatusCheckStage requires shared preferences")
        self.session_services = SessionServiceManager(ctx.preferences)

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None]:
        if await self.session_services.is_session_enabled(event.unified_msg_origin):
            return
        if allows_disabled_session(event):
            return

        logger.debug(f"会话 {event.unified_msg_origin} 已被关闭，已终止事件传播。")

        # workaround for #2309
        conv_id = await self.conv_mgr.get_curr_conversation_id(
            event.unified_msg_origin,
        )
        if not conv_id:
            await self.conv_mgr.new_conversation(
                event.unified_msg_origin,
                platform_id=event.get_platform_id(),
            )

        event.stop_event()
