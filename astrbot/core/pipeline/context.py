from dataclasses import dataclass
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star import PluginManager


@dataclass
class PipelineContext:
    astrbot_config: AstrBotConfig
    plugin_manager: PluginManager
