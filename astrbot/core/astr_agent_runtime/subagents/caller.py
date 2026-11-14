"""Ownership and host services for a delegated input, separate from its runtime."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from astrbot.core.agent.runtime import AgentInput, AgentPermissions

if TYPE_CHECKING:
    from astrbot.core.agent.tool import ToolSet
    from astrbot.core.astr_agent_runtime.context import AstrAgentContext
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.star.context import Context

    from .store import AgentScope


@dataclass
class AgentCaller:
    """Current owner, services, and permissions supplied to an agent runtime."""

    context: Context
    event: AstrMessageEvent
    scope: AgentScope
    tools: ToolSet
    agent_context: AstrAgentContext
    limits: dict = field(default_factory=dict)

    def owner_metadata(self) -> dict:
        """Snapshot only the information required for safe result wakeups.

        Returns:
            Serializable sender, group, plugin, and role information.
        """
        return {
            "sender_id": str(self.event.get_sender_id()),
            "sender_name": self.event.message_obj.sender.nickname,
            "group_id": self.event.get_group_id(),
            "plugins_name": copy.copy(self.event.plugins_name),
            "was_admin": (
                self.agent_context.permissions
                or AgentPermissions.from_event(self.event)
            ).is_admin,
        }


@dataclass
class DelegatedAgentInput(AgentInput):
    """Delegated input with its owning main context and accepted sequence."""

    caller: AgentCaller | None = None
    sequence: int = 1
