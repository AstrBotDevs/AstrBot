from dataclasses import dataclass
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star import PluginManager


@dataclass
class PipelineContext:
    """上下文对象，包含管道执行所需的上下文信息"""

    astrbot_config: AstrBotConfig  # AstrBot 配置对象
    plugin_manager: PluginManager  # 插件管理器对象
