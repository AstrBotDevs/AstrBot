import typing as T
from dataclasses import dataclass, field

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import TokenUsage


class AgentResponseData(T.TypedDict):
    chain: MessageChain


@dataclass
class AgentResponse:
    """One runner output, dispatched by its literal type.

    Display responses carry ``chain``; protocol responses carry event payloads.
    ``context.updated`` is an in-memory snapshot for legacy mutation adaptation.
    Event IDs identify durable records and must be reused on redelivery.
    """

    type: T.Literal[
        "streaming_delta",
        "llm_result",
        "err",
        "aborted",
        "agent_stats",
        "tool_call",
        "tool_call_result",
        "turn.started",
        "turn.finished",
        "request.started",
        "request.finished",
        "tool.started",
        "tool.finished",
        "context.updated",
        "message.appended",
        "context.rebased",
    ]
    data: AgentResponseData | dict[str, T.Any]
    event_id: str | None = None


@dataclass
class AgentStats:
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    current_context_tokens: int = 0
    """Input tokens sent in the most recent LLM request."""
    start_time: float = 0.0
    end_time: float = 0.0
    time_to_first_token: float = 0.0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict:
        return {
            "token_usage": self.token_usage.__dict__.copy(),
            "current_context_tokens": self.current_context_tokens,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "time_to_first_token": self.time_to_first_token,
        }
