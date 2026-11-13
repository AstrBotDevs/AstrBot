from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.core.config import AstrBotConfig
from astrbot.core.config.runtime import current_message_config

from .context_utils import call_event_hook, call_handler

if TYPE_CHECKING:
    from astrbot.core.agent.runtime import AgentRuntime
    from astrbot.core.db import BaseDatabase
    from astrbot.core.star import PluginManager


class PipelineContext:
    """Shared pipeline services with task-local message configuration."""

    def __init__(
        self,
        astrbot_config: AstrBotConfig,
        plugin_manager: PluginManager,
        astrbot_config_id: str,
        db_helper: BaseDatabase | None = None,
        agent_runtimes: dict[str, AgentRuntime] | None = None,
    ) -> None:
        self._base_config = astrbot_config
        self.plugin_manager = plugin_manager
        self.astrbot_config_id = astrbot_config_id
        self.db_helper = db_helper
        self.agent_runtimes = agent_runtimes if agent_runtimes is not None else {}

    @property
    def astrbot_config(self) -> AstrBotConfig:
        """Read the active message snapshot, or the base profile outside execution.

        Returns:
            Configuration belonging to this pipeline's current execution.
        """
        scope = current_message_config.get()
        if scope is not None and scope.active and scope.context is self:
            return scope.config
        return self._base_config

    call_handler = call_handler
    call_event_hook = call_event_hook
