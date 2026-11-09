"""Typed execution facts shared by runners, runtimes and output consumers."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, JsonValue

from .output import OutputComponent, OutputValue, PlainOutput

JsonObject: TypeAlias = dict[str, JsonValue]


class TurnStatus(str, Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentSessionRef:
    """Persistent address of an agent, independent of UMO selection."""

    runtime: str
    session_id: str


class RuntimeExecutionError(RuntimeError):
    """An internal failure carrying a stable public error code."""

    def __init__(self, code: str, message: str) -> None:
        """Identify a failure without publishing exception objects.

        Args:
            code: Stable public failure classification.
            message: Human-readable explanation.
        """
        super().__init__(message)
        self.code = code


class RuntimeErrorInfo(OutputValue):
    """Stable error classification and text, without exception objects."""

    code: str
    message: str


class RuntimeTokenUsage(OutputValue):
    """Reported token counts; missing values remain distinct from zero."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


class ContextUsage(OutputValue):
    """Current context occupancy, independent from cumulative billing."""

    tokens: int | None = Field(default=None, ge=0)
    limit: int | None = Field(default=None, ge=0)


class TurnUsage(OutputValue):
    """An authoritative cumulative snapshot for one turn."""

    tokens: RuntimeTokenUsage = Field(default_factory=RuntimeTokenUsage)
    source: Literal["requests", "turn", "unknown"] = "unknown"
    complete: bool = False
    context: ContextUsage = Field(default_factory=ContextUsage)


class ExecutionMetrics(OutputValue):
    """Runtime-observed durations and actual model/tool step count."""

    duration_ms: float | None = None
    first_token_ms: float | None = None
    steps: int | None = None


class TurnResult(OutputValue):
    """Settled final reply after hooks and runtime history handling."""

    status: TurnStatus = TurnStatus.COMPLETED
    content: tuple[OutputComponent, ...] = ()
    error: RuntimeErrorInfo | None = None
    reason: str = "completed"
    usage: TurnUsage = Field(default_factory=TurnUsage)
    metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)

    @property
    def text(self) -> str:
        """Extract final plain text without reasoning or intermediate output."""
        return "".join(
            part.text for part in self.content if isinstance(part, PlainOutput)
        )


class TurnStarted(OutputValue):
    """Execution acquired its serial slot."""

    type: Literal["turn.started"] = "turn.started"


class TurnPrepared(OutputValue):
    """Presentation metadata without the model system prompt."""

    type: Literal["turn.prepared"] = "turn.prepared"
    user_prompt: str
    model: str
    provider_id: str | None = None
    persona_id: str | None = None
    tool_names: tuple[str, ...] = ()
    streaming: bool = False


class TextDelta(OutputValue):
    """Append text to one content position in an assistant message."""

    type: Literal["text.delta"] = "text.delta"
    message_id: str
    part_index: int = Field(ge=0)
    text: str


class ReasoningDelta(OutputValue):
    """Append readable reasoning to one message content position."""

    type: Literal["reasoning.delta"] = "reasoning.delta"
    message_id: str
    part_index: int = Field(ge=0)
    text: str


class MessageCompleted(OutputValue):
    """An authoritative full message snapshot replacing earlier deltas."""

    type: Literal["message.completed"] = "message.completed"
    message_id: str
    content: tuple[OutputComponent, ...]
    status: TurnStatus = TurnStatus.COMPLETED


class RequestStarted(OutputValue):
    """One provider method invocation, not a hidden HTTP attempt."""

    type: Literal["request.started"] = "request.started"
    request_id: str
    provider_id: str | None = None
    model: str
    streaming: bool
    scope: Literal["provider_call"] = "provider_call"


class RequestFinished(OutputValue):
    """The observed outcome and usage of one provider invocation."""

    type: Literal["request.finished"] = "request.finished"
    request_id: str
    status: TurnStatus
    usage: RuntimeTokenUsage | None = None
    error: RuntimeErrorInfo | None = None
    duration_ms: float


class ToolStarted(OutputValue):
    """Actual executor entry after validation and plugin hooks."""

    type: Literal["tool.started"] = "tool.started"
    execution_id: str
    call_id: str
    name: str
    arguments: JsonObject


class ToolProgress(OutputValue):
    """Append or replace an executor output preview."""

    type: Literal["tool.progress"] = "tool.progress"
    execution_id: str
    mode: Literal["append", "replace"]
    content: tuple[OutputComponent, ...]


class ToolFinished(OutputValue):
    """Observed executor settlement, without claims about descendants."""

    type: Literal["tool.finished"] = "tool.finished"
    execution_id: str
    call_id: str
    status: TurnStatus
    content: tuple[OutputComponent, ...] = ()
    structured_result: JsonValue = None
    error: RuntimeErrorInfo | None = None
    exit_code: int | None = None


class ToolRejected(OutputValue):
    """A tool call rejected before executor entry."""

    type: Literal["tool.rejected"] = "tool.rejected"
    call_id: str
    name: str
    arguments: JsonObject
    error: RuntimeErrorInfo
    content: tuple[OutputComponent, ...]


class UsageUpdated(OutputValue):
    """Replace the turn usage and execution metric snapshots."""

    type: Literal["usage.updated"] = "usage.updated"
    usage: TurnUsage
    metrics: ExecutionMetrics


class TurnFinished(OutputValue):
    """Terminal result after runtime hooks and history handling."""

    type: Literal["turn.finished"] = "turn.finished"
    result: TurnResult


RunnerEventPayload: TypeAlias = Annotated[
    TextDelta
    | ReasoningDelta
    | MessageCompleted
    | RequestStarted
    | RequestFinished
    | ToolStarted
    | ToolProgress
    | ToolFinished
    | ToolRejected
    | UsageUpdated,
    Field(discriminator="type"),
]
RuntimeEventPayload: TypeAlias = Annotated[
    TurnStarted
    | TurnPrepared
    | TextDelta
    | ReasoningDelta
    | MessageCompleted
    | RequestStarted
    | RequestFinished
    | ToolStarted
    | ToolProgress
    | ToolFinished
    | ToolRejected
    | UsageUpdated
    | TurnFinished,
    Field(discriminator="type"),
]


class RuntimeEvent(OutputValue):
    """One attributed fact; database sequence numbers belong to storage."""

    event_id: str
    session: AgentSessionRef
    turn_id: str | None
    created_at: datetime
    payload: RuntimeEventPayload

    @property
    def type(self) -> str:
        return self.payload.type
