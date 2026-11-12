"""Internal configuration scope for one pipeline execution."""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.config.snapshot import AstrBotConfigSnapshot
    from astrbot.core.pipeline.context import PipelineContext


@dataclass
class MessageConfig:
    """Keep a message snapshot private to its pipeline and inherited tasks."""

    umo: str
    config: "AstrBotConfigSnapshot"
    context: "PipelineContext"
    override_paths: frozenset[str]
    active: bool = True


current_message_config: ContextVar[MessageConfig | None] = ContextVar(
    "current_message_config", default=None
)
