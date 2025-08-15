from dataclasses import dataclass
from typing import Any, Generic
from typing_extensions import TypeVar

TContext = TypeVar("TContext", default=Any)


@dataclass
class RunContext(Generic[TContext]):
    """A context for running an agent, which can be used to pass additional data or state."""

    context: TContext

class AgentRunContext:
    request: ProviderRequest | None
    streaming: bool
    event: AstrMessageEvent
    pipeline_ctx: PipelineContext

