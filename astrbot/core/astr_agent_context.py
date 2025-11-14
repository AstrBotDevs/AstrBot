from dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider import Provider


@dataclass
class AstrAgentContext:
    provider: Provider
    event: AstrMessageEvent


AgentContextWrapper = ContextWrapper[AstrAgentContext]
