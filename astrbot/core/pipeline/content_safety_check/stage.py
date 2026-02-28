from astrbot.core.lang import t
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..context import PipelineContext
from ..stage import Stage, register_stage
from .strategies.strategy import StrategySelector


@register_stage
class ContentSafetyCheckStage(Stage):
    """检查内容安全

    当前只会检查文本的。
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        config = ctx.astrbot_config["content_safety"]
        self.strategy_selector = StrategySelector(config)

    async def process(
        self,
        event: AstrMessageEvent,
        check_text: str | None = None,
    ) -> AsyncGenerator[None, None]:
        """检查内容安全"""
        text = check_text if check_text else event.get_message_str()
        ok, info = self.strategy_selector.check(text)
        if not ok:
            if event.is_at_or_wake_command:
                event.set_result(
                    MessageEventResult().message(
                        t("msg-c733275f"),
                    ),
                )
                yield
            event.stop_event()
            logger.info(t("msg-46c80f28", info=info))
            return
