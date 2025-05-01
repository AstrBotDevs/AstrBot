"""
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
"""

import base64
import json
import os
import uuid
import asyncio
import typing as T
from enum import Enum
from pydantic.v1 import BaseModel
from astrbot.core import logger
from astrbot.core.utils.io import download_image_by_url, file_to_base64, download_file


class ComponentType(Enum):
    Plain = "Plain"  # 纯文本消息
    Face = "Face"  # QQ表情
    Record = "Record"  # 语音
    Video = "Video"  # 视频
    At = "At"  # At
    Node = "Node"  # 转发消息的一个节点
    Nodes = "Nodes"  # 转发消息的多个节点
    Poke = "Poke"  # QQ 戳一戳
    Image = "Image"  # 图片
    Reply = "Reply"  # 回复
    Forward = "Forward"  # 转发消息
    File = "File"  # 文件

    RPS = "RPS"  # TODO
    Dice = "Dice"  # TODO
    Shake = "Shake"  # TODO
    Anonymous = "Anonymous"  # TODO
    Share = "Share"
    Contact = "Contact"  # TODO
    Location = "Location"  # TODO
    Music = "Music"
    RedBag = "RedBag"
    Xml = "Xml"
    Json = "Json"
    CardImage = "CardImage"
    TTS = "TTS"
    Unknown = "Unknown"

    WechatEmoji = "WechatEmoji"  # Wechat 下的 emoji 表情包


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
            output += ",%s=%s" % (
                k,
                str(v)
                .replace("&", "&amp;")
                .replace(",", "&#44;")
                .replace("[", "&#91;")
                .replace("]", "&#93;"),
            )
        output += "]"
        return output

    def toDict(self):
        data = {}
        for k, v in self.__dict__.items():
            if k == "type" or v is None:
                continue
            if k == "_type":
                k = "type"
            data[k] = v
        return {"type": self.type.lower(), "data": data}


class Plain(BaseMessageComponent):
    type: ComponentType = "Plain"
    text: str
    convert: T.Optional[bool] = True  # 若为 False 则直接发送未转换 CQ 码的消息

    def __init__(self, text: str, convert: bool = True, **_):
        super().__init__(text=text, convert=convert, **_)

    def toString(self):  # 没有 [CQ:plain] 这种东西，所以直接导出纯文本
        if not self.convert:
            return self.text
        return (
            self.text.replace("&", "&amp;").replace("[", "&#91;").replace("]", "&#93;")
        )


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

    async def convert_to_file_path(self) -> str:
        """将这个语音统一转换为本地文件路径。这个方法避免了手动判断语音数据类型，直接返回语音数据的本地路径（如果是网络 URL, 则会自动进行下载）。

        Returns:
            str: 语音的本地路径，以绝对路径表示。
        """
        if self.file and self.file.startswith("file:///"):
            file_path = self.file[8:]
            return file_path
        elif self.file and self.file.startswith("http"):
            file_path = await download_image_by_url(self.file)
            return os.path.abspath(file_path)
        elif self.file and self.file.startswith("base64://"):
            bs64_data = self.file.removeprefix("base64://")
            image_bytes = base64.b64decode(bs64_data)
            file_path = f"data/temp/{uuid.uuid4()}.jpg"
            with open(file_path, "wb") as f:
                f.write(image_bytes)
            return os.path.abspath(file_path)
        elif os.path.exists(self.file):
            file_path = self.file
            return os.path.abspath(file_path)
        else:
            raise Exception(f"not a valid file: {self.file}")

    async def convert_to_base64(self) -> str:
        """将语音统一转换为 base64 编码。这个方法避免了手动判断语音数据类型，直接返回语音数据的 base64 编码。

        Returns:
            str: 语音的 base64 编码，不以 base64:// 或者 data:image/jpeg;base64, 开头。
        """
        # convert to base64
        if self.file and self.file.startswith("file:///"):
            bs64_data = file_to_base64(self.file[8:])
        elif self.file and self.file.startswith("http"):
            file_path = await download_image_by_url(self.file)
            bs64_data = file_to_base64(file_path)
        elif self.file and self.file.startswith("base64://"):
            bs64_data = self.file
        elif os.path.exists(self.file):
            bs64_data = file_to_base64(self.file)
        else:
            raise Exception(f"not a valid file: {self.file}")
        bs64_data = bs64_data.removeprefix("base64://")
        return bs64_data


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
    file_unique: T.Optional[str] = ""  # 某些平台可能有图片缓存的唯一标识

    def __init__(self, file: T.Optional[str], **_):
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

    async def convert_to_file_path(self) -> str:
        """将这个图片统一转换为本地文件路径。这个方法避免了手动判断图片数据类型，直接返回图片数据的本地路径（如果是网络 URL, 则会自动进行下载）。

        Returns:
            str: 图片的本地路径，以绝对路径表示。
        """
        url = self.url if self.url else self.file
        if url and url.startswith("file:///"):
            image_file_path = url[8:]
            return image_file_path
        elif url and url.startswith("http"):
            image_file_path = await download_image_by_url(url)
            return os.path.abspath(image_file_path)
        elif url and url.startswith("base64://"):
            bs64_data = url.removeprefix("base64://")
            image_bytes = base64.b64decode(bs64_data)
            image_file_path = f"data/temp/{uuid.uuid4()}.jpg"
            with open(image_file_path, "wb") as f:
                f.write(image_bytes)
            return os.path.abspath(image_file_path)
        elif os.path.exists(url):
            image_file_path = url
            return os.path.abspath(image_file_path)
        else:
            raise Exception(f"not a valid file: {url}")

    async def convert_to_base64(self) -> str:
        """将这个图片统一转换为 base64 编码。这个方法避免了手动判断图片数据类型，直接返回图片数据的 base64 编码。

        Returns:
            str: 图片的 base64 编码，不以 base64:// 或者 data:image/jpeg;base64, 开头。
        """
        # convert to base64
        url = self.url if self.url else self.file
        if url and url.startswith("file:///"):
            bs64_data = file_to_base64(url[8:])
        elif url and url.startswith("http"):
            image_file_path = await download_image_by_url(url)
            bs64_data = file_to_base64(image_file_path)
        elif url and url.startswith("base64://"):
            bs64_data = url
        elif os.path.exists(url):
            bs64_data = file_to_base64(url)
        else:
            raise Exception(f"not a valid file: {url}")
        bs64_data = bs64_data.removeprefix("base64://")
        return bs64_data


class Reply(BaseMessageComponent):
    type: ComponentType = "Reply"
    id: T.Union[str, int]
    """所引用的消息 ID"""
    chain: T.Optional[T.List["BaseMessageComponent"]] = []
    """被引用的消息段列表"""
    sender_id: T.Optional[int] | T.Optional[str] = 0
    """被引用的消息对应的发送者的 ID"""
    sender_nickname: T.Optional[str] = ""
    """被引用的消息对应的发送者的昵称"""
    time: T.Optional[int] = 0
    """被引用的消息发送时间"""
    message_str: T.Optional[str] = ""
    """被引用的消息解析后的纯文本消息字符串"""

    text: T.Optional[str] = ""
    """deprecated"""
    qq: T.Optional[int] = 0
    """deprecated"""
    seq: T.Optional[int] = 0
    """deprecated"""

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
    """群合并转发消息"""

    type: ComponentType = "Node"
    id: T.Optional[int] = 0  # 忽略
    name: T.Optional[str] = ""  # qq昵称
    uin: T.Optional[int] = 0  # qq号
    content: T.Optional[T.Union[str, list, dict]] = ""  # 子消息段列表
    seq: T.Optional[T.Union[str, list]] = ""  # 忽略
    time: T.Optional[int] = 0

    def __init__(self, content: T.Union[str, list, dict, "Node", T.List["Node"]], **_):
        if isinstance(content, list):
            _content = None
            if all(isinstance(item, Node) for item in content):
                _content = [node.toDict() for node in content]
            else:
                _content = ""
                for chain in content:
                    _content += chain.toString()
            content = _content
        elif isinstance(content, Node):
            content = content.toDict()
        super().__init__(content=content, **_)

    def toString(self):
        # logger.warn("Protocol: node doesn't support stringify")
        return ""


class Nodes(BaseMessageComponent):
    type: ComponentType = "Nodes"
    nodes: T.List[Node]

    def __init__(self, nodes: T.List[Node], **_):
        super().__init__(nodes=nodes, **_)

    def toDict(self):
        return {"messages": [node.toDict() for node in self.nodes]}


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
    """
    文件消息段
    """

    type: ComponentType = "File"
    name: T.Optional[str] = ""  # 名字
    _file: T.Optional[str] = ""  # 本地路径
    url: T.Optional[str] = ""  # url
    _downloaded: bool = False  # 是否已经下载

    def __init__(self, name: str = "", file: str = "", url: str = ""):
        super().__init__(name=name, _file=file, url=url)

    @property
    def file(self) -> str:
        """
        获取文件路径，如果文件不存在但有URL，则同步下载文件

        Returns:
            str: 文件路径
        """
        if self._file and os.path.exists(self._file):
            return self._file

        if self.url and not self._downloaded:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    logger.warning(
                        "不可以在异步上下文中同步等待下载! 请使用 await get_file() 代替"
                    )
                    return ""
                else:
                    # 等待下载完成
                    loop.run_until_complete(self._download_file())

                    if self._file and os.path.exists(self._file):
                        return self._file
            except Exception as e:
                logger.error(f"文件下载失败: {e}")

        return ""

    @file.setter
    def file(self, value: str):
        """
        向前兼容, 设置file属性, 传入的参数可能是文件路径或URL

        Args:
            value (str): 文件路径或URL
        """
        if value.startswith("http://") or value.startswith("https://"):
            self.url = value
        else:
            self._file = value

    async def get_file(self) -> str:
        """
        异步获取文件
        To 插件开发者: 请注意在使用后清理下载的文件, 以免占用过多空间

        Returns:
            str: 文件路径
        """
        if self._file and os.path.exists(self._file):
            return self._file

        if self.url:
            await self._download_file()
            return self._file

        return ""

    async def _download_file(self):
        """下载文件"""
        if self._downloaded:
            return

        os.makedirs("data/download", exist_ok=True)
        filename = self.name or f"{uuid.uuid4().hex}"
        file_path = f"data/download/{filename}"

        await download_file(self.url, file_path)

        self._file = file_path
        self._downloaded = True


class WechatEmoji(BaseMessageComponent):
    type: ComponentType = "WechatEmoji"
    md5: T.Optional[str] = ""
    md5_len: T.Optional[int] = 0
    cdnurl: T.Optional[str] = ""

    def __init__(self, **_):
        super().__init__(**_)


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
    "nodes": Nodes,
    "xml": Xml,
    "json": Json,
    "cardimage": CardImage,
    "tts": TTS,
    "unknown": Unknown,
    "file": File,
    "WechatEmoji": WechatEmoji,
}
