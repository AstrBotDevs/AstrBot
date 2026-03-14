from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

import msgpack

from .messages import ProtocolMessage, parse_message

StdioFraming = Literal["line", "length_prefixed"]
WebSocketFrameType = Literal["text", "binary"]
WireCodecName = Literal["json", "msgpack"]


class ProtocolCodec(ABC):
    name: WireCodecName
    stdio_framing: StdioFraming
    websocket_frame_type: WebSocketFrameType

    @abstractmethod
    def encode_message(self, message: ProtocolMessage) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def decode_message(self, payload: bytes | str) -> ProtocolMessage:
        raise NotImplementedError


class JsonProtocolCodec(ProtocolCodec):
    name: WireCodecName = "json"
    stdio_framing: StdioFraming = "line"
    websocket_frame_type: WebSocketFrameType = "text"

    def encode_message(self, message: ProtocolMessage) -> bytes:
        return message.model_dump_json(exclude_none=True).encode("utf-8")

    def decode_message(self, payload: bytes | str) -> ProtocolMessage:
        if isinstance(payload, bytes):
            return parse_message(payload.decode("utf-8"))
        return parse_message(payload)


class MsgpackProtocolCodec(ProtocolCodec):
    name: WireCodecName = "msgpack"
    stdio_framing: StdioFraming = "length_prefixed"
    websocket_frame_type: WebSocketFrameType = "binary"

    def encode_message(self, message: ProtocolMessage) -> bytes:
        return msgpack.packb(
            message.model_dump(exclude_none=True),
            use_bin_type=True,
        )

    def decode_message(self, payload: bytes | str) -> ProtocolMessage:
        if isinstance(payload, str):
            return parse_message(payload)
        return parse_message(msgpack.unpackb(payload, raw=False))


def make_protocol_codec(name: WireCodecName | str) -> ProtocolCodec:
    if name == "json":
        return JsonProtocolCodec()
    if name == "msgpack":
        return MsgpackProtocolCodec()
    raise ValueError(f"未知 wire codec: {name}")


__all__ = [
    "JsonProtocolCodec",
    "MsgpackProtocolCodec",
    "ProtocolCodec",
    "StdioFraming",
    "WebSocketFrameType",
    "WireCodecName",
    "make_protocol_codec",
]
