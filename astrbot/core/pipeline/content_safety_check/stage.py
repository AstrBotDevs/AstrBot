from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.i18n import t
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.stage import Stage, register_stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .strategies.strategy import StrategySelector


@register_stage
class ContentSafetyCheckStage(Stage):
    """检查内容安全

    当前只会检查文本的｡
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        config = ctx.astrbot_config["content_safety"]
        self.strategy_selector = StrategySelector(config)

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[None, None]:
        async for item in self.process_text(event, event.get_message_str()):
            yield item

    async def process_text(
        self,
        event: AstrMessageEvent,
        check_text: str,
    ) -> AsyncGenerator[None, None]:
        """检查内容安全"""
        text = check_text if check_text else event.get_message_str()
        locale = self.ctx.get_current_language()
        ok, info = self.strategy_selector.check(text, locale=locale)
        if not ok:
            if event.is_at_or_wake_command:
                event.set_result(
                    MessageEventResult().message(
                        t("pipeline.content_blocked", locale=locale),
                    ),
                )
                yield None
            event.stop_event()
            logger.info(f"内容安全检查不通过,原因:{info}")
            return
