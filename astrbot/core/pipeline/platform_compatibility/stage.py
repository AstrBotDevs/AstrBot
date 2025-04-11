from ..stage import Stage, register_stage
from ..context import PipelineContext
from typing import Union, AsyncGenerator
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import StarHandlerMetadata
from astrbot.core import logger


@register_stage
class PlatformCompatibilityStage(Stage):
    """检查所有处理器的平台兼容性。

    这个阶段会检查所有处理器是否在当前平台启用，如果未启用则设置platform_compatible属性为False。
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化平台兼容性检查阶段

        Args:
            ctx (PipelineContext): 消息管道上下文对象, 包括配置和插件管理器
        """
        self.ctx = ctx

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        # 获取当前平台ID
        platform_id = event.get_platform_id()

        # 获取已激活的处理器
        activated_handlers = event.get_extra("activated_handlers")
        if activated_handlers is None:
            activated_handlers = []

        # 标记不兼容的处理器
        for handler in activated_handlers:
            if not isinstance(handler, StarHandlerMetadata):
                continue
            # 检查处理器是否在当前平台启用
            enabled = handler.is_enabled_for_platform(platform_id)
            if not enabled:
                if handler.handler_module_path in star_map:
                    plugin_name = star_map[handler.handler_module_path].name
                logger.debug(
                    f"[PlatformCompatibilityStage] 插件 {plugin_name} 在平台 {platform_id} 未启用，标记处理器 {handler.handler_name} 为平台不兼容"
                )
                # 设置处理器为平台不兼容状态
                # TODO: 更好的标记方式
                handler.platform_compatible = False
            else:
                # 确保处理器为平台兼容状态
                handler.platform_compatible = True

        # 更新已激活的处理器列表
        event.set_extra("activated_handlers", activated_handlers)
