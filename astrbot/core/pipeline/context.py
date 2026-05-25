from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from astrbot.core.config import AstrBotConfig

from .context_utils import call_event_hook, call_handler


@dataclass
class PipelineContext:
    """上下文对象，包含管道执行所需的上下文信息"""

    astrbot_config: AstrBotConfig  # AstrBot 配置对象
    plugin_manager: Any  # 插件管理器对象
    astrbot_config_id: str
    call_handler = call_handler
    call_event_hook = call_event_hook
