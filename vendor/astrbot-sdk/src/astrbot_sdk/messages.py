from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import TypeAlias, overload

from .message_components import MessageSegment, Plain


@dataclass(frozen=True, slots=True, init=False)
class MessageChain(Sequence[MessageSegment]):
    segments: tuple[MessageSegment, ...]

    def __init__(self, *segments: MessageSegment) -> None:
        for segment in segments:
            if not isinstance(segment, MessageSegment):
                raise TypeError(
                    f"message chain items must be MessageSegment, got {type(segment)!r}"
                )
        object.__setattr__(self, "segments", tuple(segments))

    @overload
    def __getitem__(self, index: int) -> MessageSegment: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[MessageSegment, ...]: ...

    def __getitem__(
        self,
        index: int | slice,
    ) -> MessageSegment | tuple[MessageSegment, ...]:
        return self.segments[index]

    def __iter__(self) -> Iterator[MessageSegment]:
        return iter(self.segments)

    def __len__(self) -> int:
        return len(self.segments)

    @property
    def text(self) -> str:
        return "".join(
            segment.text for segment in self.segments if isinstance(segment, Plain)
        )


MessageLike: TypeAlias = str | MessageSegment | Sequence[MessageSegment] | MessageChain


def to_message_chain(content: MessageLike) -> MessageChain:
    if isinstance(content, MessageChain):
        return content
    if isinstance(content, str):
        return MessageChain(Plain(content))
    if isinstance(content, MessageSegment):
        return MessageChain(content)
    if isinstance(content, Sequence):
        return MessageChain(*content)
    raise TypeError(f"unsupported message content: {type(content)!r}")
