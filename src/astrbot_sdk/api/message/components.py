from __future__ import annotations
from enum import Enum

from pydantic import BaseModel, Field
from typing import Literal


class ComponentType(str, Enum):
    # Basic Segment Types
    Plain = "Plain"  # plain text message
    Image = "Image"  # image
    Record = "Record"  # audio
    Video = "Video"  # video
    File = "File"  # file attachment

    # IM-specific Segment Types
    Face = "Face"  # Emoji segment for Tencent QQ platform
    At = "At"  # mention a user in IM apps
    Node = "Node"  # a node in a forwarded message
    Nodes = "Nodes"  # a forwarded message consisting of multiple nodes
    Poke = "Poke"  # a poke message for Tencent QQ platform
    Reply = "Reply"  # a reply message segment
    Forward = "Forward"  # a forwarded message segment
    RPS = "RPS"
    Dice = "Dice"
    Shake = "Shake"
    Share = "Share"
    Contact = "Contact"
    Location = "Location"
    Music = "Music"
    Json = "Json"
    Unknown = "Unknown"
    WechatEmoji = "WechatEmoji"


CompT = ComponentType


class BaseMessageComponent(BaseModel):
    type: CompT

    def to_dict(self) -> dict:
        """Unified dict format"""
        return self.model_dump()


class Plain(BaseMessageComponent):
    """Represents a plain text message segment."""

    type: Literal[CompT.Plain] = CompT.Plain
    text: str


class Image(BaseMessageComponent):
    type: Literal[CompT.Image] = CompT.Image
    file: str
    """base64-encoded image data, or file path, or HTTP URL"""


class Record(BaseMessageComponent):
    type: Literal[CompT.Record] = CompT.Record
    file: str
    """base64-encoded audio data, or file path, or HTTP URL"""


class Video(BaseMessageComponent):
    type: Literal[CompT.Video] = CompT.Video
    file: str
    """The video file URL."""


class File(BaseMessageComponent):
    type: Literal[CompT.File] = CompT.File
    file_name: str
    mime_type: str | None = None
    file: str
    """The file URL."""


class At(BaseMessageComponent):
    type: Literal[CompT.At] = CompT.At
    user_id: str | None = None
    user_name: str | None = None


class AtAll(At):
    user_id: str = "all"


class Reply(BaseMessageComponent):
    type: Literal[CompT.Reply] = CompT.Reply
    id: str | int
    """所引用的消息 ID"""
    chain: list[BaseMessageComponent] | None = []
    """被引用的消息段列表"""
    sender_id: int | None | str = 0
    """被引用的消息对应的发送者的 ID"""
    sender_nickname: str | None = ""
    """被引用的消息对应的发送者的昵称"""
    time: int | None = 0
    """被引用的消息发送时间"""
    message_str: str | None = ""
    """被引用的消息解析后的纯文本消息字符串"""


class Node(BaseMessageComponent):
    type: Literal[CompT.Node] = CompT.Node
    sender_id: str
    nickname: str | None = None
    content: list[BaseMessageComponent] = Field(default_factory=list)


class Nodes(BaseMessageComponent):
    type: Literal[CompT.Nodes] = CompT.Nodes
    nodes: list[Node] = Field(default_factory=list)


class Face(BaseMessageComponent):
    type: Literal[CompT.Face] = CompT.Face
    id: int


class RPS(BaseMessageComponent):
    type: Literal[CompT.RPS] = CompT.RPS


class Dice(BaseMessageComponent):
    type: Literal[CompT.Dice] = CompT.Dice


class Shake(BaseMessageComponent):
    type: Literal[CompT.Shake] = CompT.Shake


class Share(BaseMessageComponent):
    type: Literal[CompT.Share] = CompT.Share
    url: str
    title: str
    content: str | None = ""
    image: str | None = ""


class Contact(BaseMessageComponent):
    type: Literal[CompT.Contact] = CompT.Contact
    _type: str  # type 字段冲突
    id: int | None = 0


class Location(BaseMessageComponent):
    type: Literal[CompT.Location] = CompT.Location
    lat: float
    lon: float
    title: str | None = ""
    content: str | None = ""


class Music(BaseMessageComponent):
    type: Literal[CompT.Music] = CompT.Music
    _type: str
    id: int | None = 0
    url: str | None = ""
    audio: str | None = ""
    title: str | None = ""
    content: str | None = ""
    image: str | None = ""


class Poke(BaseMessageComponent):
    type: Literal[CompT.Poke] = CompT.Poke
    id: int | None = 0
    qq: int | None = 0


class Forward(BaseMessageComponent):
    type: Literal[CompT.Forward] = CompT.Forward
    id: str


class Json(BaseMessageComponent):
    type: Literal[CompT.Json] = CompT.Json
    data: dict


class Unknown(BaseMessageComponent):
    type: Literal[CompT.Unknown] = CompT.Unknown
    text: str


class WechatEmoji(BaseMessageComponent):
    type: Literal[CompT.WechatEmoji] = CompT.WechatEmoji
    md5: str | None = ""
    md5_len: int | None = 0
    cdnurl: str | None = ""

    def __init__(self, **_):
        super().__init__(**_)


ComponentTypes = {
    # Basic Message Segments
    "plain": Plain,
    "text": Plain,
    "image": Image,
    "record": Record,
    "video": Video,
    "file": File,
    # IM-specific Message Segments
    "face": Face,
    "at": At,
    "rps": RPS,
    "dice": Dice,
    "shake": Shake,
    "share": Share,
    "contact": Contact,
    "location": Location,
    "music": Music,
    "reply": Reply,
    "poke": Poke,
    "forward": Forward,
    "node": Node,
    "nodes": Nodes,
    "json": Json,
    "unknown": Unknown,
    "WechatEmoji": WechatEmoji,
}
