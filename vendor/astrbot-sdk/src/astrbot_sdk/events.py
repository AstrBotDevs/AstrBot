from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .message_components import ButtonInteraction, UIInteraction
from .messages import MessageChain, MessageLike
from .results import EventResult, MessageResult, Propagation, ViewResult, message_result


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

    @property
    def is_button_interaction(self) -> bool:
        """Return whether the inbound message carries a button interaction."""
        return self.button_interaction is not None

    @property
    def button_interaction(self) -> ButtonInteraction | None:
        """Return the inbound ButtonInteraction segment, if present."""
        return next(
            (seg for seg in self.message if isinstance(seg, ButtonInteraction)),
            None,
        )

    @property
    def ui_interaction(self) -> UIInteraction | None:
        """Return the inbound ChatUI view interaction segment, if present."""
        return next(
            (seg for seg in self.message if isinstance(seg, UIInteraction)),
            None,
        )

    def reply(
        self,
        content: MessageLike,
        *,
        quote: bool = False,
        propagation: Propagation = Propagation.CONTINUE,
    ) -> MessageResult:
        return message_result(content, quote=quote, propagation=propagation)

    def view_result(
        self,
        *,
        data: Mapping[str, Any],
        name: str | None = None,
        text: str = "",
        title: str = "",
        stop: bool = False,
    ) -> ViewResult:
        """Create a named ChatUI view card or update the active interaction card.

        Args:
            data: JSON-compatible card snapshot data.
            name: Registered view name when creating a new card; omit to update.
            text: Fallback text when creating a new view card.
            title: Display title when creating a new view card.
            stop: Whether to stop further pipeline propagation.

        Returns:
            ViewResult ready to yield or return from a handler.

        Raises:
            ValueError: If creation/update invariants are violated.
        """
        if name is None and (self.ui_interaction is None or text):
            raise ValueError("A view update requires a UI interaction and no text.")
        return ViewResult(
            propagation=Propagation.STOP if stop else Propagation.CONTINUE,
            data=data,
            name=name,
            text=text,
            title=title,
        )

    def stop(self) -> EventResult:
        return EventResult(propagation=Propagation.STOP)
