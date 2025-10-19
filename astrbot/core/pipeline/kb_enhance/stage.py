"""
知识库增强阶段
在 LLM 调用之前,根据会话配置注入知识库上下文
"""

from typing import Union, AsyncGenerator
from ..stage import Stage, register_stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core import logger


@register_stage
class KBEnhanceStage(Stage):
    """知识库增强阶段

    功能:
    - 检查会话是否配置了知识库
    - 如果配置了知识库,则检索相关知识并注入到事件上下文中
    - 供后续的 ProcessStage 使用
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.kb_config = self.config.get("knowledge_base", {})

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        """处理知识库上下文注入"""

        # 检查知识库功能是否启用
        if not self.kb_config.get("enabled", False):
            return

        # 检查是否需要调用知识库 (只有在被@或唤醒时才检索)
        if not event.is_at_or_wake_command:
            return

        try:
            # 从 plugin_manager.context 获取 kb_injector
            kb_injector = getattr(self.ctx.plugin_manager.context, "kb_injector", None)

            if not kb_injector:
                logger.debug("知识库注入器未初始化，跳过知识库增强")
                return

            # 获取会话 ID
            unified_msg_origin = event.unified_msg_origin

            # 获取用户查询
            query = event.message_str

            # 检索并注入知识
            kb_context = await kb_injector.retrieve_and_inject(
                unified_msg_origin=unified_msg_origin,
                query=query,
            )

            if kb_context:
                # 将知识库上下文存储到事件的 extra 中
                event.set_extra("kb_context", kb_context)
                logger.debug(
                    f"知识库上下文已注入，检索到 {len(kb_context.get('results', []))} 条相关知识"
                )

        except Exception as e:
            logger.error(f"知识库增强阶段处理失败: {e}")
            import traceback

            logger.error(traceback.format_exc())
