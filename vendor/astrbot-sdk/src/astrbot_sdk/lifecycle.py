from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from .registration import HandlerKind, _lifecycle

ConfigT = TypeVar("ConfigT")


@dataclass(frozen=True, slots=True)
class ConfigChangedEvent(Generic[ConfigT]):
    previous: ConfigT
    current: ConfigT


@dataclass(frozen=True, slots=True)
class ShutdownEvent:
    deadline: datetime | None = None
    reason: str = "shutdown"


startup = _lifecycle(HandlerKind.LIFECYCLE_STARTUP)
config_changed = _lifecycle(HandlerKind.LIFECYCLE_CONFIG_CHANGED)
validate_config = _lifecycle(HandlerKind.LIFECYCLE_VALIDATE_CONFIG)
health = _lifecycle(HandlerKind.LIFECYCLE_HEALTH)
shutdown = _lifecycle(HandlerKind.LIFECYCLE_SHUTDOWN)

__all__ = [
    "ConfigChangedEvent",
    "ShutdownEvent",
    "config_changed",
    "health",
    "shutdown",
    "startup",
    "validate_config",
]
