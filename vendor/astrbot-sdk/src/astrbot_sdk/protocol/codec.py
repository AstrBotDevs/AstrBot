from __future__ import annotations

import types
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, TypeAlias, Union, get_args, get_origin, get_type_hints

from ..assets import AssetRef
from ..errors import InvalidRequest
from ..events import (
    UMO,
    CommandInvocation,
    MessageEvent,
    MessageRef,
    MessageType,
    Sender,
    SenderRole,
)
from ..message_components import (
    ActionRow,
    At,
    AtAll,
    Button,
    ButtonInteraction,
    Face,
    File,
    Forward,
    Image,
    Json,
    Location,
    MediaSegment,
    MessageSegment,
    Music,
    Node,
    Nodes,
    Plain,
    Poke,
    Record,
    Reply,
    Share,
    UIInteraction,
    UnknownSegment,
    Video,
    ViewContext,
)
from ..messages import MessageChain
from ..protocol_registry import (
    _PROTOCOL_DATACLASSES,
)
from ..results import EventResult, GroupUsage, MessageResult, Propagation, ViewResult

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)


def _coerce_value(annotation: Any, raw: Any) -> Any:
    """Coerce a decoded JSON value into one annotated field type.

    Args:
        annotation: Resolved field annotation.
        raw: Decoded JSON value.

    Returns:
        Value converted to the annotated shape.
    """
    if raw is None:
        return None
    if (
        isinstance(raw, dict)
        and set(raw) == {"$type", "value"}
        and raw["$type"] in _PROTOCOL_DATACLASSES
    ):
        # Nested registered dataclass, e.g. AssetRef inside an Any-typed field.
        return _decode_dataclass(_PROTOCOL_DATACLASSES[raw["$type"]], raw["value"])
    if (
        isinstance(raw, dict)
        and set(raw) == {"$type", "value"}
        and raw["$type"] == "bytes"
    ):
        import base64

        return base64.b64decode(str(raw["value"]).encode("ascii"))
    origin = get_origin(annotation)
    if origin is tuple:
        (item_type,) = get_args(annotation)[:1]
        return tuple(_coerce_value(item_type, item) for item in raw)
    if origin is list:
        (item_type,) = get_args(annotation)[:1]
        return [_coerce_value(item_type, item) for item in raw]
    if origin is dict:
        return dict(raw)
    if origin in (Union, types.UnionType):
        for option in get_args(annotation):
            if option is type(None):
                continue
            if option in (str, int, float, bool) and not isinstance(raw, option):
                # Primitive options must match exactly; otherwise more
                # specific options (dataclasses, tuples) never get a chance.
                continue
            try:
                return _coerce_value(option, raw)
            except (InvalidRequest, TypeError, ValueError, KeyError):
                continue
        return raw
    if annotation is datetime:
        return datetime.fromisoformat(str(raw))
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(raw)
    if annotation is MessageEvent:
        if isinstance(raw, dict) and set(raw) == {"$type", "value"}:
            return decode_message_event(raw["value"])
        return raw
    if annotation is MessageChain:
        if isinstance(raw, dict) and set(raw) == {"$type", "value"}:
            return decode_message_chain(raw["value"])
        return raw
    if annotation is UMO:
        if isinstance(raw, dict) and set(raw) == {"$type", "value"}:
            raw = raw["value"]
        if isinstance(raw, dict):
            return UMO(
                platform_id=str(raw["platform_id"]),
                message_type=MessageType(str(raw["message_type"])),
                session_id=str(raw["session_id"]),
            )
        return raw
    if isinstance(annotation, type) and annotation.__name__ in _PROTOCOL_DATACLASSES:
        if isinstance(raw, dict) and set(raw) == {"$type", "value"}:
            # Nested dataclasses arrive wrapped in their own envelope.
            raw = raw["value"]
        return _decode_dataclass(annotation, raw)
    return raw


def _decode_dataclass(cls: type, payload: Any) -> Any:
    """Decode one registered dataclass from its protocol object.

    Unknown payload keys are ignored so newer peers can add fields; missing
    fields fall back to their declared defaults.
    """
    if not isinstance(payload, dict):
        raise InvalidRequest(f"{cls.__name__} payload must be an object")
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for field in fields(cls):
        if field.name not in payload:
            continue
        kwargs[field.name] = _coerce_value(
            hints.get(field.name, Any),
            payload[field.name],
        )
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise InvalidRequest(f"invalid {cls.__name__} payload") from exc


def encode_value(value: Any, *, allow_unknown: bool = False) -> JSONValue:
    """Encode a supported SDK or JSON value.

    Args:
        value: Value passed through the protocol.
        allow_unknown: Whether inbound UnknownSegment instances inside message
            chains may be encoded. Enable only for pass-through state (hook
            snapshots and write ops); fresh handler results stay strict.

    Returns:
        JSON-compatible representation.

    Raises:
        InvalidRequest: The value is unsupported or has non-string mapping keys.
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, bytes | bytearray):
        import base64

        return {
            "$type": "bytes",
            "value": base64.b64encode(bytes(value)).decode("ascii"),
        }
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, MessageEvent):
        return {
            "$type": "MessageEvent",
            "value": encode_message_event(value),
        }
    if isinstance(value, UMO):
        return {
            "$type": "UMO",
            "value": {
                "platform_id": value.platform_id,
                "message_type": value.message_type.value,
                "session_id": value.session_id,
            },
        }
    if (
        is_dataclass(value)
        and not isinstance(value, type)
        and type(value).__name__ in _PROTOCOL_DATACLASSES
    ):
        return {
            "$type": type(value).__name__,
            "value": {
                field.name: encode_value(
                    getattr(value, field.name),
                    allow_unknown=allow_unknown,
                )
                for field in fields(value)
            },
        }
    if isinstance(value, MessageChain):
        return {
            "$type": "MessageChain",
            "value": encode_message_chain(value, allow_unknown=allow_unknown),
        }
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [encode_value(item, allow_unknown=allow_unknown) for item in value]
    if isinstance(value, Mapping):
        encoded: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise InvalidRequest("protocol mapping keys must be strings")
            encoded[key] = encode_value(item, allow_unknown=allow_unknown)
        return encoded
    raise InvalidRequest(f"unsupported protocol value: {type(value)!r}")


def decode_value(value: JSONValue) -> Any:
    """Decode a supported SDK or JSON value.

    Args:
        value: JSON-compatible protocol value.

    Returns:
        Decoded SDK object or JSON value.

    Raises:
        InvalidRequest: A reserved SDK envelope is malformed or unknown.
    """
    if isinstance(value, list):
        return [decode_value(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$type", "value"}:
            value_type = value["$type"]
            payload = value["value"]
            if value_type == "bytes":
                import base64

                if not isinstance(payload, str):
                    raise InvalidRequest("bytes payload must be base64 text")
                return base64.b64decode(payload.encode("ascii"))
            if value_type == "MessageEvent":
                if not isinstance(payload, dict):
                    raise InvalidRequest("MessageEvent payload must be an object")
                return decode_message_event(payload)
            if value_type == "MessageChain":
                if not isinstance(payload, list):
                    raise InvalidRequest("MessageChain payload must be a list")
                return decode_message_chain(payload)
            if value_type == "UMO":
                if not isinstance(payload, dict):
                    raise InvalidRequest("UMO payload must be an object")
                try:
                    return UMO(
                        platform_id=str(payload["platform_id"]),
                        message_type=MessageType(str(payload["message_type"])),
                        session_id=str(payload["session_id"]),
                    )
                except (KeyError, ValueError) as exc:
                    raise InvalidRequest("invalid UMO payload") from exc
            if value_type in _PROTOCOL_DATACLASSES:
                return _decode_dataclass(_PROTOCOL_DATACLASSES[value_type], payload)
            raise InvalidRequest(f"unknown SDK value type: {value_type!r}")
        return {key: decode_value(item) for key, item in value.items()}
    return value


def encode_message_event(event: MessageEvent) -> dict[str, JSONValue]:
    """Encode a message event.

    Args:
        event: Event to encode.

    Returns:
        JSON-compatible event object.
    """
    command: JSONValue = None
    if event.command is not None:
        command = {
            "path": event.command.path,
            "arguments": encode_value(event.command.arguments),
        }
    return {
        "id": event.id,
        "umo": {
            "platform_id": event.umo.platform_id,
            "message_type": event.umo.message_type.value,
            "session_id": event.umo.session_id,
        },
        "platform_type": event.platform_type,
        "message_ref": {"id": event.message_ref.id},
        "message": encode_message_chain(event.message, allow_unknown=True),
        "sender": {
            "id": event.sender.id,
            "name": event.sender.name,
            "role": event.sender.role.value,
        },
        "timestamp": event.timestamp.isoformat(),
        "command": command,
        "is_wake": event.is_wake,
        "extras": encode_value(dict(event.extras)),
    }


def decode_message_event(data: Mapping[str, Any]) -> MessageEvent:
    """Decode a message event.

    Args:
        data: Protocol event object.

    Returns:
        Immutable message event.

    Raises:
        InvalidRequest: The event object is incomplete or invalid.
    """
    try:
        umo = data["umo"]
        message_ref = data["message_ref"]
        sender = data["sender"]
        message = data["message"]
        if not all(
            isinstance(item, Mapping) for item in (umo, message_ref, sender)
        ) or not isinstance(message, list):
            raise TypeError

        command_data = data.get("command")
        command = None
        if command_data is not None:
            if not isinstance(command_data, Mapping):
                raise TypeError
            arguments = decode_value(command_data.get("arguments", {}))
            if not isinstance(arguments, Mapping):
                raise TypeError
            command = CommandInvocation(
                path=str(command_data["path"]),
                arguments=arguments,
            )

        return MessageEvent(
            id=str(data["id"]),
            umo=UMO(
                platform_id=str(umo["platform_id"]),
                message_type=MessageType(str(umo["message_type"])),
                session_id=str(umo["session_id"]),
            ),
            platform_type=str(data["platform_type"]),
            message_ref=MessageRef(id=str(message_ref["id"])),
            message=decode_message_chain(message),
            sender=Sender(
                id=str(sender["id"]),
                name=str(sender["name"]),
                role=SenderRole(str(sender.get("role", SenderRole.MEMBER.value))),
            ),
            timestamp=datetime.fromisoformat(str(data["timestamp"])),
            command=command,
            is_wake=bool(data.get("is_wake", False)),
            extras=dict(decode_value(data.get("extras", {}))),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidRequest("invalid MessageEvent payload") from exc


# ---------------------------------------------------------------------------
# Message segment codec registry
#
# Each segment type declares how to cross the protocol boundary. Adding a new
# segment is one registration; decoding an unregistered type downgrades to
# UnknownSegment instead of failing (forward compatibility).
# ---------------------------------------------------------------------------


def _encode_media(segment: MediaSegment) -> dict[str, JSONValue]:
    """Encode one media segment source as an asset reference or URL.

    Args:
        segment: Media segment to encode.

    Returns:
        Protocol object for the media segment.

    Raises:
        InvalidRequest: The source is a local file or bytes, which must be
            uploaded through the asset service before serialization.
    """
    if isinstance(segment.source, AssetRef):
        source: JSONValue = {
            "kind": "asset",
            "id": segment.source.id,
            "filename": segment.source.filename,
            "media_type": segment.source.media_type,
            "size": segment.source.size,
        }
    elif isinstance(segment.source, str) and segment.source.startswith(
        ("http://", "https://")
    ):
        source = {"kind": "url", "url": segment.source}
    elif isinstance(segment.source, Path | bytes):
        raise InvalidRequest(
            "local media must be uploaded before protocol serialization"
        )
    else:
        raise InvalidRequest("media source must be an AssetRef or public URL")
    media: dict[str, JSONValue] = {
        "type": segment.type,
        "source": source,
        "media_type": segment.media_type,
    }
    if isinstance(segment, File):
        media["filename"] = segment.filename
    return media


_MEDIA_CLASSES = {
    "Image": Image,
    "Record": Record,
    "Video": Video,
    "File": File,
}


def _decode_media(data: Mapping[str, Any]) -> MediaSegment:
    """Decode one media segment from its protocol object."""
    try:
        source_data = data["source"]
        if not isinstance(source_data, Mapping):
            raise TypeError
        if source_data.get("kind") == "asset":
            source: AssetRef | str = AssetRef(
                id=str(source_data["id"]),
                filename=(
                    str(source_data["filename"])
                    if source_data.get("filename") is not None
                    else None
                ),
                media_type=(
                    str(source_data["media_type"])
                    if source_data.get("media_type") is not None
                    else None
                ),
                size=(
                    int(source_data["size"])
                    if source_data.get("size") is not None
                    else None
                ),
            )
        elif source_data.get("kind") == "url":
            source = str(source_data["url"])
        else:
            raise ValueError
        media_type = (
            str(data["media_type"]) if data.get("media_type") is not None else None
        )
        segment_type = str(data["type"])
        media_class = _MEDIA_CLASSES[segment_type]
        if media_class is File:
            return File(
                source=source,
                media_type=media_type,
                filename=(
                    str(data["filename"]) if data.get("filename") is not None else None
                ),
            )
        return media_class(source=source, media_type=media_type)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidRequest("invalid media segment payload") from exc


def _encode_node_content(
    segments: Sequence[MessageSegment],
    allow_unknown: bool,
) -> list[JSONValue]:
    return [
        _encode_segment(segment, allow_unknown=allow_unknown) for segment in segments
    ]


def _encode_segment(
    segment: MessageSegment,
    *,
    allow_unknown: bool,
) -> JSONValue:
    """Encode one segment through the registry."""
    if isinstance(segment, Plain):
        return {"type": "Plain", "text": segment.text}
    if isinstance(segment, At):
        return {"type": "At", "user_id": segment.user_id, "name": segment.name}
    if isinstance(segment, AtAll):
        return {"type": "AtAll"}
    if isinstance(segment, Reply):
        return {
            "type": "Reply",
            "id": segment.id,
            "sender_id": segment.sender_id,
            "sender_name": segment.sender_name,
            "text": segment.text,
        }
    if isinstance(segment, Face):
        return {"type": "Face", "id": segment.id}
    if isinstance(segment, Forward):
        return {"type": "Forward", "id": segment.id}
    if isinstance(segment, Poke):
        return {
            "type": "Poke",
            "poke_type": segment.poke_type,
            "user_id": segment.user_id,
        }
    if isinstance(segment, Json):
        payload = (
            dict(segment.data) if isinstance(segment.data, Mapping) else segment.data
        )
        return {"type": "Json", "data": encode_value(payload)}
    if isinstance(segment, Share):
        return {
            "type": "Share",
            "url": segment.url,
            "title": segment.title,
            "content": segment.content,
            "image": segment.image,
        }
    if isinstance(segment, Location):
        return {
            "type": "Location",
            "lat": segment.lat,
            "lon": segment.lon,
            "title": segment.title,
            "content": segment.content,
        }
    if isinstance(segment, Music):
        return {
            "type": "Music",
            "music_type": segment.music_type,
            "id": segment.id,
            "url": segment.url,
            "audio": segment.audio,
            "title": segment.title,
            "content": segment.content,
            "image": segment.image,
        }
    if isinstance(segment, Button):
        return {
            "type": "Button",
            "label": segment.label,
            "action_id": segment.action_id,
            "url": segment.url,
            "data": encode_value(segment.data),
            "style": segment.style,
            "emoji": segment.emoji,
            "disabled": segment.disabled,
        }
    if isinstance(segment, ActionRow):
        return {
            "type": "ActionRow",
            "buttons": [
                _encode_segment(btn, allow_unknown=allow_unknown)
                for btn in segment.buttons
            ],
        }
    if isinstance(segment, ButtonInteraction):
        return {
            "type": "ButtonInteraction",
            "action_id": segment.action_id,
            "interaction_id": segment.interaction_id,
            "data": encode_value(segment.data),
            "source_message_id": segment.source_message_id,
            "callback_data": segment.callback_data,
        }
    if isinstance(segment, UIInteraction):
        return {
            "type": "UIInteraction",
            "action_id": segment.action_id,
            "interaction_id": segment.interaction_id,
            "data": encode_value(segment.data),
            "source": segment.source,
            "source_message_id": segment.source_message_id,
            "view": {
                "id": segment.view.id,
                "name": segment.view.name,
                "version": segment.view.version,
                "revision": segment.view.revision,
                "data": encode_value(dict(segment.view.data)),
            },
        }
    if isinstance(segment, MediaSegment):
        return _encode_media(segment)
    if isinstance(segment, Node):
        return {
            "type": "Node",
            "sender_id": segment.sender_id,
            "sender_name": segment.sender_name,
            "content": _encode_node_content(segment.content, allow_unknown),
        }
    if isinstance(segment, Nodes):
        return {
            "type": "Nodes",
            "nodes": _encode_node_content(segment.nodes, allow_unknown),
        }
    if isinstance(segment, UnknownSegment) and allow_unknown:
        return {
            "type": "Unknown",
            "segment_type": segment.segment_type,
            "data": encode_value(segment.data),
        }
    raise InvalidRequest(f"unsupported outbound message segment: {type(segment)!r}")


def _decode_segment(data: Mapping[str, Any]) -> MessageSegment:
    """Decode one segment, downgrading unknown types to UnknownSegment."""
    try:
        segment_type = data.get("type")
        if segment_type == "Plain":
            return Plain(str(data["text"]))
        if segment_type == "At":
            name = data.get("name")
            return At(
                user_id=str(data["user_id"]),
                name=str(name) if name is not None else None,
            )
        if segment_type == "AtAll":
            return AtAll()
        if segment_type == "Reply":
            return Reply(
                id=str(data["id"]),
                sender_id=(
                    str(data["sender_id"])
                    if data.get("sender_id") is not None
                    else None
                ),
                sender_name=(
                    str(data["sender_name"])
                    if data.get("sender_name") is not None
                    else None
                ),
                text=(str(data["text"]) if data.get("text") is not None else None),
            )
        if segment_type == "Face":
            return Face(id=int(data["id"]))
        if segment_type == "Forward":
            return Forward(id=str(data["id"]))
        if segment_type == "Poke":
            user_id = data.get("user_id")
            return Poke(
                poke_type=str(data.get("poke_type", "126")),
                user_id=str(user_id) if user_id is not None else None,
            )
        if segment_type == "Json":
            return Json(data=decode_value(data.get("data")))
        if segment_type == "Share":
            return Share(
                url=str(data.get("url", "")),
                title=str(data.get("title", "")),
                content=str(data.get("content", "")),
                image=str(data.get("image", "")),
            )
        if segment_type == "Location":
            return Location(
                lat=float(data.get("lat", 0.0)),
                lon=float(data.get("lon", 0.0)),
                title=str(data.get("title", "")),
                content=str(data.get("content", "")),
            )
        if segment_type == "Music":
            return Music(
                music_type=str(data.get("music_type", "custom")),
                id=int(data.get("id", 0)),
                url=str(data.get("url", "")),
                audio=str(data.get("audio", "")),
                title=str(data.get("title", "")),
                content=str(data.get("content", "")),
                image=str(data.get("image", "")),
            )
        if segment_type == "Button":
            return Button(
                label=str(data["label"]),
                action_id=(
                    str(data["action_id"])
                    if data.get("action_id") is not None
                    else None
                ),
                url=str(data["url"]) if data.get("url") is not None else None,
                data=decode_value(data.get("data")),
                style=str(data.get("style", "secondary")),  # type: ignore[arg-type]
                emoji=str(data["emoji"]) if data.get("emoji") is not None else None,
                disabled=bool(data.get("disabled", False)),
            )
        if segment_type == "ActionRow":
            raw_buttons = data["buttons"]
            if not isinstance(raw_buttons, list):
                raise TypeError
            decoded_buttons = [_decode_segment(item) for item in raw_buttons]
            if not all(isinstance(btn, Button) for btn in decoded_buttons):
                raise TypeError
            return ActionRow(buttons=decoded_buttons)  # type: ignore[arg-type]
        if segment_type == "ButtonInteraction":
            return ButtonInteraction(
                action_id=str(data["action_id"]),
                interaction_id=str(data["interaction_id"]),
                data=decode_value(data.get("data")),
                source_message_id=(
                    str(data["source_message_id"])
                    if data.get("source_message_id") is not None
                    else None
                ),
                callback_data=(
                    str(data["callback_data"])
                    if data.get("callback_data") is not None
                    else None
                ),
            )
        if segment_type == "UIInteraction":
            view_raw = data["view"]
            if not isinstance(view_raw, Mapping):
                raise TypeError
            view_data = decode_value(view_raw.get("data", {}))
            if not isinstance(view_data, Mapping):
                raise TypeError
            return UIInteraction(
                action_id=str(data["action_id"]),
                interaction_id=str(data["interaction_id"]),
                data=decode_value(data.get("data")),
                source=str(data.get("source", "view")),
                source_message_id=(
                    str(data["source_message_id"])
                    if data.get("source_message_id") is not None
                    else None
                ),
                view=ViewContext(
                    id=str(view_raw["id"]),
                    name=str(view_raw["name"]),
                    version=int(view_raw.get("version", 1)),
                    revision=int(view_raw.get("revision", 0)),
                    data=view_data,
                ),
            )
        if segment_type in _MEDIA_CLASSES:
            return _decode_media(data)
        if segment_type == "Node":
            content = data["content"]
            if not isinstance(content, list):
                raise TypeError
            return Node(
                sender_id=str(data["sender_id"]),
                sender_name=(
                    str(data["sender_name"])
                    if data.get("sender_name") is not None
                    else None
                ),
                content=[_decode_segment(item) for item in content],
            )
        if segment_type == "Nodes":
            nodes_data = data["nodes"]
            if not isinstance(nodes_data, list):
                raise TypeError
            nodes = [_decode_segment(item) for item in nodes_data]
            if not all(isinstance(node, Node) for node in nodes):
                raise TypeError
            return Nodes(nodes=nodes)
        if segment_type == "Unknown":
            decoded_data = decode_value(data.get("data", {}))
            if not isinstance(decoded_data, Mapping):
                raise TypeError
            return UnknownSegment(
                segment_type=str(data["segment_type"]),
                data=decoded_data,
            )
        # Forward compatibility: unregistered segment types degrade to
        # UnknownSegment carrying every JSON-safe field.
        extra = {
            key: decode_value(value) for key, value in data.items() if key != "type"
        }
        return UnknownSegment(
            segment_type=str(segment_type),
            data=extra,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidRequest("invalid message segment payload") from exc


def encode_message_chain(
    chain: MessageChain,
    *,
    allow_unknown: bool = False,
) -> list[JSONValue]:
    """Encode a message chain.

    Args:
        chain: Message chain to encode.
        allow_unknown: Whether inbound unknown segments may be encoded.

    Returns:
        Ordered list of encoded message segments.

    Raises:
        InvalidRequest: A segment cannot cross the protocol boundary.
    """
    return [_encode_segment(segment, allow_unknown=allow_unknown) for segment in chain]


def decode_message_chain(data: list[Any]) -> MessageChain:
    """Decode a message chain.

    Args:
        data: Ordered list of segment objects.

    Returns:
        Immutable message chain. Unregistered segment types are downgraded to
        UnknownSegment.

    Raises:
        InvalidRequest: A segment object is malformed.
    """
    segments: list[MessageSegment] = []
    for item in data:
        if not isinstance(item, Mapping):
            raise InvalidRequest("invalid message segment payload")
        segments.append(_decode_segment(item))
    return MessageChain(*segments)


def encode_result(result: EventResult | None) -> JSONValue:
    """Encode one handler result.

    Args:
        result: Handler result or pipeline continuation marker.

    Returns:
        JSON-compatible result object.
    """
    if result is None:
        return None
    data: dict[str, JSONValue] = {
        "type": "event",
        "propagation": result.propagation.value,
    }
    if isinstance(result, GroupUsage):
        data["type"] = "group_usage"
    elif isinstance(result, MessageResult):
        data.update(
            {
                "type": "message",
                "message": encode_message_chain(result.message),
                "quote": result.quote,
            }
        )
    elif isinstance(result, ViewResult):
        data.update(
            {
                "type": "view",
                "name": result.name,
                "data": encode_value(dict(result.data)),
                "text": result.text,
                "title": result.title,
            }
        )
    return data


def decode_result(data: Any) -> EventResult | None:
    """Decode one handler result.

    Args:
        data: JSON-compatible result object.

    Returns:
        Handler result or pipeline continuation marker.

    Raises:
        InvalidRequest: The result object is malformed.
    """
    if data is None:
        return None
    if not isinstance(data, Mapping):
        raise InvalidRequest("handler result must be an object or null")
    try:
        propagation = Propagation(str(data["propagation"]))
        if data.get("type") == "event":
            return EventResult(propagation=propagation)
        if data.get("type") == "group_usage":
            return GroupUsage(propagation=propagation)
        if data.get("type") == "message":
            message = data["message"]
            if not isinstance(message, list):
                raise TypeError
            return MessageResult(
                propagation=propagation,
                message=decode_message_chain(message),
                quote=bool(data.get("quote", False)),
            )
        if data.get("type") == "view":
            raw_view_data = decode_value(data.get("data", {}))
            if not isinstance(raw_view_data, Mapping):
                raise TypeError
            raw_name = data.get("name")
            return ViewResult(
                propagation=propagation,
                name=str(raw_name) if raw_name is not None else None,
                data=dict(raw_view_data),
                text=str(data.get("text", "")),
                title=str(data.get("title", "")),
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidRequest("invalid handler result payload") from exc
    raise InvalidRequest(f"unknown handler result type: {data.get('type')!r}")
