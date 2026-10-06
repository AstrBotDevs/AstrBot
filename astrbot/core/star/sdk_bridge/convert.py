from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from astrbot_sdk.assets import AssetRef
from astrbot_sdk.events import (
    UMO,
    CommandInvocation,
    MessageEvent,
    MessageRef,
    MessageType,
    Sender,
    SenderRole,
)
from astrbot_sdk.message_components import (
    At,
    AtAll,
    Face,
    File,
    Forward,
    Image,
    Node,
    Nodes,
    Plain,
    Record,
    Reply,
    UnknownSegment,
    Video,
)
from astrbot_sdk.messages import MessageChain
from astrbot_sdk.results import EventResult, MessageResult, Propagation

from astrbot.core.message import components as core_comp
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType as CoreMessageType

_SDK_TO_CORE_MESSAGE_TYPE = {
    MessageType.PRIVATE: CoreMessageType.FRIEND_MESSAGE,
    MessageType.GROUP: CoreMessageType.GROUP_MESSAGE,
    MessageType.OTHER: CoreMessageType.OTHER_MESSAGE,
}
_CORE_TO_SDK_MESSAGE_TYPE = {
    value: key for key, value in _SDK_TO_CORE_MESSAGE_TYPE.items()
}


def to_core_message_type(message_type: MessageType) -> CoreMessageType:
    """Map an SDK message type onto the core enum."""
    return _SDK_TO_CORE_MESSAGE_TYPE[message_type]


def to_umo_string(umo: UMO) -> str:
    """Serialize an SDK UMO into the core unified_msg_origin string."""
    return f"{umo.platform_id}:{to_core_message_type(umo.message_type).value}:{umo.session_id}"


def _json_safe(value: Any) -> Any:
    """Keep only values that can cross the protocol boundary."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, (list | tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def _http_source(*candidates: Any) -> str | None:
    """Return the first public URL among candidate media references."""
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
            return candidate
    return None


def to_sdk_chain(components: list) -> MessageChain:
    """Convert core inbound components into an SDK message chain."""
    segments = []
    for component in components:
        if isinstance(component, core_comp.AtAll):
            segments.append(AtAll())
        elif isinstance(component, core_comp.At):
            segments.append(
                At(user_id=str(component.qq), name=component.name or None),
            )
        elif isinstance(component, core_comp.Plain):
            segments.append(Plain(component.text))
        elif isinstance(component, core_comp.Face):
            segments.append(Face(id=int(component.id)))
        elif isinstance(component, core_comp.Forward):
            segments.append(Forward(id=str(component.id)))
        elif isinstance(component, core_comp.Reply):
            segments.append(
                Reply(
                    id=str(component.id),
                    sender_id=str(component.sender_id),
                    sender_name=component.sender_nickname or None,
                    text=component.message_str or None,
                ),
            )
        elif isinstance(component, core_comp.Nodes):
            nodes = [
                Node(
                    sender_id=str(getattr(node, "uin", "") or ""),
                    sender_name=getattr(node, "name", "") or None,
                    content=to_sdk_chain(getattr(node, "content", []) or []),
                )
                for node in component.nodes
            ]
            segments.append(Nodes(nodes=nodes))
        elif isinstance(component, core_comp.Node):
            segments.append(
                Node(
                    sender_id=str(component.uin or ""),
                    sender_name=component.name or None,
                    content=to_sdk_chain(component.content or []),
                ),
            )
        elif isinstance(
            component,
            core_comp.Image | core_comp.Record | core_comp.Video | core_comp.File,
        ):
            url = _http_source(
                getattr(component, "url", None),
                getattr(component, "file", None),
            )
            if url is None:
                # Local media requires the asset service, which is not part of
                # this slice; keep the segment visible but inert.
                segments.append(
                    UnknownSegment(
                        segment_type=component.type.name,
                        data={"reason": "local media is not supported yet"},
                    ),
                )
                continue
            if isinstance(component, core_comp.Image):
                segments.append(Image(source=url))
            elif isinstance(component, core_comp.Record):
                segments.append(Record(source=url))
            elif isinstance(component, core_comp.Video):
                segments.append(Video(source=url))
            else:
                segments.append(
                    File(
                        source=url,
                        filename=component.name or None,
                    ),
                )
        else:
            data = {
                key: _json_safe(value)
                for key, value in vars(component).items()
                if not key.startswith("_")
            }
            segments.append(
                UnknownSegment(
                    segment_type=getattr(
                        component.type,
                        "name",
                        str(type(component).__name__),
                    ),
                    data=data,
                ),
            )
    return MessageChain(*segments)


def to_sdk_event(
    event: AstrMessageEvent,
    *,
    command_path: str | None = None,
    arguments: dict[str, Any] | None = None,
) -> MessageEvent:
    """Convert a core message event into the immutable SDK event DTO."""
    platform_id, message_type_value, session_id = event.unified_msg_origin.split(
        ":",
        2,
    )
    try:
        sdk_message_type = _CORE_TO_SDK_MESSAGE_TYPE[
            CoreMessageType(message_type_value)
        ]
    except ValueError:
        sdk_message_type = MessageType.OTHER

    command = None
    if command_path is not None:
        command = CommandInvocation(
            path=command_path,
            arguments=arguments or {},
        )

    # AstrMessageEvent has no message_id attribute of its own; the platform
    # message id lives on the wrapped AstrBotMessage.
    message_id = str(getattr(event.message_obj, "message_id", "") or uuid4().hex)
    created_at = getattr(event, "created_at", None)
    timestamp = (
        datetime.fromtimestamp(created_at, UTC)
        if isinstance(created_at, int | float)
        else datetime.now(UTC)
    )

    return MessageEvent(
        id=message_id,
        umo=UMO(platform_id, sdk_message_type, session_id),
        platform_type=event.get_platform_name(),
        message_ref=MessageRef(message_id),
        message=to_sdk_chain(event.get_messages()),
        sender=Sender(
            id=event.get_sender_id(),
            name=event.get_sender_name(),
            role=(SenderRole.ADMIN if event.role == "admin" else SenderRole.MEMBER),
        ),
        timestamp=timestamp,
        command=command,
        is_wake=event.is_wake,
        # waking_check fills plugins_name before handlers run; legacy plugins
        # read it off the event, so carry it through the wire extras.
        extras={"plugins_name": getattr(event, "plugins_name", None)},
    )


def to_core_chain(
    chain: MessageChain,
    *,
    resolve_asset: Any = None,
) -> list:
    """Convert an SDK outbound chain into core components.

    Args:
        chain: SDK chain to convert.
        resolve_asset: Optional resolver mapping AssetRef to a local file.

    Raises:
        ValueError: The chain contains segments the Host cannot send yet.
    """
    components = []
    for segment in chain:
        if isinstance(segment, Plain):
            components.append(core_comp.Plain(segment.text))
        elif isinstance(segment, AtAll):
            components.append(core_comp.AtAll())
        elif isinstance(segment, At):
            components.append(core_comp.At(qq=segment.user_id, name=segment.name or ""))
        elif isinstance(segment, Face):
            components.append(core_comp.Face(id=segment.id))
        elif isinstance(segment, Forward):
            components.append(core_comp.Forward(id=segment.id))
        elif isinstance(segment, Reply):
            components.append(
                core_comp.Reply(
                    id=segment.id,
                    sender_id=segment.sender_id or 0,
                    sender_nickname=segment.sender_name or "",
                    message_str=segment.text or "",
                ),
            )
        elif isinstance(segment, Image | Record | Video | File):
            source = segment.source
            if isinstance(source, AssetRef):
                if resolve_asset is None:
                    raise ValueError(
                        f"{segment.type} references an asset without a resolver",
                    )
                path = str(resolve_asset(source))
                if isinstance(segment, Image):
                    components.append(core_comp.Image.fromFileSystem(path))
                elif isinstance(segment, Record):
                    components.append(core_comp.Record.fromFileSystem(path))
                elif isinstance(segment, Video):
                    components.append(core_comp.Video.fromFileSystem(path))
                else:
                    components.append(
                        core_comp.File(name=segment.filename or "file", file=path),
                    )
            elif isinstance(source, str):
                if isinstance(segment, Image):
                    components.append(core_comp.Image.fromURL(source))
                elif isinstance(segment, Record):
                    components.append(core_comp.Record.fromURL(source))
                elif isinstance(segment, Video):
                    components.append(core_comp.Video.fromURL(source))
                else:
                    components.append(
                        core_comp.File(name=segment.filename or "file", url=source),
                    )
            else:
                raise ValueError(f"unsupported {segment.type} source: {source!r}")
        elif isinstance(segment, Nodes):
            components.append(
                core_comp.Nodes(
                    nodes=[
                        core_comp.Node(
                            content=to_core_chain(
                                MessageChain(*node.content),
                                resolve_asset=resolve_asset,
                            ),
                            name=node.sender_name or "",
                            uin=node.sender_id,
                        )
                        for node in segment.nodes
                    ],
                ),
            )
        elif isinstance(segment, Node):
            components.append(
                core_comp.Node(
                    content=to_core_chain(
                        MessageChain(*segment.content),
                        resolve_asset=resolve_asset,
                    ),
                    name=segment.sender_name or "",
                    uin=segment.sender_id,
                ),
            )
        elif isinstance(segment, UnknownSegment):
            # The legacy compat layer carries components without a new SDK
            # counterpart as typed unknown segments; rebuild the core form.
            if segment.segment_type == "Poke":
                components.append(
                    core_comp.Poke(
                        poke_type=segment.data.get("poke_type", "126"),
                        id=segment.data.get("user_id") or 0,
                    ),
                )
            elif segment.segment_type == "Json":
                components.append(core_comp.Json(data=segment.data.get("data")))
            elif segment.segment_type == "Share":
                components.append(
                    core_comp.Share(
                        url=str(segment.data.get("url", "")),
                        title=str(segment.data.get("title", "")),
                        content=str(segment.data.get("content", "")),
                        image=str(segment.data.get("image", "")),
                    ),
                )
            else:
                raise ValueError(
                    f"unsupported outbound segment type: {segment.segment_type!r}",
                )
        else:
            raise ValueError(f"unsupported outbound segment: {type(segment)!r}")
    return components


def _resolve_part_source(source: Any, resolve_asset: Any) -> str:
    """Resolve one content part source into a usable URL or file path."""
    if isinstance(source, AssetRef):
        if resolve_asset is None:
            raise ValueError("content part references an asset without a resolver")
        return str(resolve_asset(source))
    return str(source)


def to_core_content(content: Any, *, resolve_asset: Any = None) -> Any:
    """Convert SDK message content into the core format (str or part dicts)."""
    if content is None or isinstance(content, str):
        return content
    from astrbot_sdk.conversations import AudioPart, ImagePart, TextPart

    parts = []
    for part in content:
        if isinstance(part, TextPart):
            parts.append({"type": "text", "text": part.text})
        elif isinstance(part, ImagePart):
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _resolve_part_source(part.source, resolve_asset),
                    },
                },
            )
        elif isinstance(part, AudioPart):
            parts.append(
                {
                    "type": "audio_url",
                    "audio_url": {
                        "url": _resolve_part_source(part.source, resolve_asset),
                    },
                },
            )
        else:
            raise ValueError(f"unsupported content part: {type(part)!r}")
    return parts


def to_core_context_message(message: Any, *, resolve_asset: Any = None) -> dict:
    """Convert an SDK conversation Message into a core context dict."""
    item: dict[str, Any] = {
        "role": message.role,
        "content": to_core_content(message.content, resolve_asset=resolve_asset),
    }
    if message.tool_calls is not None:
        item["tool_calls"] = [dict(call) for call in message.tool_calls]
    if message.tool_call_id is not None:
        item["tool_call_id"] = message.tool_call_id
    return item


def apply_sdk_result(
    event: AstrMessageEvent,
    result: EventResult,
    *,
    resolve_asset: Any = None,
) -> None:
    """Apply one SDK handler result onto the core event.

    Args:
        event: Core event being processed.
        result: SDK result produced by the remote handler.
        resolve_asset: Optional resolver mapping AssetRef to a local file.
    """
    if isinstance(result, MessageResult):
        event.set_result(
            MessageEventResult(
                chain=to_core_chain(result.message, resolve_asset=resolve_asset),
            ),
        )
    if result.propagation is Propagation.STOP:
        event.stop_event()
