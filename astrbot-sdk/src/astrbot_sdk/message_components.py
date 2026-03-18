"""SDK message component compatibility layer.

该模块有意避免在导入时导入遗留核心组件模块。
SDK工作线程应该保持轻量级并且不能依赖于主机核心引导程序
仅用于构造消息对象的路径。
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import os
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlretrieve

from ._star_runtime import current_runtime_context
from .errors import AstrBotError

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_RECORD_SUFFIXES = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}
_VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".avi"}


def _temp_path(prefix: str, suffix: str = "") -> Path:
    return Path(tempfile.gettempdir()) / f"{prefix}_{uuid.uuid4().hex}{suffix}"


def _guess_suffix_from_url(url: str, fallback: str = "") -> str:
    suffix = Path(urlparse(url).path).suffix
    return suffix or fallback


def _download_to_temp(url: str, prefix: str, fallback_suffix: str = "") -> str:
    target = _temp_path(prefix, _guess_suffix_from_url(url, fallback_suffix))
    urlretrieve(url, target)
    return str(target.resolve())


def _stringify_mapping(mapping: Mapping[Any, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in mapping.items()}


async def _register_file_to_service(path: str) -> str:
    context = current_runtime_context()
    if context is None:
        raise RuntimeError("message component file service requires runtime context")
    return await context._register_file_url(path)


def _reply_chain_payloads_sync(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [component_to_payload_sync(item) for item in value]


async def _reply_chain_payloads(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [await component_to_payload(item) for item in value]


def _coerce_reply_chain(value: Any) -> list[BaseMessageComponent]:
    if not isinstance(value, list):
        return []
    if value and all(isinstance(item, BaseMessageComponent) for item in value):
        return list(value)
    return payloads_to_components(value)


def _component_type_name(component: Any) -> str:
    raw_type = getattr(component, "type", "unknown")
    normalized = getattr(raw_type, "value", raw_type)
    return str(normalized or "unknown").lower()


def _resolve_media_kind(url: str, kind: str = "auto") -> str:
    normalized_kind = str(kind).strip().lower() or "auto"
    if normalized_kind != "auto":
        return normalized_kind
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _RECORD_SUFFIXES:
        return "record"
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    return "file"


def build_media_component_from_url(
    url: str,
    *,
    kind: str = "auto",
) -> BaseMessageComponent:
    url_text = str(url).strip()
    if not url_text:
        raise AstrBotError.invalid_input(
            "MediaHelper.from_url requires a non-empty url"
        )
    resolved_kind = _resolve_media_kind(url_text, kind=kind)
    if resolved_kind == "image":
        return Image.fromURL(url_text)
    if resolved_kind in {"record", "audio"}:
        return Record.fromURL(url_text)
    if resolved_kind == "video":
        return Video.fromURL(url_text)
    if resolved_kind == "file":
        return File(name=_filename_from_url(url_text), url=url_text)
    raise AstrBotError.invalid_input(
        f"Unsupported media kind: {kind}",
        details={"kind": kind, "url": url_text},
    )


def _filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    return name or "download"


class BaseMessageComponent:
    type: str = "unknown"

    def toDict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key == "type" or value is None:
                continue
            data["type" if key == "_type" else key] = value
        return {"type": str(self.type).lower(), "data": data}

    async def to_dict(self) -> dict[str, Any]:
        return self.toDict()


class Plain(BaseMessageComponent):
    type = "plain"

    def __init__(self, text: str, convert: bool = True, **_: Any) -> None:
        self.text = text
        self.convert = convert

    def toDict(self) -> dict[str, Any]:
        return {"type": "text", "data": {"text": self.text.strip()}}

    async def to_dict(self) -> dict[str, Any]:
        return {"type": "text", "data": {"text": self.text}}


class At(BaseMessageComponent):
    type = "at"

    def __init__(self, qq: int | str, name: str | None = "", **_: Any) -> None:
        self.qq = qq
        self.name = name or ""

    def toDict(self) -> dict[str, Any]:
        return {"type": "at", "data": {"qq": str(self.qq)}}


class AtAll(At):
    def __init__(self, **_: Any) -> None:
        super().__init__(qq="all")


class Reply(BaseMessageComponent):
    type = "reply"

    def __init__(self, **kwargs: Any) -> None:
        self.id = kwargs.get("id", "")
        self.chain = _coerce_reply_chain(kwargs.get("chain", []))
        self.sender_id = kwargs.get("sender_id", 0)
        self.sender_nickname = kwargs.get("sender_nickname", "")
        self.time = kwargs.get("time", 0)
        self.message_str = kwargs.get("message_str", "")
        self.text = kwargs.get("text", "")
        self.qq = kwargs.get("qq", 0)
        self.seq = kwargs.get("seq", 0)

    def toDict(self) -> dict[str, Any]:
        return {
            "type": "reply",
            "data": {
                "id": self.id,
                "chain": _reply_chain_payloads_sync(self.chain),
                "sender_id": self.sender_id,
                "sender_nickname": self.sender_nickname,
                "time": self.time,
                "message_str": self.message_str,
                "text": self.text,
                "qq": self.qq,
                "seq": self.seq,
            },
        }

    async def to_dict(self) -> dict[str, Any]:
        return {
            "type": "reply",
            "data": {
                "id": self.id,
                "chain": await _reply_chain_payloads(self.chain),
                "sender_id": self.sender_id,
                "sender_nickname": self.sender_nickname,
                "time": self.time,
                "message_str": self.message_str,
                "text": self.text,
                "qq": self.qq,
                "seq": self.seq,
            },
        }


class Image(BaseMessageComponent):
    type = "image"

    def __init__(self, file: str | None, **kwargs: Any) -> None:
        self.file = file or ""
        self._type = kwargs.get("_type", "")
        self.subType = kwargs.get("subType", 0)
        self.url = kwargs.get("url", "")
        self.cache = kwargs.get("cache", True)
        self.id = kwargs.get("id", 40000)
        self.c = kwargs.get("c", 2)
        self.path = kwargs.get("path", "")
        self.file_unique = kwargs.get("file_unique", "")

    @staticmethod
    def fromURL(url: str, **kwargs: Any) -> Image:
        return Image(url, **kwargs)

    @staticmethod
    def fromFileSystem(path: str, **kwargs: Any) -> Image:
        return Image(f"file:///{os.path.abspath(path)}", path=path, **kwargs)

    @staticmethod
    def fromBase64(base64_data: str, **kwargs: Any) -> Image:
        return Image(f"base64://{base64_data}", **kwargs)

    async def convert_to_file_path(self) -> str:
        url = self.url or self.file
        if not url:
            raise ValueError("No valid file or URL provided")
        if url.startswith("file:///"):
            return os.path.abspath(url[8:])
        if url.startswith(("http://", "https://")):
            return _download_to_temp(url, "imgseg", ".jpg")
        if url.startswith("base64://"):
            file_path = _temp_path("imgseg", ".jpg")
            file_path.write_bytes(base64.b64decode(url.removeprefix("base64://")))
            return str(file_path.resolve())
        if os.path.exists(url):
            return os.path.abspath(url)
        raise ValueError(f"not a valid file: {url}")

    async def register_to_file_service(self) -> str:
        return await _register_file_to_service(await self.convert_to_file_path())


class Record(BaseMessageComponent):
    type = "record"

    def __init__(self, file: str | None, **kwargs: Any) -> None:
        self.file = file or ""
        self.magic = kwargs.get("magic", False)
        self.url = kwargs.get("url", "")
        self.cache = kwargs.get("cache", True)
        self.proxy = kwargs.get("proxy", True)
        self.timeout = kwargs.get("timeout", 0)
        self.text = kwargs.get("text")
        self.path = kwargs.get("path")

    @staticmethod
    def fromFileSystem(path: str, **kwargs: Any) -> Record:
        return Record(f"file:///{os.path.abspath(path)}", path=path, **kwargs)

    @staticmethod
    def fromURL(url: str, **kwargs: Any) -> Record:
        return Record(url, **kwargs)

    async def convert_to_file_path(self) -> str:
        if self.file.startswith("file:///"):
            return os.path.abspath(self.file[8:])
        if self.file.startswith(("http://", "https://")):
            return _download_to_temp(self.file, "recordseg", ".dat")
        if self.file.startswith("base64://"):
            file_path = _temp_path("recordseg", ".dat")
            file_path.write_bytes(base64.b64decode(self.file.removeprefix("base64://")))
            return str(file_path.resolve())
        if os.path.exists(self.file):
            return os.path.abspath(self.file)
        raise ValueError(f"not a valid file: {self.file}")

    async def register_to_file_service(self) -> str:
        return await _register_file_to_service(await self.convert_to_file_path())


class Video(BaseMessageComponent):
    type = "video"

    def __init__(self, file: str, **kwargs: Any) -> None:
        self.file = file
        self.cover = kwargs.get("cover", "")
        self.c = kwargs.get("c", 2)
        self.path = kwargs.get("path", "")

    @staticmethod
    def fromFileSystem(path: str, **kwargs: Any) -> Video:
        return Video(f"file:///{os.path.abspath(path)}", path=path, **kwargs)

    @staticmethod
    def fromURL(url: str, **kwargs: Any) -> Video:
        return Video(url, **kwargs)

    async def convert_to_file_path(self) -> str:
        if self.file.startswith("file:///"):
            return os.path.abspath(self.file[8:])
        if self.file.startswith(("http://", "https://")):
            return _download_to_temp(self.file, "videoseg")
        if os.path.exists(self.file):
            return os.path.abspath(self.file)
        raise ValueError(f"not a valid file: {self.file}")

    async def register_to_file_service(self) -> str:
        return await _register_file_to_service(await self.convert_to_file_path())


class File(BaseMessageComponent):
    type = "file"

    def __init__(self, name: str, file: str = "", url: str = "") -> None:
        self.name = name
        self.file_ = file
        self.url = url

    @property
    def file(self) -> str:
        return self.file_

    @file.setter
    def file(self, value: str) -> None:
        if value.startswith(("http://", "https://")):
            self.url = value
        else:
            self.file_ = value

    async def get_file(self, allow_return_url: bool = False) -> str:
        if allow_return_url and self.url:
            return self.url
        if self.file_:
            path = self.file_
            if path.startswith("file://"):
                path = path[7:]
                if (
                    os.name == "nt"
                    and len(path) > 2
                    and path[0] == "/"
                    and path[2] == ":"
                ):
                    path = path[1:]
            if os.path.exists(path):
                return os.path.abspath(path)
        if self.url:
            suffix = Path(urlparse(self.url).path).suffix
            target = _download_to_temp(self.url, "fileseg", suffix)
            self.file_ = target
            return target
        return ""

    async def register_to_file_service(self) -> str:
        return await _register_file_to_service(await self.get_file())

    def toDict(self) -> dict[str, Any]:
        payload_file = self.url or self.file_
        return {
            "type": "file",
            "data": {
                "name": self.name,
                "file": payload_file,
            },
        }

    async def to_dict(self) -> dict[str, Any]:
        payload_file = await self.get_file(allow_return_url=True)
        return {
            "type": "file",
            "data": {
                "name": self.name,
                "file": payload_file,
            },
        }


class Poke(BaseMessageComponent):
    type = "poke"

    def __init__(self, poke_type: str | int | None = None, **kwargs: Any) -> None:
        legacy_type = kwargs.pop("type", None)
        if poke_type is None:
            poke_type = legacy_type
        if poke_type in (None, "", "poke", "Poke"):
            poke_type = "126"
        self._type = str(poke_type)
        self.id = kwargs.get("id")
        self.qq = kwargs.get("qq", 0)

    def target_id(self) -> str | None:
        for value in (self.id, self.qq):
            if value is None:
                continue
            text = str(value).strip()
            if text and text != "0":
                return text
        return None

    def toDict(self) -> dict[str, Any]:
        data = {"type": str(self._type or "126")}
        target_id = self.target_id()
        if target_id:
            data["id"] = target_id
        return {"type": "poke", "data": data}


class Forward(BaseMessageComponent):
    type = "forward"

    def __init__(self, id: str, **_: Any) -> None:
        self.id = id


class UnknownComponent(BaseMessageComponent):
    type = "unknown"

    def __init__(
        self,
        *,
        raw_type: str = "unknown",
        raw_data: dict[str, Any] | None = None,
    ) -> None:
        self.raw_type = raw_type
        self.raw_data = raw_data or {}

    def toDict(self) -> dict[str, Any]:
        return {
            "type": self.raw_type or "unknown",
            "data": dict(self.raw_data),
        }


def is_message_component(value: Any) -> bool:
    return isinstance(value, BaseMessageComponent)


def payload_to_component(payload: Any) -> BaseMessageComponent:
    if not isinstance(payload, dict):
        return UnknownComponent(raw_data={"value": payload})

    raw_type = str(payload.get("type", "unknown") or "unknown").lower()
    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}

    if raw_type in {"text", "plain"}:
        return Plain(str(data.get("text", "")), convert=False)
    if raw_type == "image":
        return Image(str(data.get("file") or data.get("url") or ""))
    if raw_type == "at":
        qq_value = data.get("qq")
        if str(qq_value).lower() == "all":
            return AtAll()
        qq = "" if qq_value is None else str(qq_value)
        return At(qq=qq, name=str(data.get("name", "")))
    if raw_type == "reply":
        return Reply(**data)
    if raw_type == "record":
        return Record(str(data.get("file") or data.get("url") or ""), **data)
    if raw_type == "video":
        return Video(str(data.get("file") or ""), **data)
    if raw_type == "file":
        file_value = str(data.get("file") or data.get("file_") or "")
        if not file_value:
            file_value = str(data.get("url") or "")
        return File(
            str(data.get("name", "")),
            file="" if file_value.startswith(("http://", "https://")) else file_value,
            url=file_value if file_value.startswith(("http://", "https://")) else "",
        )
    if raw_type == "poke":
        return Poke(
            poke_type=data.get("type"),
            id=data.get("id"),
            qq=data.get("qq"),
        )
    if raw_type == "forward":
        return Forward(id=str(data.get("id", "")))

    return UnknownComponent(raw_type=raw_type, raw_data=_stringify_mapping(data))


def payloads_to_components(payloads: list[Any]) -> list[BaseMessageComponent]:
    return [payload_to_component(item) for item in payloads]


def component_to_payload_sync(component: Any) -> dict[str, Any]:
    if isinstance(component, UnknownComponent):
        return component.toDict()
    if isinstance(component, Plain):
        return {"type": "text", "data": {"text": component.text}}
    if _component_type_name(component) == "reply":
        return {
            "type": "reply",
            "data": {
                "id": getattr(component, "id", ""),
                "chain": _reply_chain_payloads_sync(getattr(component, "chain", [])),
                "sender_id": getattr(component, "sender_id", 0),
                "sender_nickname": getattr(component, "sender_nickname", ""),
                "time": getattr(component, "time", 0),
                "message_str": getattr(component, "message_str", ""),
                "text": getattr(component, "text", ""),
                "qq": getattr(component, "qq", 0),
                "seq": getattr(component, "seq", 0),
            },
        }
    to_dict = getattr(component, "toDict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return _stringify_mapping(result)
    return {"type": "unknown", "data": {"value": str(component)}}


async def component_to_payload(component: Any) -> dict[str, Any]:
    if isinstance(component, (UnknownComponent, Plain)):
        return component_to_payload_sync(component)
    async_method = getattr(component, "to_dict", None)
    if callable(async_method):
        payload = async_method()
        if inspect.isawaitable(payload):
            result = await payload
            if isinstance(result, dict):
                return result
    return component_to_payload_sync(component)


class MediaHelper:
    @staticmethod
    async def from_url(
        url: str,
        *,
        kind: str = "auto",
    ) -> BaseMessageComponent:
        return build_media_component_from_url(url, kind=kind)

    @staticmethod
    async def download(url: str, save_dir: Path) -> Path:
        url_text = str(url).strip()
        if not url_text:
            raise AstrBotError.invalid_input(
                "MediaHelper.download requires a non-empty url"
            )
        parsed = urlparse(url_text)
        if parsed.scheme not in {"http", "https"}:
            raise AstrBotError.invalid_input(
                "MediaHelper.download only supports http/https urls",
                details={"url": url_text},
            )
        target_dir = Path(save_dir)
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AstrBotError.internal_error(
                f"Failed to prepare download directory: {target_dir}",
                details={"save_dir": str(target_dir)},
            ) from exc
        target_path = target_dir / _filename_from_url(url_text)
        try:
            await asyncio.to_thread(urlretrieve, url_text, target_path)
        except Exception as exc:
            raise AstrBotError.network_error(
                f"Failed to download media from '{url_text}'",
                details={"url": url_text},
            ) from exc
        return target_path.resolve()


__all__ = [
    "At",
    "AtAll",
    "BaseMessageComponent",
    "File",
    "Forward",
    "Image",
    "MediaHelper",
    "Plain",
    "Poke",
    "Record",
    "Reply",
    "UnknownComponent",
    "Video",
    "component_to_payload",
    "component_to_payload_sync",
    "is_message_component",
    "payload_to_component",
    "payloads_to_components",
]
