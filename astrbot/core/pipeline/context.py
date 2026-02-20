from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core.config import AstrBotConfig

from .context_utils import call_event_hook

if TYPE_CHECKING:
    from astrbot.core.star import PluginManager


__all__ = ["PipelineContext", "call_event_hook"]


@dataclass
class PipelineContext:
    """上下文对象，包含管道执行所需的上下文信息"""

    astrbot_config: AstrBotConfig  # AstrBot 配置对象
    plugin_manager: "PluginManager"  # 插件管理器对象
