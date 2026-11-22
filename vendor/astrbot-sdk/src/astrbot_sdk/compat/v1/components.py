"""Legacy message components mirroring the old astrbot.api component shapes.

These classes are thin facades over the new SDK message segments: they expose
the old field names and constructors, and convert to the new immutable DTOs
at the protocol boundary.
"""

from __future__ import annotations

import base64
import enum
from pathlib import Path
from typing import Any

from ...message_components import (
    ActionRow as SDKActionRow,
)
from ...message_components import (
    At as SDKAt,
)
from ...message_components import (
    AtAll as SDKAtAll,
)
from ...message_components import (
    Button as SDKButton,
)
from ...message_components import (
    ButtonInteraction as SDKButtonInteraction,
)
from ...message_components import (
    Face as SDKFace,
)
from ...message_components import (
    File as SDKFile,
)
from ...message_components import (
    Forward as SDKForward,
)
from ...message_components import (
    Image as SDKImage,
)
from ...message_components import (
    Json as SDKJson,
)
from ...message_components import (
    Location as SDKLocation,
)
from ...message_components import (
    MessageSegment,
)
from ...message_components import (
    Music as SDKMusic,
)
from ...message_components import (
    Node as SDKNode,
)
from ...message_components import (
    Nodes as SDKNodes,
)
from ...message_components import (
    Plain as SDKPlain,
)
from ...message_components import (
    Poke as SDKPoke,
)
from ...message_components import (
    Record as SDKRecord,
)
from ...message_components import (
    Reply as SDKReply,
)
from ...message_components import (
    Share as SDKShare,
)
from ...message_components import (
    UIInteraction as SDKUIInteraction,
)
from ...message_components import (
    UnknownSegment as SDKUnknownSegment,
)
from ...message_components import (
    Video as SDKVideo,
)
from ...message_components import (
    ViewContext as SDKViewContext,
)
from ...messages import MessageChain as SDKMessageChain
from ...results import MessageResult as SDKMessageResult
from ...results import Propagation


def _media_source(url: Any, file: Any) -> Any:
    """Resolve a legacy media source into a form the outbound uploader accepts.

    Local path strings become ``Path`` objects (uploaded via assets.transfer);
    ``base64://`` strings are decoded to bytes. Public URLs pass through.

    Args:
        url: Legacy ``url`` field, preferred when set.
        file: Legacy ``file`` field fallback.

    Returns:
        A URL string, ``Path``, or bytes suitable as a media segment source.
    """
    source = url or file
    # AssetRef (render/speech capability results) passes straight through.
    from ...assets import AssetRef

    if isinstance(source, AssetRef):
        return source
    if isinstance(source, str):
        if source.startswith("base64://"):
            return base64.b64decode(source[len("base64://") :])
        if source and not source.startswith(("http://", "https://")):
            return Path(source)
    return source


def to_sdk_segment(component: Any) -> MessageSegment:
    """Convert one compat component into the new SDK segment."""
    if isinstance(component, UnknownComponent):
        return component.segment
    if isinstance(component, MessageSegment):
        return component
    if isinstance(component, Plain):
        return SDKPlain(component.text)
    if isinstance(component, AtAll):
        return SDKAtAll()
    if isinstance(component, At):
        return SDKAt(user_id=str(component.qq), name=component.name or None)
    if isinstance(component, Reply):
        return SDKReply(
            id=str(component.id),
            sender_id=str(component.sender_id),
            sender_name=component.sender_nickname or None,
            text=component.message_str or None,
        )
    if isinstance(component, Image):
        return SDKImage(source=_media_source(component.url, component.file))
    if isinstance(component, Record):
        return SDKRecord(source=_media_source(component.url, component.file))
    if isinstance(component, Video):
        return SDKVideo(source=_media_source(component.url, component.file))
    if isinstance(component, Face):
        return SDKFace(id=int(component.id))
    if isinstance(component, Forward):
        return SDKForward(id=str(component.id))
    if isinstance(component, File):
        return SDKFile(
            source=_media_source(component.url, component.file_),
            filename=component.name or None,
        )
    if isinstance(component, Nodes):
        return SDKNodes([to_sdk_segment(node) for node in component.nodes])
    if isinstance(component, Node):
        return SDKNode(
            sender_id=str(component.uin or "0"),
            sender_name=component.name or None,
            content=[to_sdk_segment(c) for c in component.content],
        )
    if isinstance(component, Poke):
        return SDKPoke(
            poke_type=str(component.poke_type or "126"),
            user_id=component.target_id(),
        )
    if isinstance(component, Json):
        return SDKJson(data=component.data)
    if isinstance(component, Share):
        return SDKShare(
            url=component.url,
            title=component.title,
            content=component.content or "",
            image=component.image or "",
        )
    if isinstance(component, Location):
        return SDKLocation(
            lat=float(component.lat),
            lon=float(component.lon),
            title=component.title or "",
            content=component.content or "",
        )
    if isinstance(component, Music):
        return SDKMusic(
            music_type=str(component._type or "custom"),
            id=int(component.id or 0),
            url=component.url or "",
            audio=component.audio or "",
            title=component.title or "",
            content=component.content or "",
            image=component.image or "",
        )
    if isinstance(component, Button):
        return SDKButton(
            label=component.label,
            action_id=component.action_id,
            url=component.url,
            data=component.data,
            style=component.style,
            emoji=component.emoji,
            disabled=bool(component.disabled),
        )
    if isinstance(component, ActionRow):
        return SDKActionRow([to_sdk_segment(btn) for btn in component.buttons])  # type: ignore[arg-type]
    if isinstance(component, ButtonInteraction):
        return SDKButtonInteraction(
            action_id=component.action_id,
            interaction_id=component.interaction_id,
            data=component.data,
            source_message_id=component.source_message_id,
            callback_data=component.callback_data,
        )
    if isinstance(component, UIInteraction):
        view_ctx = component.view
        return SDKUIInteraction(
            action_id=component.action_id,
            interaction_id=component.interaction_id,
            data=component.data,
            source=component.source,
            source_message_id=component.source_message_id,
            view=SDKViewContext(
                id=view_ctx.id,
                name=view_ctx.name,
                version=view_ctx.version,
                revision=view_ctx.revision,
                data=dict(view_ctx.data),
            ),
        )
    if isinstance(component, Unknown):
        return SDKUnknownSegment(
            segment_type="Unknown",
            data={"text": component.text},
        )
    raise TypeError(f"unsupported message component: {type(component)!r}")


def from_sdk_segment(segment: MessageSegment) -> Any:
    """Convert one SDK segment back into the compat component."""
    if isinstance(segment, SDKPlain):
        return Plain(segment.text)
    if isinstance(segment, SDKAtAll):
        return AtAll()
    if isinstance(segment, SDKAt):
        return At(qq=segment.user_id, name=segment.name or "")
    if isinstance(segment, SDKReply):
        return Reply(
            id=segment.id,
            sender_id=segment.sender_id or "",
            sender_nickname=segment.sender_name or "",
            message_str=segment.text or "",
        )
    if isinstance(segment, SDKImage):
        source = segment.source
        if isinstance(source, str):
            return Image(file=source, url=source)
        return Image(file=source)
    if isinstance(segment, SDKRecord):
        source = segment.source
        if isinstance(source, str):
            return Record(file=source, url=source)
        return Record(file=source)
    if isinstance(segment, SDKVideo):
        source = segment.source
        if isinstance(source, str):
            return Video(file=source, url=source)
        return Video(file=source)
    if isinstance(segment, SDKFace):
        return Face(id=segment.id)
    if isinstance(segment, SDKForward):
        return Forward(id=segment.id)
    if isinstance(segment, SDKFile):
        source = segment.source
        file_comp = File(name=segment.filename or "")
        if isinstance(source, str):
            file_comp.url = source
        else:
            file_comp.file_ = source
        return file_comp
    if isinstance(segment, SDKNodes):
        return Nodes([from_sdk_segment(node) for node in segment.nodes])
    if isinstance(segment, SDKNode):
        return Node(
            content=[from_sdk_segment(c) for c in segment.content],
            uin=segment.sender_id,
            name=segment.sender_name or "",
        )
    if isinstance(segment, SDKPoke):
        return Poke(poke_type=segment.poke_type, user_id=segment.user_id)
    if isinstance(segment, SDKJson):
        return Json(
            data=dict(segment.data)
            if isinstance(segment.data, dict) or hasattr(segment.data, "items")
            else segment.data
        )
    if isinstance(segment, SDKShare):
        return Share(
            url=segment.url,
            title=segment.title,
            content=segment.content,
            image=segment.image,
        )
    if isinstance(segment, SDKLocation):
        return Location(
            lat=segment.lat,
            lon=segment.lon,
            title=segment.title,
            content=segment.content,
        )
    if isinstance(segment, SDKMusic):
        return Music(
            _type=segment.music_type,
            id=segment.id,
            url=segment.url,
            audio=segment.audio,
            title=segment.title,
            content=segment.content,
            image=segment.image,
        )
    if isinstance(segment, SDKButton):
        return Button(
            label=segment.label,
            action_id=segment.action_id,
            url=segment.url,
            data=segment.data,
            style=segment.style,
            emoji=segment.emoji,
            disabled=segment.disabled,
        )
    if isinstance(segment, SDKActionRow):
        return ActionRow([from_sdk_segment(btn) for btn in segment.buttons])
    if isinstance(segment, SDKButtonInteraction):
        return ButtonInteraction(
            action_id=segment.action_id,
            interaction_id=segment.interaction_id,
            data=segment.data,
            source_message_id=segment.source_message_id,
            callback_data=segment.callback_data,
        )
    if isinstance(segment, SDKUIInteraction):
        return UIInteraction(
            action_id=segment.action_id,
            interaction_id=segment.interaction_id,
            data=segment.data,
            source=segment.source,
            source_message_id=segment.source_message_id,
            view=ViewContext(
                id=segment.view.id,
                name=segment.view.name,
                version=segment.view.version,
                revision=segment.view.revision,
                data=dict(segment.view.data),
            ),
        )
    if isinstance(segment, SDKUnknownSegment):
        if segment.segment_type == "Poke":
            return Poke(
                user_id=segment.data.get("user_id"),
                poke_type=segment.data.get("poke_type", "126"),
            )
        if segment.segment_type == "Json":
            return Json(data=segment.data.get("data"))
        if segment.segment_type == "Share":
            return Share(
                url=str(segment.data.get("url", "")),
                title=str(segment.data.get("title", "")),
                content=str(segment.data.get("content", "")),
                image=str(segment.data.get("image", "")),
            )
    return UnknownComponent(segment)


class BaseMessageComponent:
    """Legacy base component; structural typing covers the real usage."""

    type: Any = "unknown"

    def toDict(self) -> dict:
        return {"type": getattr(self.type, "value", self.type), "data": {}}


class UnknownComponent(BaseMessageComponent):
    """Compat placeholder for segments without a legacy counterpart."""

    def __init__(self, segment: MessageSegment) -> None:
        self.segment = segment
        self.type = getattr(segment, "type", "unknown")


class ComponentType(enum.Enum):
    """Legacy component type enum (labels only)."""

    Plain = "Plain"
    Face = "Face"
    Record = "Record"
    Video = "Video"
    At = "At"
    AtAll = "AtAll"
    RPS = "RPS"
    Dice = "Dice"
    Shake = "Shake"
    Share = "Share"
    Contact = "Contact"
    Location = "Location"
    Music = "Music"
    Image = "Image"
    Reply = "Reply"
    Poke = "Poke"
    Forward = "Forward"
    Node = "Node"
    Nodes = "Nodes"
    Json = "Json"
    ActionRow = "ActionRow"
    Button = "Button"
    ButtonInteraction = "ButtonInteraction"
    UIInteraction = "UIInteraction"
    Unknown = "Unknown"
    File = "File"


async def _register_media_to_file_service(
    source: Any, *, filename: str | None = None
) -> str:
    """Register one legacy media source with Host file_token_service and return URL."""
    from .star import StarTools

    ctx = StarTools._bound()
    cfg = ctx._snapshot.get("config") or {}
    callback_host = str(cfg.get("callback_api_base") or "").strip().removesuffix("/")
    if not callback_host:
        raise RuntimeError(
            "callback_api_base is not configured; file service unavailable"
        )
    resolved = _media_source(None, source)
    if isinstance(resolved, str) and resolved.startswith(("http://", "https://")):
        return resolved
    token = await ctx._ctx.assets.issue_download_token(resolved, filename=filename)
    return f"{callback_host}/api/file/{token}"


class Plain(BaseMessageComponent):
    """Legacy Plain component."""

    type = ComponentType.Plain

    def __init__(self, text: str, **_: Any) -> None:
        self.text = text

    def toDict(self) -> dict:
        return {"type": "text", "data": {"text": self.text}}


class At(BaseMessageComponent):
    """Legacy At component; qq carries the user id."""

    type = ComponentType.At

    def __init__(self, qq: Any = None, name: str = "", **_: Any) -> None:
        self.qq = qq
        self.name = name

    def toDict(self) -> dict:
        return {"type": "at", "data": {"qq": str(self.qq)}}


class AtAll(At):
    type = ComponentType.AtAll

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(qq="all", **kwargs)


class Reply(BaseMessageComponent):
    """Legacy Reply component."""

    type = ComponentType.Reply

    def __init__(
        self,
        id: Any = "",
        sender_id: Any = "",
        sender_nickname: str = "",
        message_str: str = "",
        **_: Any,
    ) -> None:
        self.id = id
        self.sender_id = sender_id
        self.sender_nickname = sender_nickname
        self.message_str = message_str

    def toDict(self) -> dict:
        return {"type": "reply", "data": {"id": str(self.id)}}


class Image(BaseMessageComponent):
    """Legacy Image component with the old file/url/path field trio."""

    type = ComponentType.Image

    def __init__(
        self,
        file: Any = "",
        url: str | None = "",
        path: str | None = "",
        **_: Any,
    ) -> None:
        self.file = file
        self.url = url
        self.path = path

    @staticmethod
    def fromURL(url: str, **kwargs: Any) -> Image:
        return Image(file=url, url=url, **kwargs)

    @staticmethod
    def fromFileSystem(path: Any, **kwargs: Any) -> Image:
        from ...assets import AssetRef

        if isinstance(path, AssetRef):
            return Image(file=path, **kwargs)
        return Image(file=str(path), path=str(path), **kwargs)

    @staticmethod
    def fromBase64(base64_str: str, **kwargs: Any) -> Image:
        return Image(file=f"base64://{base64_str}", **kwargs)

    @staticmethod
    def fromBytes(data: bytes, **kwargs: Any) -> Image:
        return Image(file=data, **kwargs)

    def toDict(self) -> dict:
        return {"type": "image", "data": {"file": self.file}}

    async def register_to_file_service(self) -> str:
        """Stage this image with Host file_token_service and return its URL."""
        return await _register_media_to_file_service(self.url or self.file)


class Record(BaseMessageComponent):
    """Legacy Record (voice) component."""

    type = ComponentType.Record

    def __init__(self, file: Any = "", url: str | None = "", **_: Any) -> None:
        self.file = file
        self.url = url

    async def register_to_file_service(self) -> str:
        """Stage this audio file with Host file_token_service and return its URL."""
        return await _register_media_to_file_service(self.url or self.file)


class Video(BaseMessageComponent):
    """Legacy Video component."""

    type = ComponentType.Video

    def __init__(self, file: Any = "", url: str | None = "", **_: Any) -> None:
        self.file = file
        self.url = url

    async def register_to_file_service(self) -> str:
        """Stage this video file with Host file_token_service and return its URL."""
        return await _register_media_to_file_service(self.url or self.file)


class Face(BaseMessageComponent):
    """Legacy Face (platform emoji) component."""

    type = ComponentType.Face

    def __init__(self, id: int = 0, **_: Any) -> None:
        self.id = id


class Forward(BaseMessageComponent):
    """Legacy Forward (merged-forward reference) component."""

    type = ComponentType.Forward

    def __init__(self, id: str = "", **_: Any) -> None:
        self.id = id


class File(BaseMessageComponent):
    """Legacy File message segment."""

    type = ComponentType.File

    def __init__(self, name: str = "", file: str = "", url: str = "") -> None:
        self.name = name
        self.file_ = file
        self.url = url

    @property
    def file(self) -> Any:
        return self.url or self.file_

    async def get_file(self, allow_return_url: bool = False) -> Any:
        """Return URL or local path/source of this file component."""
        if allow_return_url and self.url:
            return self.url
        return self.file_ or self.url

    async def register_to_file_service(self) -> str:
        """Stage this file with Host file_token_service and return its URL."""
        return await _register_media_to_file_service(
            self.url or self.file_,
            filename=self.name or None,
        )


class Node(BaseMessageComponent):
    """Legacy merged-forward node."""

    type = ComponentType.Node

    def __init__(
        self,
        content: Any,
        id: Any = 0,
        name: str = "",
        uin: Any = "0",
        seq: Any = "",
        time: Any = 0,
        **_: Any,
    ) -> None:
        if isinstance(content, Node):
            content = [content]
        self.id = id
        self.name = name
        self.uin = uin
        self.content: list = list(content or [])
        self.seq = seq
        self.time = time


class Nodes(BaseMessageComponent):
    """Legacy merged-forward node list."""

    type = ComponentType.Nodes

    def __init__(self, nodes: list | None = None, **_: Any) -> None:
        self.nodes: list = list(nodes or [])


class Poke(BaseMessageComponent):
    """Legacy poke component."""

    type = ComponentType.Poke

    def __init__(
        self,
        poke_type: Any = "126",
        user_id: Any = None,
        id: Any = None,
        qq: Any = None,
        **extra: Any,
    ) -> None:
        legacy_type = extra.pop("type", None)
        if poke_type in (None, "", "poke", "Poke"):
            poke_type = legacy_type
        if poke_type in (None, "", "poke", "Poke"):
            poke_type = "126"
        self.poke_type = str(poke_type)
        self._type = self.poke_type
        self.id = id
        self.qq = qq
        self.user_id = user_id

    def target_id(self) -> str | None:
        """Return normalized poke target ID."""
        for value in (self.user_id, self.id, self.qq):
            if value is None:
                continue
            text = str(value).strip()
            if text and text != "0":
                return text
        return None


class Json(BaseMessageComponent):
    """Legacy JSON card component."""

    type = ComponentType.Json

    def __init__(self, data: Any = None, **_: Any) -> None:
        self.data = data


class Share(BaseMessageComponent):
    """Legacy link-share card component."""

    type = ComponentType.Share

    def __init__(
        self,
        url: str = "",
        title: str = "",
        content: str = "",
        image: str = "",
        **_: Any,
    ) -> None:
        self.url = url
        self.title = title
        self.content = content
        self.image = image


class Location(BaseMessageComponent):
    """Legacy location component (coordinates plus optional labels)."""

    type = ComponentType.Location

    def __init__(
        self,
        lat: float = 0.0,
        lon: float = 0.0,
        title: str = "",
        content: str = "",
        **_: Any,
    ) -> None:
        self.lat = lat
        self.lon = lon
        self.title = title
        self.content = content


class Music(BaseMessageComponent):
    """Legacy music card component."""

    type = ComponentType.Music

    def __init__(
        self,
        _type: str = "custom",
        id: int = 0,
        url: str = "",
        audio: str = "",
        title: str = "",
        content: str = "",
        image: str = "",
        **extra: Any,
    ) -> None:
        self._type = str(extra.pop("music_type", _type) or "custom")
        self.id = int(id or 0)
        self.url = url
        self.audio = audio
        self.title = title
        self.content = content
        self.image = image


class Button(BaseMessageComponent):
    """Legacy portable interactive button component."""

    type = ComponentType.Button

    def __init__(
        self,
        label: str,
        action_id: str | None = None,
        url: str | None = None,
        data: Any = None,
        style: str = "secondary",
        emoji: str | None = None,
        disabled: bool = False,
        **_: Any,
    ) -> None:
        if not str(label).strip():
            raise ValueError("Button label must not be empty.")
        if (action_id is None) == (url is None):
            raise ValueError("Button requires exactly one of action_id or url.")
        self.type = ComponentType.Button
        self.label = label
        self.action_id = action_id
        self.url = url
        self.data = data
        self.style = style
        self.emoji = emoji
        self.disabled = disabled

    @classmethod
    def callback(
        cls,
        label: str,
        action_id: str,
        data: Any = None,
        *,
        style: str = "secondary",
        emoji: str | None = None,
        disabled: bool = False,
    ) -> Button:
        """Create a callback button bound to a button_action handler."""
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
        style: str = "secondary",
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


class ActionRow(BaseMessageComponent):
    """Legacy horizontal row of 1-5 interactive buttons."""

    type = ComponentType.ActionRow

    def __init__(self, buttons: list[Button] | tuple[Button, ...], **_: Any) -> None:
        btn_list = list(buttons)
        if not 1 <= len(btn_list) <= 5:
            raise ValueError("ActionRow requires between 1 and 5 buttons.")
        self.type = ComponentType.ActionRow
        self.buttons = btn_list


class ButtonInteraction(BaseMessageComponent):
    """Legacy inbound callback button click component."""

    type = ComponentType.ButtonInteraction

    def __init__(
        self,
        action_id: str,
        interaction_id: str,
        data: Any = None,
        source_message_id: str | None = None,
        callback_data: str | None = None,
        **_: Any,
    ) -> None:
        self.type = ComponentType.ButtonInteraction
        self.action_id = action_id
        self.interaction_id = interaction_id
        self.data = data
        self.source_message_id = source_message_id
        self.callback_data = callback_data


class ViewContext:
    """Legacy snapshot of the ChatUI card that initiated an interaction."""

    def __init__(
        self,
        id: str,
        name: str,
        version: int = 1,
        revision: int = 0,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.version = version
        self.revision = revision
        self.data = dict(data or {})


class UIInteraction(BaseMessageComponent):
    """Legacy authenticated ChatUI view interaction component."""

    type = ComponentType.UIInteraction

    def __init__(
        self,
        action_id: str,
        interaction_id: str,
        view: ViewContext,
        data: Any = None,
        source: str = "view",
        source_message_id: str | None = None,
        **_: Any,
    ) -> None:
        self.type = ComponentType.UIInteraction
        self.action_id = action_id
        self.interaction_id = interaction_id
        self.data = data
        self.source = source
        self.source_message_id = source_message_id
        self.view = view


class Unknown(BaseMessageComponent):
    """Legacy unknown component preserving the raw text payload."""

    type = ComponentType.Unknown

    def __init__(self, text: str = "", **_: Any) -> None:
        self.text = text


class EventResultType(enum.Enum):
    """Legacy event result type (propagation decision)."""

    CONTINUE = enum.auto()
    STOP = enum.auto()


class ResultContentType(enum.Enum):
    """Legacy result content type."""

    LLM_RESULT = enum.auto()
    AGENT_RUNNER_ERROR = enum.auto()
    GENERAL_RESULT = enum.auto()
    STREAMING_RESULT = enum.auto()
    STREAMING_FINISH = enum.auto()


class MessageChain:
    """Legacy mutable message chain."""

    def __init__(
        self,
        chain: list | None = None,
        use_t2i_: bool | None = None,
        use_markdown_: bool | None = None,
        type: str | None = None,
        **_: Any,
    ) -> None:
        self.chain: list = list(chain or [])
        self.use_t2i_ = use_t2i_
        self.use_markdown_ = use_markdown_
        self.type = type

    def derive(self, chain: list | None = None) -> MessageChain:
        """Create a new chain inheriting this chain's metadata flags."""
        return MessageChain(
            chain=chain if chain is not None else [],
            use_t2i_=self.use_t2i_,
            use_markdown_=self.use_markdown_,
            type=self.type,
        )

    def message(self, message: str) -> MessageChain:
        self.chain.append(Plain(message))
        return self

    def at(self, name: str, qq: Any) -> MessageChain:
        self.chain.append(At(name=name, qq=qq))
        return self

    def at_all(self) -> MessageChain:
        self.chain.append(AtAll())
        return self

    def error(self, message: str) -> MessageChain:
        # Deprecated in the in-process core; kept as an alias of message().
        return self.message(message)

    def url_image(self, url: str) -> MessageChain:
        self.chain.append(Image.fromURL(url))
        return self

    def file_image(self, path: Any) -> MessageChain:
        self.chain.append(Image.fromFileSystem(path))
        return self

    def base64_image(self, base64_str: str) -> MessageChain:
        self.chain.append(Image.fromBase64(base64_str))
        return self

    def use_t2i(self, use_t2i: bool) -> MessageChain:
        self.use_t2i_ = use_t2i
        return self

    def use_markdown(self, use: bool | None = True) -> MessageChain:
        self.use_markdown_ = use
        return self

    def get_plain_text(self, with_other_comps_mark: bool = False) -> str:
        if not with_other_comps_mark:
            return " ".join(c.text for c in self.chain if isinstance(c, Plain))
        texts = []
        for comp in self.chain:
            if isinstance(comp, Plain):
                texts.append(comp.text)
            elif isinstance(comp, Json):
                texts.append(f"{comp.data}")
            else:
                texts.append(f"[{comp.__class__.__name__}]")
        return " ".join(texts)

    def squash_plain(self) -> MessageChain | None:
        """Merge all Plain segments into the first one, preserving order."""
        if not self.chain:
            return None
        new_chain = []
        first_plain = None
        plain_texts = []
        for comp in self.chain:
            if isinstance(comp, Plain):
                if first_plain is None:
                    first_plain = comp
                    new_chain.append(comp)
                plain_texts.append(comp.text)
            else:
                new_chain.append(comp)
        if first_plain is not None:
            first_plain.text = "".join(plain_texts)
        self.chain = new_chain
        return self

    def to_sdk(self) -> SDKMessageChain:
        """Convert to the new immutable chain."""
        return SDKMessageChain(*[to_sdk_segment(c) for c in self.chain])

    @staticmethod
    def from_sdk(chain: SDKMessageChain) -> MessageChain:
        """Build a compat chain from the new SDK chain."""
        return MessageChain(chain=[from_sdk_segment(s) for s in chain])


class MessageEventResult(MessageChain):
    """Legacy message event result: a chain plus the propagation decision."""

    def __init__(self) -> None:
        super().__init__()
        self.result_type = EventResultType.CONTINUE
        self.result_content_type = ResultContentType.GENERAL_RESULT
        self.async_stream: Any = None

    def set_chain(self, chain: MessageChain | list) -> MessageEventResult:
        self.chain = list(chain.chain if isinstance(chain, MessageChain) else chain)
        return self

    def stop_event(self) -> MessageEventResult:
        self.result_type = EventResultType.STOP
        return self

    def continue_event(self) -> MessageEventResult:
        self.result_type = EventResultType.CONTINUE
        return self

    def is_stopped(self) -> bool:
        return self.result_type == EventResultType.STOP

    def set_result_content_type(self, typ: ResultContentType) -> MessageEventResult:
        self.result_content_type = typ
        return self

    def set_async_stream(self, stream: Any) -> MessageEventResult:
        self.async_stream = stream
        return self

    def is_llm_result(self) -> bool:
        return self.result_content_type == ResultContentType.LLM_RESULT

    def is_model_result(self) -> bool:
        return self.result_content_type in (
            ResultContentType.LLM_RESULT,
            ResultContentType.AGENT_RUNNER_ERROR,
        )

    def to_sdk_result(self) -> SDKMessageResult | None:
        """Convert to the new result; None when empty and not stopped."""
        propagation = Propagation.STOP if self.is_stopped() else Propagation.CONTINUE
        if not self.chain:
            if self.is_stopped():
                from ...results import EventResult

                return EventResult(propagation=propagation)
            return None
        return SDKMessageResult(
            propagation=propagation,
            message=MessageChain(chain=self.chain).to_sdk(),
        )


ComponentTypes = {
    # Mirror of the old core's name -> component class registry.
    "plain": Plain,
    "text": Plain,
    "image": Image,
    "record": Record,
    "video": Video,
    "file": File,
    "face": Face,
    "at": At,
    "share": Share,
    "reply": Reply,
    "poke": Poke,
    "forward": Forward,
    "node": Node,
    "nodes": Nodes,
    "actionrow": ActionRow,
    "button": Button,
    "buttoninteraction": ButtonInteraction,
    "uiinteraction": UIInteraction,
    "music": Music,
    "json": Json,
    "location": Location,
    "unknown": Unknown,
}
