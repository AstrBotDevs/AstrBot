from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from astrbot.core.message.components import (
    RPS,
    At,
    AtAll,
    BaseMessageComponent,
    Contact,
    Dice,
    Face,
    File,
    FlashTransfer,
    Forward,
    Image,
    Json,
    Location,
    Markdown,
    MFace,
    MiniApp,
    Music,
    Node,
    Nodes,
    OnlineFile,
    Plain,
    Poke,
    Record,
    Reply,
    Shake,
    Share,
    Unknown,
    Video,
    Xml,
)
from astrbot.core.message.json_card import format_json_card_prompt
from astrbot.core.message.qq_face import format_qq_face
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .quoted_message.chain_parser import OneBotPayloadParser
from .quoted_message.image_resolver import ImageResolver
from .quoted_message.onebot_client import OneBotClient
from .quoted_message.settings import SETTINGS, QuotedMessageParserSettings
from .string_utils import normalize_and_dedupe_strings

_MAX_RENDERED_VALUE_LENGTH = 4000


def _limited_text(value: object) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    if len(text) <= _MAX_RENDERED_VALUE_LENGTH:
        return text
    return f"{text[:_MAX_RENDERED_VALUE_LENGTH]}…[truncated]"


def _is_usable_media_ref(value: str) -> bool:
    return bool(
        value
        and (
            value.startswith(("http://", "https://", "file://", "base64://"))
            or "/" in value
            or "\\" in value
        )
    )


def _render_simple_component(
    component: BaseMessageComponent,
    *,
    include_plain: bool,
) -> str:
    if isinstance(component, Plain):
        return component.text if include_plain else ""
    if isinstance(component, At):
        return f"@{component.name or component.qq}" if include_plain else ""
    if isinstance(component, AtAll):
        return "@all" if include_plain else ""
    if isinstance(component, Reply):
        return component.message_str or "[Quoted Message]" if include_plain else ""
    return _render_metadata_component(component)


def _render_metadata_component(component: BaseMessageComponent) -> str:
    if isinstance(component, Json):
        return format_json_card_prompt(component)
    for component_type, prefix, attribute in (
        (Xml, "[XML]\n", "data"),
        (Markdown, "[Markdown]\n", "content"),
        (MiniApp, "[MiniApp]\n", "data"),
    ):
        if isinstance(component, component_type):
            return f"{prefix}{_limited_text(getattr(component, attribute))}"
    for component_type, label in (
        (Dice, "[Dice]"),
        (RPS, "[Rock Paper Scissors]"),
        (Shake, "[Window Shake]"),
    ):
        if isinstance(component, component_type):
            return label
    if isinstance(component, Music):
        return f"[Music: {component.title or component.sub_type or component.id}]"
    if isinstance(component, Contact):
        return f"[Contact: {component.sub_type} {component.id}]"
    if isinstance(component, Location):
        return (
            f"[Location: {component.title or ''} "
            f"({component.lat}, {component.lon}) {component.content or ''}]"
        )
    if isinstance(component, Share):
        return f"[Share: {component.title} {component.url}]"
    if isinstance(component, MFace):
        return component.summary or "[Market Face]"
    if isinstance(component, Face):
        return format_qq_face(component.id)
    if isinstance(component, Poke):
        return f"[Poke: {component.id}]"
    if isinstance(component, OnlineFile):
        return f"[Online File: {component.file_name}]"
    if isinstance(component, FlashTransfer):
        return f"[Flash Transfer: {component.file_set_id}]"
    if isinstance(component, Unknown):
        return component.text or f"[Unsupported: {component.segment_type}]"
    return ""


@dataclass(slots=True)
class MessageContextContent:
    text: str | None = None
    image_refs: list[str] = field(default_factory=list)
    nested_media: list[BaseMessageComponent] = field(default_factory=list)

    def extend(self, other: MessageContextContent) -> None:
        if other.text:
            self.text = "\n".join(part for part in (self.text, other.text) if part)
        self.image_refs.extend(other.image_refs)
        self.nested_media.extend(other.nested_media)


class MessageContextRenderer:
    """Render non-plain message components for an agent request."""

    def __init__(
        self,
        event: AstrMessageEvent,
        settings: QuotedMessageParserSettings = SETTINGS,
    ) -> None:
        self._event = event
        self._settings = settings
        self._client = OneBotClient(event, settings=settings)
        self._payload_parser = OneBotPayloadParser(settings=settings)
        self._image_resolver = ImageResolver(event, self._client)
        cache = getattr(event, "_forward_message_payload_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            setattr(event, "_forward_message_payload_cache", cache)
        self._forward_payload_cache: dict[str, dict[str, object] | None] = cache
        message_cache = getattr(event, "_message_component_payload_cache", None)
        if not isinstance(message_cache, dict):
            message_cache = {}
            setattr(event, "_message_component_payload_cache", message_cache)
        self._message_payload_cache: dict[str, dict[str, object] | None] = message_cache
        self._active_forward_ids: set[str] = set()
        self._forward_fetch_count = 0

    async def render_event_components(self) -> MessageContextContent:
        content = await self._render_components(
            self._event.message_obj.message,
            include_plain=False,
            depth=0,
        )
        content.image_refs = await self._image_resolver.resolve_for_llm(
            normalize_and_dedupe_strings(content.image_refs)
        )
        return content

    async def _render_forward(
        self,
        component: Forward,
        *,
        depth: int,
    ) -> MessageContextContent:
        if depth > self._settings.max_forward_node_depth:
            return MessageContextContent(text="[Forward depth limit reached]")

        if component.content:
            return await self._render_components(
                component.content,
                include_plain=True,
                depth=depth + 1,
            )

        forward_id = str(component.id).strip()
        if not forward_id:
            return MessageContextContent(text="[Empty Forward Message]")
        if forward_id in self._active_forward_ids:
            return MessageContextContent(text="[Cyclic Forward Message]")

        payload = self._forward_payload_cache.get(forward_id)
        if forward_id not in self._forward_payload_cache:
            if self._forward_fetch_count >= self._settings.max_forward_fetch:
                return MessageContextContent(text="[Forward fetch limit reached]")
            self._forward_fetch_count += 1
            payload = await self._client.get_forward_msg(forward_id)
            self._forward_payload_cache[forward_id] = payload
        if not payload:
            return MessageContextContent(text="[Unavailable Forward Message]")

        self._active_forward_ids.add(forward_id)
        try:
            parsed = self._payload_parser.parse_get_forward_payload(payload)
            content = MessageContextContent(
                text=parsed["text"],
                image_refs=list(parsed["image_refs"]),
                nested_media=self._collect_forward_media(payload),
            )
            for nested_id in parsed["forward_ids"]:
                nested = await self._render_forward(
                    Forward(id=nested_id),
                    depth=depth + 1,
                )
                content.extend(nested)
            return content
        finally:
            self._active_forward_ids.discard(forward_id)

    async def _render_existing_node(
        self,
        component: Node,
        *,
        depth: int,
    ) -> MessageContextContent:
        node_id = str(component.id or "").strip()
        if not node_id or node_id == "0":
            return MessageContextContent()
        payload = self._message_payload_cache.get(node_id)
        if node_id not in self._message_payload_cache:
            if self._forward_fetch_count >= self._settings.max_forward_fetch:
                return MessageContextContent(text="[Message fetch limit reached]")
            self._forward_fetch_count += 1
            payload = await self._client.get_msg(node_id)
            self._message_payload_cache[node_id] = payload
        if not payload:
            return MessageContextContent()

        parsed = self._payload_parser.parse_get_msg_payload(payload)
        payload_data = payload.get("data")
        message_data = payload_data if isinstance(payload_data, Mapping) else payload
        raw_segments = message_data.get("message") or message_data.get("messages") or []
        nested_media = (
            self._collect_forward_media(
                {"messages": [{"message": raw_segments}]},
                depth=depth,
            )
            if isinstance(raw_segments, list)
            else []
        )
        content = MessageContextContent(
            text=parsed["text"],
            image_refs=list(parsed["image_refs"]),
            nested_media=nested_media,
        )
        for nested_id in parsed["forward_ids"]:
            content.extend(
                await self._render_forward(
                    Forward(id=nested_id),
                    depth=depth + 1,
                )
            )
        return content

    def _collect_forward_media(
        self,
        payload: Mapping[str, object],
        *,
        depth: int = 0,
    ) -> list[BaseMessageComponent]:
        if depth > self._settings.max_forward_node_depth:
            return []

        data = payload.get("data")
        payload_data = data if isinstance(data, Mapping) else payload
        raw_nodes = (
            payload_data.get("messages")
            or payload_data.get("message")
            or payload_data.get("nodes")
            or []
        )
        if not isinstance(raw_nodes, list):
            return []

        media: list[BaseMessageComponent] = []
        for raw_node in raw_nodes:
            if not isinstance(raw_node, Mapping):
                continue
            if raw_node.get("type") == "node":
                node_data = raw_node.get("data")
                if not isinstance(node_data, Mapping):
                    continue
                raw_chain = node_data.get("content") or node_data.get("message") or []
            else:
                raw_chain = raw_node.get("message") or raw_node.get("content") or []
            if not isinstance(raw_chain, list):
                continue

            for raw_segment in raw_chain:
                if not isinstance(raw_segment, Mapping):
                    continue
                segment_type = raw_segment.get("type")
                raw_data = raw_segment.get("data")
                segment_data = raw_data if isinstance(raw_data, Mapping) else {}
                file_ref = segment_data.get("file")
                url_ref = segment_data.get("url")
                path_ref = segment_data.get("path")
                file_text = str(file_ref) if file_ref is not None else ""
                url_text = str(url_ref) if url_ref is not None else ""
                path_text = str(path_ref) if path_ref is not None else ""

                if segment_type in {"record", "voice"} and (
                    url_text or path_text or _is_usable_media_ref(file_text)
                ):
                    media.append(
                        Record(
                            file=file_text or url_text or path_text,
                            url=url_text,
                            path=path_text or None,
                        )
                    )
                elif segment_type == "video" and (file_text or url_text):
                    media.append(Video(file=file_text or url_text, url=url_text))
                elif segment_type == "file" and (url_text or path_text):
                    name = (
                        segment_data.get("name")
                        or segment_data.get("file_name")
                        or file_text
                        or "file"
                    )
                    media.append(
                        File(
                            name=str(name),
                            file=path_text or file_text or url_text,
                            url=url_text,
                        )
                    )
                elif segment_type in {"forward", "forward_msg", "nodes"}:
                    nested_content = segment_data.get("content")
                    if isinstance(nested_content, list) and nested_content:
                        media.extend(
                            self._collect_forward_media(
                                {"messages": nested_content},
                                depth=depth + 1,
                            )
                        )
                elif segment_type == "node":
                    media.extend(
                        self._collect_forward_media(
                            {"messages": [raw_segment]},
                            depth=depth + 1,
                        )
                    )
        return media

    async def _render_components(
        self,
        components: list[BaseMessageComponent],
        *,
        include_plain: bool,
        depth: int,
    ) -> MessageContextContent:
        if depth > self._settings.max_component_chain_depth:
            return MessageContextContent(text="[Message component depth limit reached]")

        result = MessageContextContent()
        for component in components:
            result.extend(
                await self._render_component(
                    component,
                    include_plain=include_plain,
                    depth=depth,
                )
            )
        return result

    async def _render_component(
        self,
        component: BaseMessageComponent,
        *,
        include_plain: bool,
        depth: int,
    ) -> MessageContextContent:
        nested_media = self._render_nested_media(component, depth=depth)
        if nested_media is not None:
            return nested_media
        if isinstance(component, Forward):
            return await self._render_forward_component(component, depth=depth)
        if isinstance(component, Node):
            return await self._render_node_component(component, depth=depth)
        if isinstance(component, Nodes):
            return await self._render_nodes_component(component, depth=depth)
        return MessageContextContent(
            text=_render_simple_component(component, include_plain=include_plain)
        )

    @staticmethod
    def _render_nested_media(
        component: BaseMessageComponent,
        *,
        depth: int,
    ) -> MessageContextContent | None:
        if depth == 0:
            return None
        for component_type, label in (
            (Image, "[Image]"),
            (Record, "[Audio]"),
            (Video, "[Video]"),
        ):
            if isinstance(component, component_type):
                return MessageContextContent(text=label, nested_media=[component])
        if isinstance(component, File):
            return MessageContextContent(
                text=f"[File: {component.name or 'file'}]",
                nested_media=[component],
            )
        return None

    async def _render_forward_component(
        self,
        component: Forward,
        *,
        depth: int,
    ) -> MessageContextContent:
        nested = await self._render_forward(component, depth=depth)
        text = (
            f"<Forwarded Message>\n{nested.text}\n</Forwarded Message>"
            if nested.text
            else None
        )
        return MessageContextContent(
            text=text,
            image_refs=nested.image_refs,
            nested_media=nested.nested_media,
        )

    async def _render_node_component(
        self,
        component: Node,
        *,
        depth: int,
    ) -> MessageContextContent:
        if component.content:
            nested = await self._render_components(
                component.content,
                include_plain=True,
                depth=depth + 1,
            )
        else:
            nested = await self._render_existing_node(component, depth=depth)
        preview = "\n".join(
            str(item.get("text") or "")
            for item in component.news or []
            if item.get("text")
        )
        node_text = (
            nested.text
            or component.summary
            or component.prompt
            or preview
            or component.source
            or "[Empty Node]"
        )
        sender = component.name or component.uin or "Unknown User"
        return MessageContextContent(
            text=f"{sender}: {node_text}",
            image_refs=nested.image_refs,
            nested_media=nested.nested_media,
        )

    async def _render_nodes_component(
        self,
        component: Nodes,
        *,
        depth: int,
    ) -> MessageContextContent:
        nested = await self._render_components(
            [*component.nodes],
            include_plain=True,
            depth=depth + 1,
        )
        return MessageContextContent(
            text=nested.text or "[Empty Forward Nodes]",
            image_refs=nested.image_refs,
            nested_media=nested.nested_media,
        )
