from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Self

from .assets import AssetRef


class MessageSegment:
    type: ClassVar[str]


@dataclass(frozen=True, slots=True)
class Plain(MessageSegment):
    text: str
    type: ClassVar[str] = "Plain"


@dataclass(frozen=True, slots=True)
class At(MessageSegment):
    user_id: str
    name: str | None = None
    type: ClassVar[str] = "At"


@dataclass(frozen=True, slots=True)
class AtAll(MessageSegment):
    type: ClassVar[str] = "AtAll"


@dataclass(frozen=True, slots=True)
class Reply(MessageSegment):
    id: str
    sender_id: str | None = None
    sender_name: str | None = None
    text: str | None = None
    type: ClassVar[str] = "Reply"


MediaSource = AssetRef | Path | bytes | str


@dataclass(frozen=True, slots=True)
class MediaSegment(MessageSegment):
    source: MediaSource
    media_type: str | None = None

    @classmethod
    def from_url(cls, url: str, *, media_type: str | None = None) -> Self:
        if not url.startswith(("http://", "https://")):
            raise ValueError("media URL must start with http:// or https://")
        return cls(source=url, media_type=media_type)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        media_type: str | None = None,
    ) -> Self:
        return cls(source=Path(path), media_type=media_type)

    @classmethod
    def from_bytes(cls, data: bytes, *, media_type: str | None = None) -> Self:
        return cls(source=data, media_type=media_type)


@dataclass(frozen=True, slots=True)
class Image(MediaSegment):
    type: ClassVar[str] = "Image"


@dataclass(frozen=True, slots=True)
class Record(MediaSegment):
    type: ClassVar[str] = "Record"


@dataclass(frozen=True, slots=True)
class Video(MediaSegment):
    type: ClassVar[str] = "Video"


@dataclass(frozen=True, slots=True)
class File(MediaSegment):
    filename: str | None = None
    type: ClassVar[str] = "File"

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> Self:
        """Create a file segment from a public URL."""
        if not url.startswith(("http://", "https://")):
            raise ValueError("media URL must start with http:// or https://")
        return cls(source=url, media_type=media_type, filename=filename)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> Self:
        """Create a file segment from a local path (uploaded before sending)."""
        return cls(source=Path(path), media_type=media_type, filename=filename)

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> Self:
        """Create a file segment from bytes (uploaded before sending)."""
        return cls(source=data, media_type=media_type, filename=filename)


@dataclass(frozen=True, slots=True)
class Face(MessageSegment):
    """Platform emoji face identified by a numeric ID."""

    id: int
    type: ClassVar[str] = "Face"


@dataclass(frozen=True, slots=True)
class Forward(MessageSegment):
    """Reference to a platform forwarded-message bundle."""

    id: str
    type: ClassVar[str] = "Forward"


@dataclass(frozen=True, slots=True)
class Node(MessageSegment):
    sender_id: str
    content: tuple[MessageSegment, ...]
    sender_name: str | None = None
    type: ClassVar[str] = "Node"

    def __init__(
        self,
        sender_id: str,
        content: Sequence[MessageSegment],
        sender_name: str | None = None,
    ) -> None:
        object.__setattr__(self, "sender_id", sender_id)
        object.__setattr__(self, "content", tuple(content))
        object.__setattr__(self, "sender_name", sender_name)


@dataclass(frozen=True, slots=True)
class Nodes(MessageSegment):
    nodes: tuple[Node, ...]
    type: ClassVar[str] = "Nodes"

    def __init__(self, nodes: Sequence[Node]) -> None:
        object.__setattr__(self, "nodes", tuple(nodes))


@dataclass(frozen=True, slots=True)
class UnknownSegment(MessageSegment):
    segment_type: str
    data: Mapping[str, Any] = field(default_factory=dict)
    type: ClassVar[str] = "Unknown"

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
