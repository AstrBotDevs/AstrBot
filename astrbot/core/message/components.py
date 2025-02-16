'''
MIT License

Copyright (c) 2021 Lxns-Network

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import base64
import json
import os
import typing as T
from enum import Enum
from pydantic.v1 import BaseModel

class ComponentType(Enum):
    Plain = "Plain"
    Face = "Face"
    Record = "Record"
    Video = "Video"
    At = "At"
    RPS = "RPS"  # TODO
    Dice = "Dice"  # TODO
    Shake = "Shake"  # TODO
    Anonymous = "Anonymous"  # TODO
    Share = "Share"
    Contact = "Contact"  # TODO
    Location = "Location"  # TODO
    Music = "Music"
    Image = "Image"
    Reply = "Reply"
    RedBag = "RedBag"
    Poke = "Poke"
    Forward = "Forward"
    Node = "Node"
    Xml = "Xml"
    Json = "Json"
    CardImage = "CardImage"
    TTS = "TTS"
    Unknown = "Unknown"
    File = "File"


class BaseMessageComponent(BaseModel):
    type: ComponentType

    def toString(self):
        output = f"[CQ:{self.type.lower()}"
        for k, v in self.__dict__.items():
            if k == "type" or v is None:
                continue
            if k == "_type":
                k = "type"
            if isinstance(v, bool):
                v = 1 if v else 0
            output += ",%s=%s" % (k, str(v).replace("&", "&amp;") \
                                  .replace(",", "&#44;") \
                                  .replace("[", "&#91;") \
                                  .replace("]", "&#93;"))
        output += "]"
        return output

    def toDict(self):
        data = dict()
        for k, v in self.__dict__.items():
            if k == "type" or v is None:
                continue
            if k == "_type":
                k = "type"
            data[k] = v
        return {
            "type": self.type.lower(),
            "data": data
        }


class Plain(BaseMessageComponent):
    type: ComponentType = "Plain"
    text: str
    convert: T.Optional[bool] = True  # 若为 False 则直接发送未转换 CQ 码的消息

    def __init__(self, text: str, convert: bool = True, **_):
        super().__init__(text=text, convert=convert, **_)

    def toString(self):  # 没有 [CQ:plain] 这种东西，所以直接导出纯文本
        if not self.convert:
            return self.text
        return self.text.replace("&", "&amp;") \
            .replace("[", "&#91;") \
            .replace("]", "&#93;")


class Face(BaseMessageComponent):
    type: ComponentType = "Face"
    id: int

    def __init__(self, **_):
        super().__init__(**_)


class Record(BaseMessageComponent):
    type: ComponentType = "Record"
    file: T.Optional[str] = ""
    magic: T.Optional[bool] = False
    url: T.Optional[str] = ""
    cache: T.Optional[bool] = True
    proxy: T.Optional[bool] = True
    timeout: T.Optional[int] = 0
    # 额外
    path: T.Optional[str]

    def __init__(self, file: T.Optional[str], **_):
        for k in _.keys():
            if k == "url":
                pass
                # Protocol.warn(f"go-cqhttp doesn't support send {self.type} by {k}")
        super().__init__(file=file, **_)

    @staticmethod
    def fromFileSystem(path, **_):
        return Record(file=f"file:///{os.path.abspath(path)}", path=path, **_)

    @staticmethod
    def fromURL(url: str, **_):
        if url.startswith("http://") or url.startswith("https://"):
            return Record(file=url, **_)
        raise Exception("not a valid url")


class Video(BaseMessageComponent):
    type: ComponentType = "Video"
    file: str
    cover: T.Optional[str] = ""
    c: T.Optional[int] = 2
    # 额外
    path: T.Optional[str] = ""

    def __init__(self, file: str, **_):
        # for k in _.keys():
        #     if k == "c" and _[k] not in [2, 3]:
        #         logger.warn(f"Protocol: {k}={_[k]} doesn't match values")
        super().__init__(file=file, **_)

    @staticmethod
    def fromFileSystem(path, **_):
        return Video(file=f"file:///{os.path.abspath(path)}", path=path, **_)

    @staticmethod
    def fromURL(url: str, **_):
        if url.startswith("http://") or url.startswith("https://"):
            return Video(file=url, **_)
        raise Exception("not a valid url")


class At(BaseMessageComponent):
    type: ComponentType = "At"
    qq: T.Union[int, str]  # 此处str为all时代表所有人
    name: T.Optional[str] = ""

    def __init__(self, **_):
        super().__init__(**_)


class AtAll(At):
    qq: str = "all"

    def __init__(self, **_):
        super().__init__(**_)


class RPS(BaseMessageComponent):  # TODO
    type: ComponentType = "RPS"

    def __init__(self, **_):
        super().__init__(**_)


class Dice(BaseMessageComponent):  # TODO
    type: ComponentType = "Dice"

    def __init__(self, **_):
        super().__init__(**_)


class Shake(BaseMessageComponent):  # TODO
    type: ComponentType = "Shake"

    def __init__(self, **_):
        super().__init__(**_)


class Anonymous(BaseMessageComponent):  # TODO
    type: ComponentType = "Anonymous"
    ignore: T.Optional[bool] = False

    def __init__(self, **_):
        super().__init__(**_)


class Share(BaseMessageComponent):
    type: ComponentType = "Share"
    url: str
    title: str
    content: T.Optional[str] = ""
    image: T.Optional[str] = ""

    def __init__(self, **_):
        super().__init__(**_)


class Contact(BaseMessageComponent):  # TODO
    type: ComponentType = "Contact"
    _type: str  # type 字段冲突
    id: T.Optional[int] = 0

    def __init__(self, **_):
        super().__init__(**_)


class Location(BaseMessageComponent):  # TODO
    type: ComponentType = "Location"
    lat: float
    lon: float
    title: T.Optional[str] = ""
    content: T.Optional[str] = ""

    def __init__(self, **_):
        super().__init__(**_)


class Music(BaseMessageComponent):
    type: ComponentType = "Music"
    _type: str
    id: T.Optional[int] = 0
    url: T.Optional[str] = ""
    audio: T.Optional[str] = ""
    title: T.Optional[str] = ""
    content: T.Optional[str] = ""
    image: T.Optional[str] = ""

    def __init__(self, **_):
        # for k in _.keys():
        #     if k == "_type" and _[k] not in ["qq", "163", "xm", "custom"]:
        #         logger.warn(f"Protocol: {k}={_[k]} doesn't match values")
        super().__init__(**_)


class Image(BaseMessageComponent):
    type: ComponentType = "Image"
    file: T.Optional[str] = ""
    _type: T.Optional[str] = ""
    subType: T.Optional[int] = 0
    url: T.Optional[str] = ""
    cache: T.Optional[bool] = True
    id: T.Optional[int] = 40000
    c: T.Optional[int] = 2
    # 额外
    path: T.Optional[str] = ""
    file_unique: T.Optional[str] = "" # 某些平台可能有图片缓存的唯一标识

    def __init__(self, file: T.Optional[str], **_):
        # for k in _.keys():
        #     if (k == "_type" and _[k] not in ["flash", "show", None]) or \
        #             (k == "c" and _[k] not in [2, 3]):
        #         logger.warn(f"Protocol: {k}={_[k]} doesn't match values")
        super().__init__(file=file, **_)

    @staticmethod
    def fromURL(url: str, **_):
        if url.startswith("http://") or url.startswith("https://"):
            return Image(file=url, **_)
        raise Exception("not a valid url")

    @staticmethod
    def fromFileSystem(path, **_):
        return Image(file=f"file:///{os.path.abspath(path)}", path=path, **_)

    @staticmethod
    def fromBase64(base64: str, **_):
        return Image(f"base64://{base64}", **_)

    @staticmethod
    def fromBytes(byte: bytes):
        return Image.fromBase64(base64.b64encode(byte).decode())

    @staticmethod
    def fromIO(IO):
        return Image.fromBytes(IO.read())


class Reply(BaseMessageComponent):
    type: ComponentType = "Reply"
    id: T.Union[str, int]
    text: T.Optional[str] = ""
    qq: T.Optional[int] = 0
    time: T.Optional[int] = 0
    seq: T.Optional[int] = 0

    def __init__(self, **_):
        super().__init__(**_)


class RedBag(BaseMessageComponent):
    type: ComponentType = "RedBag"
    title: str

    def __init__(self, **_):
        super().__init__(**_)


class Poke(BaseMessageComponent):
    type: str = ""
    id: T.Optional[int] = 0
    qq: T.Optional[int] = 0

    def __init__(self, type: str, **_):
        type = f"Poke:{type}"
        super().__init__(type=type, **_)


class Forward(BaseMessageComponent):
    type: ComponentType = "Forward"
    id: str

    def __init__(self, **_):
        super().__init__(**_)

class Node(BaseMessageComponent):
    '''群合并转发消息'''
    type: ComponentType = "Node"
    id: T.Optional[int] = 0 # 忽略
    name: T.Optional[str] = "" # qq昵称
    uin: T.Optional[int] = 0 # qq号
    content: T.Optional[T.Union[str, list]] = "" # 子消息段列表
    seq: T.Optional[T.Union[str, list]] = "" # 忽略
    time: T.Optional[int] = 0

    def __init__(self, content: T.Union[str, list], **_):
        if isinstance(content, list):
            _content = ""
            for chain in content:
                _content += chain.toString()
            content = _content
        super().__init__(content=content, **_)

    def toString(self):
        # logger.warn("Protocol: node doesn't support stringify")
        return ""


class Xml(BaseMessageComponent):
    type: ComponentType = "Xml"
    data: str
    resid: T.Optional[int] = 0
 
    def __init__(self, **_):
        super().__init__(**_)


class Json(BaseMessageComponent):
    type: ComponentType = "Json"
    data: T.Union[str, dict]
    resid: T.Optional[int] = 0

    def __init__(self, data, **_):
        if isinstance(data, dict):
            data = json.dumps(data)
        super().__init__(data=data, **_)


class CardImage(BaseMessageComponent):
    type: ComponentType = "CardImage"
    file: str
    cache: T.Optional[bool] = True
    minwidth: T.Optional[int] = 400
    minheight: T.Optional[int] = 400
    maxwidth: T.Optional[int] = 500
    maxheight: T.Optional[int] = 500
    source: T.Optional[str] = ""
    icon: T.Optional[str] = ""

    def __init__(self, **_):
        super().__init__(**_)

    @staticmethod
    def fromFileSystem(path, **_):
        return CardImage(file=f"file:///{os.path.abspath(path)}", **_)


class TTS(BaseMessageComponent):
    type: ComponentType = "TTS"
    text: str

    def __init__(self, **_):
        super().__init__(**_)


class Unknown(BaseMessageComponent):
    type: ComponentType = "Unknown"
    text: str

    def toString(self):
        return ""

class File(BaseMessageComponent):
    '''
    目前此消息段只适配了 Napcat。
    '''
    type: ComponentType = "File"
    name: T.Optional[str] = "" # 名字
    file: T.Optional[str] = "" # url（本地路径）
    
    def __init__(self, name: str, file: str):
        super().__init__(name=name, file=file)


ComponentTypes = {
    "plain": Plain,
    "text": Plain,
    "face": Face,
    "record": Record,
    "video": Video,
    "at": At,
    "rps": RPS,
    "dice": Dice,
    "shake": Shake,
    "anonymous": Anonymous,
    "share": Share,
    "contact": Contact,
    "location": Location,
    "music": Music,
    "image": Image,
    "reply": Reply,
    "redbag": RedBag,
    "poke": Poke,
    "forward": Forward,
    "node": Node,
    "xml": Xml,
    "json": Json,
    "cardimage": CardImage,
    "tts": TTS,
    "unknown": Unknown,
    'file': File,
}
