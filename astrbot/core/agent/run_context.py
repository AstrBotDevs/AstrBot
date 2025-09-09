from dataclasses import dataclass
from typing import Any, Generic
from typing_extensions import TypeVar

from astrbot.core.platform.astr_message_event import AstrMessageEvent

TContext = TypeVar("TContext", default=Any)


@dataclass
class ContextWrapper(Generic[TContext]):
    """A context for running an agent, which can be used to pass additional data or state."""

    context: TContext
    event: AstrMessageEvent

NoContext = ContextWrapper[None]
