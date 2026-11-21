from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from ..errors import InvalidRequest

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RequestFrame:
    """Represent a Host request."""

    id: str
    method: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze request parameters after construction."""
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


@dataclass(frozen=True, slots=True)
class ResponseFrame:
    """Represent a successful response."""

    id: str
    result: Any = None


@dataclass(frozen=True, slots=True)
class YieldFrame:
    """Represent one suspended handler result."""

    id: str
    sequence: int
    result: Any = None


@dataclass(frozen=True, slots=True)
class AckFrame:
    """Acknowledge one handler yield and allow it to resume."""

    id: str
    sequence: int


@dataclass(frozen=True, slots=True)
class CancelFrame:
    """Cancel an active handler invocation."""

    id: str


@dataclass(frozen=True, slots=True)
class ErrorFrame:
    """Represent a stable protocol or runtime error."""

    id: str
    code: str
    message: str


ProtocolFrame: TypeAlias = (
    RequestFrame | ResponseFrame | YieldFrame | AckFrame | CancelFrame | ErrorFrame
)


def encode_frame(frame: ProtocolFrame) -> bytes:
    """Encode one protocol frame as newline-delimited JSON.

    Args:
        frame: Frame to encode.

    Returns:
        UTF-8 JSON bytes terminated by one newline.

    Raises:
        InvalidRequest: The frame contains a value that JSON cannot represent.
    """
    if isinstance(frame, RequestFrame):
        data = {
            "type": "request",
            "id": frame.id,
            "method": frame.method,
            "params": dict(frame.params),
        }
    elif isinstance(frame, ResponseFrame):
        data = {"type": "response", "id": frame.id, "result": frame.result}
    elif isinstance(frame, YieldFrame):
        data = {
            "type": "yield",
            "id": frame.id,
            "sequence": frame.sequence,
            "result": frame.result,
        }
    elif isinstance(frame, AckFrame):
        data = {
            "type": "ack",
            "id": frame.id,
            "sequence": frame.sequence,
        }
    elif isinstance(frame, CancelFrame):
        data = {"type": "cancel", "id": frame.id}
    elif isinstance(frame, ErrorFrame):
        data = {
            "type": "error",
            "id": frame.id,
            "code": frame.code,
            "message": frame.message,
        }
    else:
        raise InvalidRequest(f"unsupported protocol frame: {type(frame)!r}")

    try:
        encoded = (
            json.dumps(
                data,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise InvalidRequest(f"protocol frame is not JSON serializable: {exc}") from exc
    if len(encoded) > MAX_FRAME_BYTES:
        raise InvalidRequest("protocol frame exceeds the size limit")
    return encoded


def decode_frame(data: bytes | str) -> ProtocolFrame:
    """Decode and validate one protocol frame.

    Args:
        data: UTF-8 JSON bytes or text.

    Returns:
        Parsed protocol frame.

    Raises:
        InvalidRequest: The input is malformed or has an unsupported frame type.
    """
    if len(data) > MAX_FRAME_BYTES:
        raise InvalidRequest("protocol frame exceeds the size limit")
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidRequest(f"invalid protocol JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise InvalidRequest("protocol frame must be a JSON object")

    frame_type = payload.get("type")
    frame_id = payload.get("id")
    if not isinstance(frame_id, str) or not frame_id:
        raise InvalidRequest("protocol frame id must be a non-empty string")

    if frame_type == "request":
        method = payload.get("method")
        params = payload.get("params", {})
        if not isinstance(method, str) or not method:
            raise InvalidRequest("request method must be a non-empty string")
        if not isinstance(params, dict):
            raise InvalidRequest("request params must be a JSON object")
        return RequestFrame(id=frame_id, method=method, params=params)
    if frame_type == "response":
        return ResponseFrame(id=frame_id, result=payload.get("result"))
    if frame_type == "yield":
        sequence = payload.get("sequence")
        if type(sequence) is not int or sequence < 1:
            raise InvalidRequest("yield sequence must be a positive integer")
        return YieldFrame(
            id=frame_id,
            sequence=sequence,
            result=payload.get("result"),
        )
    if frame_type == "ack":
        sequence = payload.get("sequence")
        if type(sequence) is not int or sequence < 1:
            raise InvalidRequest("ack sequence must be a positive integer")
        return AckFrame(id=frame_id, sequence=sequence)
    if frame_type == "cancel":
        return CancelFrame(id=frame_id)
    if frame_type == "error":
        code = payload.get("code")
        message = payload.get("message")
        if not isinstance(code, str) or not code:
            raise InvalidRequest("error code must be a non-empty string")
        if not isinstance(message, str):
            raise InvalidRequest("error message must be a string")
        return ErrorFrame(id=frame_id, code=code, message=message)
    raise InvalidRequest(f"unsupported protocol frame type: {frame_type!r}")
