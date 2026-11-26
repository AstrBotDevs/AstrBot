from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from .messages import MessageChain, MessageLike, to_message_chain
from .protocol_registry import register_protocol_dataclass


class Propagation(StrEnum):
    CONTINUE = "continue"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class EventResult:
    propagation: Propagation = Propagation.CONTINUE


@dataclass(frozen=True, slots=True)
class MessageResult(EventResult):
    message: MessageChain = MessageChain()
    quote: bool = False


@dataclass(frozen=True, slots=True)
class GroupUsage(EventResult):
    """Sentinel emitted by a legacy bare-group anchor when filters pass."""


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ViewResult(EventResult):
    """Create a named ChatUI card or update the active interaction card."""

    data: Mapping[str, Any] = field(default_factory=dict)
    name: str | None = None
    text: str = ""
    title: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.data, Mapping):
            raise ValueError("ViewResult data must be a mapping.")
        if self.name is not None and (not self.name or not self.text.strip()):
            raise ValueError("Creating a view requires a name and fallback text.")
        if self.name is None and self.text:
            raise ValueError("A view update cannot replace fallback text.")
        if self.name is None and self.title:
            raise ValueError("A view update cannot replace its title.")
        encoded = json.dumps(dict(self.data), allow_nan=False, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > 1024 * 1024:
            raise ValueError("View data exceeds one MiB.")
        object.__setattr__(self, "data", MappingProxyType(json.loads(encoded)))


def message_result(
    content: MessageLike,
    *,
    quote: bool = False,
    propagation: Propagation = Propagation.CONTINUE,
) -> MessageResult:
    return MessageResult(
        propagation=propagation,
        message=to_message_chain(content),
        quote=quote,
    )
