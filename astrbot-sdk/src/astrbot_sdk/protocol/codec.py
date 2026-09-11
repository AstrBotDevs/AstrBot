from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, cast

import msgpack

from .messages import ProtocolMessage, parse_message


class ProtocolCodec(ABC):
    @abstractmethod
    def encode_message(self, message: ProtocolMessage) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def decode_message(
        self,
        payload: ProtocolMessage | bytes | str | dict[str, Any],
    ) -> ProtocolMessage:
        raise NotImplementedError


class JsonProtocolCodec(ProtocolCodec):
    def encode_message(self, message: ProtocolMessage) -> bytes:
        return message.model_dump_json(exclude_none=True).encode("utf-8")

    def decode_message(
        self,
        payload: ProtocolMessage | bytes | str | dict[str, Any],
    ) -> ProtocolMessage:
        return parse_message(payload)


class MsgpackProtocolCodec(ProtocolCodec):
    def encode_message(self, message: ProtocolMessage) -> bytes:
        payload = msgpack.packb(
            message.model_dump(exclude_none=True), use_bin_type=True
        )
        return cast(bytes, payload)

    def decode_message(
        self,
        payload: ProtocolMessage | bytes | str | dict[str, Any],
    ) -> ProtocolMessage:
        if not isinstance(payload, bytes):
            return parse_message(payload)
        try:
            unpacked = msgpack.unpackb(payload, raw=False, strict_map_key=True)
        except (
            msgpack.ExtraData,
            msgpack.FormatError,
            msgpack.StackError,
            ValueError,
        ) as exc:
            raise ValueError(str(exc)) from exc
        return parse_message(unpacked)


__all__ = [
    "JsonProtocolCodec",
    "MsgpackProtocolCodec",
    "ProtocolCodec",
]
