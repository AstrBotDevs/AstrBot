"""Completed runtime state and the small control surface used by the Dashboard."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.cron import CronJobManager
    from astrbot.core.event_bus import EventBus
    from astrbot.core.execution_context import CoreExecutionContext
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.log import LogBroker
    from astrbot.core.memory import MemoryManager
    from astrbot.core.persona_mgr import PersonaManager
    from astrbot.core.persona_runtime import PersonaRuntimeManager
    from astrbot.core.pipeline.scheduler import PipelineScheduler
    from astrbot.core.platform.manager import PlatformManager
    from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
    from astrbot.core.provider.manager import ProviderManager
    from astrbot.core.runtime_catalogs import RuntimeCatalogs
    from astrbot.core.runtime_services import RuntimeServices
    from astrbot.core.star.star_manager import PluginManager
    from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
    from astrbot.core.umop_config_router import UmopConfigRouter
    from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator


@dataclass(frozen=True, slots=True)
class CoreRuntime:
    """Resources that are available only after core initialization succeeds."""

    services: RuntimeServices
    log_broker: LogBroker
    catalogs: RuntimeCatalogs
    webchat_run_coordinator: WebChatRunCoordinator
    astrbot_config: AstrBotConfig
    astrbot_config_mgr: AstrBotConfigManager
    provider_manager: ProviderManager
    platform_manager: PlatformManager
    conversation_manager: ConversationManager
    platform_message_history_manager: PlatformMessageHistoryManager
    persona_mgr: PersonaManager
    persona_runtime_manager: PersonaRuntimeManager
    memory_manager: MemoryManager
    knowledge_base_manager: KnowledgeBaseManager
    cron_manager: CronJobManager
    plugin_manager: PluginManager
    execution_context: CoreExecutionContext
    umop_config_router: UmopConfigRouter
    subagent_orchestrator: SubAgentOrchestrator
    pipeline_schedulers: dict[str, PipelineScheduler]
    event_queue: asyncio.Queue
    event_bus: EventBus
    dashboard_shutdown_event: asyncio.Event
    start_time: int


class CoreControl(Protocol):
    """Lifecycle operations intentionally exposed to Dashboard services."""

    async def reload_pipeline_scheduler(self, conf_id: str) -> None: ...

    async def remove_pipeline_scheduler(self, conf_id: str) -> None: ...

    async def restart(self) -> None: ...
