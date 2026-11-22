from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Literal, Self

from .assets import AssetRef
from .protocol_registry import register_protocol_dataclass


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
class Poke(MessageSegment):
    """QQ / IM poke nudge segment."""

    poke_type: str = "126"
    user_id: str | None = None
    type: ClassVar[str] = "Poke"


@dataclass(frozen=True, slots=True)
class Json(MessageSegment):
    """Structured JSON card message segment."""

    data: Any = field(default_factory=dict)
    type: ClassVar[str] = "Json"

    def __post_init__(self) -> None:
        raw = self.data
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, Mapping):
            object.__setattr__(self, "data", MappingProxyType(dict(raw)))


@dataclass(frozen=True, slots=True)
class Share(MessageSegment):
    """Rich link-share card segment."""

    url: str = ""
    title: str = ""
    content: str = ""
    image: str = ""
    type: ClassVar[str] = "Share"


@dataclass(frozen=True, slots=True)
class Location(MessageSegment):
    """Geographic location message segment."""

    lat: float = 0.0
    lon: float = 0.0
    title: str = ""
    content: str = ""
    type: ClassVar[str] = "Location"


@dataclass(frozen=True, slots=True)
class Music(MessageSegment):
    """Music card message segment."""

    music_type: str = "custom"
    id: int = 0
    url: str = ""
    audio: str = ""
    title: str = ""
    content: str = ""
    image: str = ""
    type: ClassVar[str] = "Music"


ButtonStyle = Literal["primary", "secondary", "danger"]


@dataclass(frozen=True, slots=True)
class Button(MessageSegment):
    """Portable interactive button for rich chat platforms."""

    label: str
    action_id: str | None = None
    url: str | None = None
    data: Any = None
    style: ButtonStyle = "secondary"
    emoji: str | None = None
    disabled: bool = False
    type: ClassVar[str] = "Button"

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Button label must not be empty.")
        if (self.action_id is None) == (self.url is None):
            raise ValueError("Button requires exactly one of action_id or url.")
        if self.action_id is not None and not self.action_id.strip():
            raise ValueError("Button action_id must not be empty.")
        if self.url is not None and not self.url.strip():
            raise ValueError("Button url must not be empty.")

    @classmethod
    def callback(
        cls,
        label: str,
        action_id: str,
        data: Any = None,
        *,
        style: ButtonStyle = "secondary",
        emoji: str | None = None,
        disabled: bool = False,
    ) -> Button:
        """Create a callback button bound to a host button_action handler."""
        return cls(
            label=label,
            action_id=action_id,
            data=data,
            style=style,
            emoji=emoji,
            disabled=disabled,
        )

    @classmethod
    def link(
        cls,
        label: str,
        url: str,
        *,
        style: ButtonStyle = "secondary",
        emoji: str | None = None,
        disabled: bool = False,
    ) -> Button:
        """Create an external link button."""
        return cls(
            label=label,
            url=url,
            style=style,
            emoji=emoji,
            disabled=disabled,
        )


@dataclass(frozen=True, slots=True, init=False)
class ActionRow(MessageSegment):
    """Horizontal row containing 1 to 5 interactive buttons."""

    buttons: tuple[Button, ...]
    type: ClassVar[str] = "ActionRow"

    def __init__(self, buttons: Sequence[Button]) -> None:
        normalized = tuple(buttons)
        if not 1 <= len(normalized) <= 5:
            raise ValueError("ActionRow requires between 1 and 5 buttons.")
        if not all(isinstance(btn, Button) for btn in normalized):
            raise TypeError("ActionRow items must be Button segments.")
        object.__setattr__(self, "buttons", normalized)


@dataclass(frozen=True, slots=True)
class ButtonInteraction(MessageSegment):
    """Normalized inbound callback button click event segment."""

    action_id: str
    interaction_id: str
    data: Any = None
    source_message_id: str | None = None
    callback_data: str | None = None
    type: ClassVar[str] = "ButtonInteraction"


@register_protocol_dataclass
@dataclass(frozen=True, slots=True)
class ViewContext:
    """Persisted snapshot of the ChatUI card initiating an interaction."""

    id: str
    name: str
    version: int = 1
    revision: int = 0
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


@dataclass(frozen=True, slots=True)
class UIInteraction(MessageSegment):
    """Authenticated user interaction submitted from a plugin-owned view."""

    action_id: str
    interaction_id: str
    view: ViewContext
    data: Any = None
    source: str = "view"
    source_message_id: str | None = None
    type: ClassVar[str] = "UIInteraction"


@dataclass(frozen=True, slots=True)
class UnknownSegment(MessageSegment):
    segment_type: str
    data: Mapping[str, Any] = field(default_factory=dict)
    type: ClassVar[str] = "Unknown"

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))


__all__ = [
    "ActionRow",
    "At",
    "AtAll",
    "Button",
    "ButtonInteraction",
    "ButtonStyle",
    "Face",
    "File",
    "Forward",
    "Image",
    "Json",
    "Location",
    "MediaSegment",
    "MediaSource",
    "MessageSegment",
    "Music",
    "Node",
    "Nodes",
    "Plain",
    "Poke",
    "Record",
    "Reply",
    "Share",
    "UIInteraction",
    "UnknownSegment",
    "Video",
    "ViewContext",
]
