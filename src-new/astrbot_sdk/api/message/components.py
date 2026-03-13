"""旧版消息组件兼容类型。"""

from __future__ import annotations

import base64
from enum import Enum
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field


class ComponentType(str, Enum):
    Plain = "Plain"
    Image = "Image"
    Record = "Record"
    Video = "Video"
    File = "File"
    Face = "Face"
    At = "At"
    Node = "Node"
    Nodes = "Nodes"
    Poke = "Poke"
    Reply = "Reply"
    Forward = "Forward"
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
        return self.model_dump(mode="json")


class Plain(BaseMessageComponent):
    type: Literal[CompT.Plain] = CompT.Plain
    text: str


class Image(BaseMessageComponent):
    type: Literal[CompT.Image] = CompT.Image
    file: str = Field(validation_alias=AliasChoices("file", "url", "path"))

    @classmethod
    def fromBytes(cls, data: bytes) -> "Image":
        encoded = base64.b64encode(data).decode("ascii")
        return cls(file=f"base64://{encoded}")

    @classmethod
    def fromURL(cls, url: str) -> "Image":
        return cls(file=url)

    @classmethod
    def fromFileSystem(cls, path: str) -> "Image":
        return cls(file=path)


class Record(BaseMessageComponent):
    type: Literal[CompT.Record] = CompT.Record
    file: str = Field(validation_alias=AliasChoices("file", "url", "path"))

    @classmethod
    def fromURL(cls, url: str) -> "Record":
        return cls(file=url)

    @classmethod
    def fromFileSystem(cls, path: str) -> "Record":
        return cls(file=path)


class Video(BaseMessageComponent):
    type: Literal[CompT.Video] = CompT.Video
    file: str = Field(validation_alias=AliasChoices("file", "url", "path"))

    @classmethod
    def fromURL(cls, url: str) -> "Video":
        return cls(file=url)

    @classmethod
    def fromFileSystem(cls, path: str) -> "Video":
        return cls(file=path)


class File(BaseMessageComponent):
    type: Literal[CompT.File] = CompT.File
    file_name: str = Field(validation_alias=AliasChoices("file_name", "name"))
    mime_type: str | None = None
    file: str = Field(validation_alias=AliasChoices("file", "url", "path"))


class At(BaseMessageComponent):
    type: Literal[CompT.At] = CompT.At
    user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user_id", "qq"),
    )
    user_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("user_name", "name"),
    )


class AtAll(At):
    user_id: str = "all"


class Reply(BaseMessageComponent):
    type: Literal[CompT.Reply] = CompT.Reply
    id: str | int
    chain: list[BaseMessageComponent] = Field(default_factory=list)
    sender_id: int | str | None = 0
    sender_nickname: str | None = ""
    time: int | None = 0
    message_str: str | None = ""


class Node(BaseMessageComponent):
    type: Literal[CompT.Node] = CompT.Node
    sender_id: str = Field(validation_alias=AliasChoices("sender_id", "uin"))
    nickname: str | None = Field(
        default=None,
        validation_alias=AliasChoices("nickname", "name"),
    )
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
    _type: str
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


ComponentTypes = {
    "plain": Plain,
    "text": Plain,
    "image": Image,
    "record": Record,
    "video": Video,
    "file": File,
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
