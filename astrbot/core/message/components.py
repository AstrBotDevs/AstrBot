"""MIT License

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

import asyncio
import base64
import json
import os
import sys
import uuid
from enum import Enum
from pathlib import Path, PurePosixPath

if sys.version_info >= (3, 14):
    from pydantic import BaseModel
else:
    from pydantic.v1 import BaseModel

from astrbot.core import astrbot_config, file_token_service, logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.utils.io import download_file
from astrbot.core.utils.media_utils import MediaResolver, file_uri_to_path, is_file_uri


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
    RPS = "RPS"  # TODO
    Dice = "Dice"  # TODO
    Shake = "Shake"  # TODO
    Share = "Share"
    Contact = "Contact"  # TODO
    Location = "Location"  # TODO
    Music = "Music"
    Json = "Json"
    Unknown = "Unknown"


class BaseMessageComponent(BaseModel):
    type: ComponentType

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def toDict(self):
        data = {}
        for k, v in self.__dict__.items():
            if k == "type" or v is None:
                continue
            if k == "_type":
                k = "type"
            data[k] = v
        return {"type": self.type.lower(), "data": data}

    async def to_dict(self) -> dict:
        # 默认情况下，回退到旧的同步 toDict()
        return self.toDict()


class Plain(BaseMessageComponent):
    type: ComponentType = ComponentType.Plain
    text: str

    def __init__(self, text: str, convert: bool = True, **_) -> None:
        super().__init__(text=text, convert=convert, **_)

    def toDict(self) -> dict:
        return {"type": "text", "data": {"text": self.text}}

    async def to_dict(self) -> dict:
        return {"type": "text", "data": {"text": self.text}}


class Face(BaseMessageComponent):
    type: ComponentType = ComponentType.Face
    id: int

    def __init__(self, **_) -> None:
        super().__init__(**_)


class Record(BaseMessageComponent):
    type: ComponentType = ComponentType.Record
    file: str | None = ""
    url: str | None = ""
    # Original text content (e.g. TTS source text), used as caption in fallback scenarios
    text: str | None = None
    # 额外
    path: str | None = None

    def __init__(self, file: str | None, **_) -> None:
        for k in _:
            if k == "url":
                pass
                # Protocol.warn(f"go-cqhttp doesn't support send {self.type} by {k}")
        super().__init__(file=file, **_)

    @staticmethod
    def fromFileSystem(path, **_):
        file_path = Path(path).resolve(strict=False)
        return Record(file=file_path.as_uri(), path=str(file_path), **_)

    @staticmethod
    def fromURL(url: str, **_):
        if url.startswith("http://") or url.startswith("https://"):
            return Record(file=url, **_)
        raise Exception("not a valid url")

    @staticmethod
    def fromBase64(bs64_data: str, **_):
        return Record(file=f"base64://{bs64_data}", **_)

    @staticmethod
    def _decode_file_uri(uri: str) -> str:
        """解码 file:/// URI 为本地文件路径。

        file:///C:/Users/...  → C:/Users/...  (Windows)
        file:///home/user/... → /home/user/... (Linux)
        其中的 URL 编码（如 %20 空格）也会被解码。
        """
        return file_uri_to_path(uri)

    async def _resolve_file_source(self) -> str:
        """选择可用的文件源。

        NapCat 在 Windows 上可能只给 file 字段一个裸文件名（如 0d2bb1468a87d64414f8e563cc61c33c.amr），
        而真实路径在 url（如 file:///C:/Users/...）或 path（如 C:\\Users\\...）中。
        Image.convert_to_file_path 使用 self.url or self.file，Record 同样需要 fallback。
        """
        # 1) 优先尝试 file：如果它已包含完整 URI 或已知格式，直接使用
        if self.file:
            file_exists = False
            try:
                file_exists = os.path.exists(self.file)
            except OSError:
                pass
            if (
                is_file_uri(self.file)
                or self.file.startswith("http")
                or self.file.startswith("base64://")
                or self.file.startswith("data:")
                or file_exists
            ):
                return self.file

        # 2) 尝试 url（可能是 file:/// 或 http 链接）
        if self.url:
            url_exists = False
            decoded_url_exists = False
            try:
                url_exists = os.path.exists(self.url)
            except OSError:
                pass
            if is_file_uri(self.url):
                try:
                    decoded_url_exists = os.path.exists(self._decode_file_uri(self.url))
                except OSError:
                    pass
            if (
                is_file_uri(self.url)
                or self.url.startswith("http")
                or self.url.startswith("data:")
                or url_exists
                or decoded_url_exists
            ):
                return self.url

        # 3) 尝试 path（可能是 Windows 绝对路径如 C:\Users\...）
        if self.path:
            try:
                if os.path.exists(self.path):
                    return self.path
            except OSError:
                pass

        # 4) 最后裸返回 file（即使不行也要让调用方看到原始内容）
        return self.file or self.url or ""

    async def convert_to_file_path(self) -> str:
        """将这个语音统一转换为本地文件路径。这个方法避免了手动判断语音数据类型，直接返回语音数据的本地路径（如果是网络 URL, 则会自动进行下载）。

        Returns:
            str: 语音的本地路径，以绝对路径表示。

        """
        file_source = await self._resolve_file_source()
        if not file_source:
            raise Exception(f"not a valid file: {self.file}")
        return await MediaResolver(
            file_source,
            media_type="audio",
            default_suffix=".wav",
        ).to_path(target_format="wav")

    async def convert_to_base64(self) -> str:
        """将语音统一转换为 base64 编码。这个方法避免了手动判断语音数据类型，直接返回语音数据的 base64 编码。

        Returns:
            str: 语音的 base64 编码，不以 base64:// 或者 data:image/jpeg;base64, 开头。

        """
        file_source = await self._resolve_file_source()
        if not file_source:
            raise Exception(f"not a valid file: {self.file}")
        return await MediaResolver(
            file_source,
            media_type="audio",
            default_suffix=".wav",
        ).to_base64(target_format="wav")

    async def register_to_file_service(self) -> str:
        """将语音注册到文件服务。

        Returns:
            str: 注册后的URL

        Raises:
            Exception: 如果未配置 callback_api_base

        """
        callback_host = astrbot_config.get("callback_api_base")

        if not callback_host:
            raise Exception("未配置 callback_api_base，文件服务不可用")

        file_path = await self.convert_to_file_path()

        token = await file_token_service.register_file(file_path)

        logger.debug(f"已注册：{callback_host}/api/file/{token}")

        return f"{callback_host}/api/file/{token}"


class Video(BaseMessageComponent):
    type: ComponentType = ComponentType.Video
    file: str
    url: str | None = ""
    cover: str | None = ""
    # 额外
    path: str | None = ""

    def __init__(self, file: str, **_) -> None:
        super().__init__(file=file, **_)

    @staticmethod
    def fromFileSystem(path, **_):
        file_path = Path(path).resolve(strict=False)
        return Video(file=file_path.as_uri(), path=str(file_path), **_)

    @staticmethod
    def fromURL(url: str, **_):
        if url.startswith("http://") or url.startswith("https://"):
            return Video(file=url, **_)
        raise Exception("not a valid url")

    @staticmethod
    def fromBase64(base64_data: str, **_):
        return Video(file=f"base64://{base64_data}", **_)

    async def _resolve_file_source(self) -> str:
        for candidate in (self.file, self.url):
            if not candidate:
                continue
            candidate_exists = False
            try:
                candidate_exists = os.path.exists(candidate)
            except OSError:
                pass
            if (
                is_file_uri(candidate)
                or candidate.startswith("http")
                or candidate.startswith("base64://")
                or candidate.startswith("data:")
                or candidate_exists
            ):
                return candidate

        if self.path:
            try:
                if os.path.exists(self.path):
                    return self.path
            except OSError:
                pass

        return self.file or self.url or ""

    async def convert_to_file_path(self) -> str:
        """将这个视频统一转换为本地文件路径。这个方法避免了手动判断视频数据类型，直接返回视频数据的本地路径（如果是网络 URL，则会自动进行下载）。

        Returns:
            str: 视频的本地路径，以绝对路径表示。

        """
        file_source = await self._resolve_file_source()
        if not file_source:
            raise Exception(f"not a valid file: {self.file}")

        if is_file_uri(file_source):
            return file_uri_to_path(file_source)
        if file_source.startswith(("http://", "https://", "base64://", "data:")):
            return await MediaResolver(
                file_source,
                media_type="video",
                default_suffix=".mp4",
            ).to_path()
        try:
            if os.path.exists(file_source):
                return os.path.abspath(file_source)
        except OSError:
            pass
        raise Exception(f"not a valid file: {file_source}")

    async def register_to_file_service(self) -> str:
        """将视频注册到文件服务。

        Returns:
            str: 注册后的URL

        Raises:
            Exception: 如果未配置 callback_api_base

        """
        callback_host = astrbot_config.get("callback_api_base")

        if not callback_host:
            raise Exception("未配置 callback_api_base，文件服务不可用")

        file_path = await self.convert_to_file_path()

        token = await file_token_service.register_file(file_path)

        logger.debug(f"已注册：{callback_host}/api/file/{token}")

        return f"{callback_host}/api/file/{token}"

    async def to_dict(self):
        """需要和 toDict 区分开，toDict 是同步方法"""
        url_or_path = self.file
        if url_or_path.startswith("http"):
            payload_file = url_or_path
        elif callback_host := astrbot_config.get("callback_api_base"):
            callback_host = str(callback_host).removesuffix("/")
            token = await file_token_service.register_file(url_or_path)
            payload_file = f"{callback_host}/api/file/{token}"
            logger.debug(f"Generated video file callback link: {payload_file}")
        else:
            payload_file = url_or_path
        return {
            "type": "video",
            "data": {
                "file": payload_file,
            },
        }


class At(BaseMessageComponent):
    type: ComponentType = ComponentType.At
    qq: int | str  # 此处str为all时代表所有人
    name: str | None = ""

    def __init__(self, **_) -> None:
        super().__init__(**_)

    def toDict(self):
        return {
            "type": "at",
            "data": {"qq": str(self.qq)},
        }


class AtAll(At):
    qq: str = "all"

    def __init__(self, **_) -> None:
        super().__init__(**_)


class RPS(BaseMessageComponent):  # TODO
    type: ComponentType = ComponentType.RPS

    def __init__(self, **_) -> None:
        super().__init__(**_)


class Dice(BaseMessageComponent):  # TODO
    type: ComponentType = ComponentType.Dice

    def __init__(self, **_) -> None:
        super().__init__(**_)


class Shake(BaseMessageComponent):  # TODO
    type: ComponentType = ComponentType.Shake

    def __init__(self, **_) -> None:
        super().__init__(**_)


class Share(BaseMessageComponent):
    type: ComponentType = ComponentType.Share
    url: str
    title: str
    content: str | None = ""
    image: str | None = ""

    def __init__(self, **_) -> None:
        super().__init__(**_)


class Contact(BaseMessageComponent):  # TODO
    type: ComponentType = ComponentType.Contact
    _type: str  # type 字段冲突
    id: int | None = 0

    def __init__(self, **_) -> None:
        super().__init__(**_)


class Location(BaseMessageComponent):  # TODO
    type: ComponentType = ComponentType.Location
    lat: float
    lon: float
    title: str | None = ""
    content: str | None = ""

    def __init__(self, **_) -> None:
        super().__init__(**_)


class Music(BaseMessageComponent):
    type: ComponentType = ComponentType.Music
    _type: str
    id: int | None = 0
    url: str | None = ""
    audio: str | None = ""
    title: str | None = ""
    content: str | None = ""
    image: str | None = ""

    def __init__(self, **_) -> None:
        # for k in _.keys():
        #     if k == "_type" and _[k] not in ["qq", "163", "xm", "custom"]:
        #         logger.warn(f"Protocol: {k}={_[k]} doesn't match values")
        super().__init__(**_)


class Image(BaseMessageComponent):
    type: ComponentType = ComponentType.Image
    file: str | None = ""
    _type: str | None = ""
    url: str | None = ""
    # 额外
    path: str | None = ""

    def __init__(self, file: str | None, **_) -> None:
        super().__init__(file=file, **_)

    @staticmethod
    def fromURL(url: str, **_):
        if url.startswith("http://") or url.startswith("https://"):
            return Image(file=url, **_)
        raise Exception("not a valid url")

    @staticmethod
    def fromFileSystem(path, **_):
        file_path = Path(path).resolve(strict=False)
        return Image(file=file_path.as_uri(), path=str(file_path), **_)

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
        url = self.url or self.file
        if not url:
            raise ValueError("No valid file or URL provided")
        return await MediaResolver(url, media_type="image").to_path()

    async def convert_to_base64(self) -> str:
        """将这个图片统一转换为 base64 编码。这个方法避免了手动判断图片数据类型，直接返回图片数据的 base64 编码。

        Returns:
            str: 图片的 base64 编码，不以 base64:// 或者 data:image/jpeg;base64, 开头。

        """
        # convert to base64
        url = self.url or self.file
        if not url:
            raise ValueError("No valid file or URL provided")
        return await MediaResolver(url, media_type="image").to_base64()

    async def register_to_file_service(self) -> str:
        """将图片注册到文件服务。

        Returns:
            str: 注册后的URL

        Raises:
            Exception: 如果未配置 callback_api_base

        """
        callback_host = astrbot_config.get("callback_api_base")

        if not callback_host:
            raise Exception("未配置 callback_api_base，文件服务不可用")

        file_path = await self.convert_to_file_path()

        token = await file_token_service.register_file(file_path)

        logger.debug(f"已注册：{callback_host}/api/file/{token}")

        return f"{callback_host}/api/file/{token}"


class Reply(BaseMessageComponent):
    type: ComponentType = ComponentType.Reply
    id: str | int
    """所引用的消息 ID"""
    chain: list["BaseMessageComponent"] | None = []
    """被引用的消息段列表"""
    sender_id: int | None | str = 0
    """被引用的消息对应的发送者的 ID"""
    sender_nickname: str | None = ""
    """被引用的消息对应的发送者的昵称"""
    time: int | None = 0
    """被引用的消息发送时间"""
    message_str: str | None = ""
    """被引用的消息解析后的纯文本消息字符串"""

    text: str | None = ""
    """deprecated"""
    qq: int | None = 0
    """deprecated"""
    seq: int | None = 0
    """deprecated"""

    def __init__(self, **_) -> None:
        super().__init__(**_)

    def toDict(self):
        """仅输出 id 字段，符合 OneBot V11 reply 段标准格式。"""
        return {"type": "reply", "data": {"id": str(self.id)}}


class Poke(BaseMessageComponent):
    type: ComponentType = ComponentType.Poke
    _type: str | int = "126"
    id: int | str | None = 0
    qq: int | str | None = 0  # deprecated: legacy field, kept for compatibility

    def __init__(self, poke_type: str | int | None = None, **_) -> None:
        # Backward compatible with old signature: Poke(type="poke", ...)
        legacy_type = _.pop("type", None)
        if poke_type is None:
            poke_type = legacy_type
        if poke_type in (None, "", "poke", "Poke"):
            poke_type = "126"
        super().__init__(_type=str(poke_type), **_)

    def target_id(self) -> str | None:
        """Return normalized target id, compatible with old `qq` field."""
        for value in (self.id, self.qq):
            if value is None:
                continue
            text = str(value).strip()
            if text and text != "0":
                return text
        return None

    def toDict(self):
        target_id = self.target_id()
        data = {"type": str(self._type or "126")}
        if target_id:
            data["id"] = target_id
        return {"type": "poke", "data": data}


class Forward(BaseMessageComponent):
    type: ComponentType = ComponentType.Forward
    id: str

    def __init__(self, **_) -> None:
        super().__init__(**_)


class Node(BaseMessageComponent):
    """群合并转发消息"""

    type: ComponentType = ComponentType.Node
    id: int | None = 0  # 忽略
    name: str | None = ""  # qq昵称
    uin: str | None = "0"  # qq号
    content: list[BaseMessageComponent] = []
    seq: str | list | None = ""  # 忽略
    time: int | None = 0  # 忽略

    def __init__(self, content: list[BaseMessageComponent], **_) -> None:
        if isinstance(content, Node):
            # back
            content = [content]
        super().__init__(content=content, **_)

    async def to_dict(self):
        data_content = []
        for comp in self.content:
            if isinstance(comp, Image | Record):
                # For Image and Record segments, we convert them to base64
                bs64 = await comp.convert_to_base64()
                data_content.append(
                    {
                        "type": comp.type.lower(),
                        "data": {"file": f"base64://{bs64}"},
                    },
                )
            elif isinstance(comp, Plain):
                # For Plain segments, we need to handle the plain differently
                d = await comp.to_dict()
                data_content.append(d)
            elif isinstance(comp, File):
                # For File segments, we need to handle the file differently
                d = await comp.to_dict()
                data_content.append(d)
            elif isinstance(comp, Node | Nodes):
                # For Node segments, we recursively convert them to dict
                d = await comp.to_dict()
                data_content.append(d)
            else:
                d = comp.toDict()
                data_content.append(d)
        return {
            "type": "node",
            "data": {
                "user_id": str(self.uin),
                "nickname": self.name,
                "content": data_content,
            },
        }


class Nodes(BaseMessageComponent):
    type: ComponentType = ComponentType.Nodes
    nodes: list[Node]

    def __init__(self, nodes: list[Node], **_) -> None:
        super().__init__(nodes=nodes, **_)

    def toDict(self):
        """Deprecated. Use to_dict instead"""
        ret = {
            "messages": [],
        }
        for node in self.nodes:
            d = node.toDict()
            ret["messages"].append(d)
        return ret

    async def to_dict(self) -> dict:
        """将 Nodes 转换为字典格式，适用于 OneBot JSON 格式"""
        ret = {"messages": []}
        for node in self.nodes:
            d = await node.to_dict()
            ret["messages"].append(d)
        return ret


class Json(BaseMessageComponent):
    type: ComponentType = ComponentType.Json
    data: dict

    def __init__(self, data: str | dict, **_) -> None:
        if isinstance(data, str):
            data = json.loads(data)
        super().__init__(data=data, **_)


class Unknown(BaseMessageComponent):
    type: ComponentType = ComponentType.Unknown
    text: str


def _sanitize_file_component_name(name: str | None) -> str:
    if not name:
        return "file"

    normalized = str(name).replace("\\", "/")
    basename = PurePosixPath(normalized).name.replace("\x00", "").strip()
    for char in ':*?"<>|':
        basename = basename.replace(char, "_")
    if basename in {"", ".", ".."}:
        return "file"
    return basename


class File(BaseMessageComponent):
    """文件消息段"""

    type: ComponentType = ComponentType.File
    name: str | None = ""  # 名字
    file_: str | None = ""  # 本地路径
    url: str | None = ""  # url

    def __init__(self, name: str, file: str = "", url: str = "") -> None:
        """文件消息段。"""
        super().__init__(name=name, file_=file, url=url)

    @property
    def file(self) -> str:
        """获取文件路径，如果文件不存在但有URL，则同步下载文件

        Returns:
            str: 文件路径

        """
        if self.file_:
            path = (
                file_uri_to_path(self.file_) if is_file_uri(self.file_) else self.file_
            )
            if os.path.exists(path):
                return os.path.abspath(path)

        if self.url:
            try:
                # 检查是否有正在运行的 event loop
                asyncio.get_running_loop()
                logger.warning(
                    "不可以在异步上下文中同步等待下载! "
                    "这个警告通常发生于某些逻辑试图通过 <File>.file 获取文件消息段的文件内容。"
                    "请使用 await get_file() 代替直接获取 <File>.file 字段",
                )
                return ""
            except RuntimeError:
                # 没有运行中的 event loop，可以同步执行
                try:
                    # 使用 asyncio.run 安全地创建和关闭事件循环
                    asyncio.run(self._download_file())
                except Exception:
                    logger.exception("文件下载失败")

                if self.file_ and os.path.exists(self.file_):
                    return os.path.abspath(self.file_)

        return ""

    @file.setter
    def file(self, value: str) -> None:
        """向前兼容, 设置file属性, 传入的参数可能是文件路径或URL

        Args:
            value (str): 文件路径或URL

        """
        if value.startswith("http://") or value.startswith("https://"):
            self.url = value
        else:
            self.file_ = value

    async def get_file(self, allow_return_url: bool = False) -> str:
        """异步获取文件。请注意在使用后清理下载的文件, 以免占用过多空间

        Args:
            allow_return_url: 是否允许以文件 http 下载链接的形式返回，这允许您自行控制是否需要下载文件。
            注意，如果为 True，也可能返回文件路径。
        Returns:
            str: 文件路径或者 http 下载链接

        """
        if allow_return_url and self.url:
            return self.url

        if self.file_:
            path = self.file_
            if is_file_uri(path):
                path = file_uri_to_path(path)

            if os.path.exists(path):
                return os.path.abspath(path)

        if self.url:
            await self._download_file()
            if self.file_:
                path = self.file_
                if is_file_uri(path):
                    path = file_uri_to_path(path)
                return os.path.abspath(path)

        return ""

    async def _download_file(self) -> None:
        """下载文件"""
        if not self.url:
            raise ValueError("Download failed: No URL provided in File component.")
        download_dir = Path(get_astrbot_temp_path())
        download_dir.mkdir(parents=True, exist_ok=True)
        if self.name:
            safe_name = _sanitize_file_component_name(self.name)
            name = Path(safe_name).stem
            ext = Path(safe_name).suffix
            filename = f"fileseg_{name}_{uuid.uuid4().hex[:8]}{ext}"
        else:
            filename = f"fileseg_{uuid.uuid4().hex}"
        file_path = download_dir / filename
        await download_file(self.url, str(file_path))
        self.file_ = str(file_path.resolve())

    async def register_to_file_service(self) -> str:
        """将文件注册到文件服务。

        Returns:
            str: 注册后的URL

        Raises:
            Exception: 如果未配置 callback_api_base

        """
        callback_host = astrbot_config.get("callback_api_base")

        if not callback_host:
            raise Exception("未配置 callback_api_base，文件服务不可用")

        file_path = await self.get_file()

        token = await file_token_service.register_file(file_path)

        logger.debug(f"已注册：{callback_host}/api/file/{token}")

        return f"{callback_host}/api/file/{token}"

    async def to_dict(self):
        """需要和 toDict 区分开，toDict 是同步方法"""
        url_or_path = await self.get_file(allow_return_url=True)
        if url_or_path.startswith("http"):
            payload_file = url_or_path
        elif callback_host := astrbot_config.get("callback_api_base"):
            callback_host = str(callback_host).removesuffix("/")
            token = await file_token_service.register_file(url_or_path)
            payload_file = f"{callback_host}/api/file/{token}"
            logger.debug(f"Generated file callback link: {payload_file}")
        else:
            payload_file = url_or_path
        return {
            "type": "file",
            "data": {
                "name": self.name,
                "file": payload_file,
            },
        }


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
}
