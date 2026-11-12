"""Internal configuration scope for one pipeline execution."""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.config import AstrBotConfig
    from astrbot.core.pipeline.context import PipelineContext


@dataclass
class MessageConfig:
    """Keep a message snapshot private to its pipeline and inherited tasks."""

    umo: str
    config: "AstrBotConfig"
    context: "PipelineContext"
    active: bool = True


current_message_config: ContextVar[MessageConfig | None] = ContextVar(
    "current_message_config", default=None
)
