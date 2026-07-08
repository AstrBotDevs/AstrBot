from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core.config import AstrBotConfig

from .context_utils import call_event_hook, call_handler

if TYPE_CHECKING:
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
    from astrbot.core.star import PluginManager


@dataclass
class PipelineContext:
    """Context object with the state needed to execute a pipeline."""

    base_astrbot_config: AstrBotConfig
    plugin_manager: PluginManager
    astrbot_config_id: str
    astrbot_config_mgr: AstrBotConfigManager
    call_handler = call_handler
    call_event_hook = call_event_hook

    @property
    def astrbot_config(self) -> AstrBotConfig:
        """Return the current event config view, or the shared base config.

        Returns:
            Effective config bound to the current task when a pipeline event is
            running; otherwise the shared config profile.
        """
        return self.astrbot_config_mgr.get_current_conf(self.base_astrbot_config)
