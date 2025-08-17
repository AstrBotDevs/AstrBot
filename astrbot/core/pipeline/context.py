from dataclasses import dataclass
from astrbot.core.config import AstrBotConfig
from astrbot.core.star import PluginManager
from .context_utils import call_handler, call_event_hook


@dataclass
class PipelineContext:
    """上下文对象，包含管道执行所需的上下文信息"""

    astrbot_config: AstrBotConfig  # AstrBot 配置对象
    plugin_manager: PluginManager  # 插件管理器对象
    astrbot_config_id: str
    call_handler = call_handler
    call_event_hook = call_event_hook
