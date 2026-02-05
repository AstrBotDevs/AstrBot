from __future__ import annotations

from dataclasses import dataclass

from astrbot.core.message.message_event_result import MessageEventResult


@dataclass(slots=True)
class AgentRunOutcome:
    handled: bool = False
    streaming: bool = False
    result: MessageEventResult | None = None
    stopped: bool = False
