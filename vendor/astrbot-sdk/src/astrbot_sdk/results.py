from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .messages import MessageChain, MessageLike, to_message_chain


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
