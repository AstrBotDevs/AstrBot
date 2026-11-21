from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .messages import MessageChain, MessageLike
from .results import EventResult, MessageResult, Propagation, message_result


class MessageType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    OTHER = "other"


class SenderRole(StrEnum):
    MEMBER = "member"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class UMO:
    platform_id: str
    message_type: MessageType
    session_id: str


@dataclass(frozen=True, slots=True)
class MessageRef:
    id: str


@dataclass(frozen=True, slots=True)
class Sender:
    id: str
    name: str
    role: SenderRole = SenderRole.MEMBER


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    path: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "arguments",
            MappingProxyType(dict(self.arguments)),
        )


@dataclass(frozen=True, slots=True)
class MessageEvent:
    id: str
    umo: UMO
    platform_type: str
    message_ref: MessageRef
    message: MessageChain
    sender: Sender
    timestamp: datetime
    command: CommandInvocation | None = None
    is_wake: bool = False
    extras: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extras", MappingProxyType(dict(self.extras)))

    @property
    def text(self) -> str:
        return self.message.text

    @property
    def is_private(self) -> bool:
        return self.umo.message_type is MessageType.PRIVATE

    @property
    def is_group(self) -> bool:
        return self.umo.message_type is MessageType.GROUP

    def reply(
        self,
        content: MessageLike,
        *,
        quote: bool = False,
        propagation: Propagation = Propagation.CONTINUE,
    ) -> MessageResult:
        return message_result(content, quote=quote, propagation=propagation)

    def stop(self) -> EventResult:
        return EventResult(propagation=Propagation.STOP)
