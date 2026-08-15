import json
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from astrbot.core.message.components import (
    At,
    AtAll,
    Face,
    File,
    Forward,
    Image,
    Node,
    Nodes,
    Plain,
    Reply,
    Video,
)
from astrbot.core.message.qq_face import format_qq_face
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from .image_refs import looks_like_image_file_name
from .settings import SETTINGS, QuotedMessageParserSettings

_FORWARD_PLACEHOLDER_PATTERN = re.compile(
    r"^(?:[\(\[]?[^\]:\)]*[\)\]]?\s*:\s*)?\[(?:forward message|转发消息|合并转发)\]$",
    flags=re.IGNORECASE,
)


class ParsedOneBotPayload(TypedDict):
    text: str | None
    forward_ids: list[str]
    image_refs: list[str]


def _build_parsed_payload(
    text: str | None,
    forward_ids: list[str] | None = None,
    image_refs: list[str] | None = None,
) -> ParsedOneBotPayload:
    return {
        "text": text,
        "forward_ids": forward_ids or [],
        "image_refs": image_refs or [],
    }


def _join_text_parts(parts: list[str]) -> str | None:
    text = "".join(parts).strip()
    return text or None


def _find_first_reply_component(event: AstrMessageEvent) -> Reply | None:
    for comp in event.message_obj.message:
        if isinstance(comp, Reply):
            return comp
    return None


def _is_forward_placeholder_only_text(text: str | None) -> bool:
    if not isinstance(text, str):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    return all(_FORWARD_PLACEHOLDER_PATTERN.match(line) for line in lines)


def _extract_image_refs_from_component_chain(
    chain: list[Any] | None,
    *,
    depth: int = 0,
    settings: QuotedMessageParserSettings = SETTINGS,
) -> list[str]:
    if not isinstance(chain, list) or depth > settings.max_component_chain_depth:
        return []

    image_refs: list[str] = []
    for seg in chain:
        if isinstance(seg, Image):
            for candidate in (seg.url, seg.file, seg.path):
                if isinstance(candidate, str) and candidate.strip():
                    image_refs.append(candidate.strip())
                    break
        elif isinstance(seg, Reply):
            image_refs.extend(
                _extract_image_refs_from_reply_component(
                    seg,
                    depth=depth + 1,
                    settings=settings,
                )
            )
        elif isinstance(seg, Node):
            image_refs.extend(
                _extract_image_refs_from_component_chain(
                    seg.content,
                    depth=depth + 1,
                    settings=settings,
                )
            )
        elif isinstance(seg, Nodes):
            for node in seg.nodes:
                image_refs.extend(
                    _extract_image_refs_from_component_chain(
                        node.content,
                        depth=depth + 1,
                        settings=settings,
                    )
                )

    return normalize_and_dedupe_strings(image_refs)


def _extract_text_from_component_chain(
    chain: list[Any] | None,
    *,
    depth: int = 0,
    settings: QuotedMessageParserSettings = SETTINGS,
) -> str | None:
    if not isinstance(chain, list) or depth > settings.max_component_chain_depth:
        return None

    parts: list[str] = []
    for seg in chain:
        if isinstance(seg, Plain):
            if seg.text:
                parts.append(seg.text)
        elif isinstance(seg, At):
            if seg.name:
                parts.append(f"@{seg.name}")
            elif seg.qq:
                parts.append(f"@{seg.qq}")
        elif isinstance(seg, AtAll):
            parts.append("@all")
        elif isinstance(seg, Image):
            parts.append("[Image]")
        elif isinstance(seg, Face):
            parts.append(format_qq_face(seg.id))
        elif isinstance(seg, Video):
            parts.append("[Video]")
        elif isinstance(seg, File):
            file_name = seg.name or "file"
            parts.append(f"[File:{file_name}]")
        elif isinstance(seg, Forward):
            parts.append("[Forward Message]")
        elif isinstance(seg, Reply):
            nested = _extract_text_from_reply_component(
                seg,
                depth=depth + 1,
                settings=settings,
            )
            if nested:
                parts.append(nested)
        elif isinstance(seg, Node):
            node_sender = seg.name or seg.uin or "Unknown User"
            node_text = _extract_text_from_component_chain(
                seg.content,
                depth=depth + 1,
                settings=settings,
            )
            if node_text:
                parts.append(f"{node_sender}: {node_text}")
        elif isinstance(seg, Nodes):
            for node in seg.nodes:
                node_sender = node.name or node.uin or "Unknown User"
                node_text = _extract_text_from_component_chain(
                    node.content,
                    depth=depth + 1,
                    settings=settings,
                )
                if node_text:
                    parts.append(f"{node_sender}: {node_text}")

    return _join_text_parts(parts)


def _extract_image_refs_from_reply_component(
    reply: Reply,
    *,
    depth: int = 0,
    settings: QuotedMessageParserSettings = SETTINGS,
) -> list[str]:
    for attr in ("chain", "message", "origin", "content"):
        payload = getattr(reply, attr, None)
        image_refs = _extract_image_refs_from_component_chain(
            payload,
            depth=depth,
            settings=settings,
        )
        if image_refs:
            return image_refs
    return []


def _extract_text_from_reply_component(
    reply: Reply,
    *,
    depth: int = 0,
    settings: QuotedMessageParserSettings = SETTINGS,
) -> str | None:
    for attr in ("chain", "message", "origin", "content"):
        payload = getattr(reply, attr, None)
        text = _extract_text_from_component_chain(
            payload,
            depth=depth,
            settings=settings,
        )
        if text:
            return text

    if reply.message_str and reply.message_str.strip():
        return reply.message_str.strip()
    return None


def _unwrap_onebot_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _extract_text_from_multimsg_json(raw_json: str) -> str | None:
    try:
        parsed = json.loads(raw_json)
    except Exception:
        return None

    if not isinstance(parsed, dict):
        return None
    if parsed.get("app") != "com.tencent.multimsg":
        return None
    config = parsed.get("config")
    if not isinstance(config, dict):
        return None
    if config.get("forward") != 1:
        return None

    meta = parsed.get("meta")
    if not isinstance(meta, dict):
        return None
    detail = meta.get("detail")
    if not isinstance(detail, dict):
        return None
    news_items = detail.get("news")
    if not isinstance(news_items, list):
        return None

    texts: list[str] = []
    for item in news_items:
        if not isinstance(item, dict):
            continue
        text_content = item.get("text")
        if not isinstance(text_content, str):
            continue
        cleaned = text_content.strip().replace("[图片]", "").strip()
        if cleaned:
            texts.append(cleaned)

    return "\n".join(texts).strip() or None


@dataclass
class _OneBotSegmentParseState:
    text_parts: list[str]
    forward_ids: list[str]
    image_refs: list[str]


def _parse_simple_onebot_segment(seg_type: str, seg_data: dict[Any, Any]) -> str | None:
    labels = {
        "video": "[Video]",
        "record": "[Audio]",
        "voice": "[Audio]",
        "dice": "[Dice]",
        "rps": "[Rock Paper Scissors]",
        "shake": "[Window Shake]",
        "miniapp": "[MiniApp]",
        "xml": "[XML]",
        "reply": "[Quoted Message]",
        "flashtransfer": "[Flash Transfer]",
    }
    if label := labels.get(seg_type):
        return label
    if seg_type in ("text", "plain"):
        text = seg_data.get("text")
        return text if isinstance(text, str) and text else None
    if seg_type == "at":
        target = seg_data.get("name") or seg_data.get("qq")
        return f"@{target}" if target is not None else None
    if seg_type == "face":
        return format_qq_face(seg_data.get("id"))
    if seg_type == "mface":
        summary = seg_data.get("summary")
        return summary if isinstance(summary, str) else "[Market Face]"
    if seg_type == "poke":
        return f"[Poke:{seg_data.get('id', '')}]"
    if seg_type == "share":
        return f"[Share:{seg_data.get('title', '')} {seg_data.get('url', '')}]"
    if seg_type == "contact":
        return f"[Contact:{seg_data.get('type', '')} {seg_data.get('id', '')}]"
    if seg_type == "location":
        return (
            f"[Location:{seg_data.get('title', '')} "
            f"({seg_data.get('lat', '')}, {seg_data.get('lon', '')})]"
        )
    if seg_type == "music":
        return f"[Music:{seg_data.get('title') or seg_data.get('type') or seg_data.get('id', '')}]"
    if seg_type == "markdown":
        content = seg_data.get("content")
        return f"[Markdown]{content}" if isinstance(content, str) else "[Markdown]"
    if seg_type == "onlinefile":
        return f"[Online File:{seg_data.get('fileName', '')}]"
    return None


def _parse_onebot_image_segment(
    seg_data: dict[Any, Any],
    state: _OneBotSegmentParseState,
    *,
    forward_depth: int,
    settings: QuotedMessageParserSettings,
) -> None:
    del forward_depth, settings
    state.text_parts.append("[Image]")
    candidate = seg_data.get("url") or seg_data.get("file")
    if isinstance(candidate, str) and candidate.strip():
        state.image_refs.append(candidate.strip())


def _parse_onebot_file_segment(
    seg_data: dict[Any, Any],
    state: _OneBotSegmentParseState,
    *,
    forward_depth: int,
    settings: QuotedMessageParserSettings,
) -> None:
    del forward_depth, settings
    file_name = (
        seg_data.get("name")
        or seg_data.get("file_name")
        or seg_data.get("file")
        or "file"
    )
    state.text_parts.append(f"[File:{file_name}]")
    candidate_url = seg_data.get("url", "")
    if (
        isinstance(candidate_url, str)
        and candidate_url.strip()
        and looks_like_image_file_name(candidate_url)
    ):
        state.image_refs.append(candidate_url.strip())
    candidate_file = seg_data.get("file")
    if (
        isinstance(candidate_file, str)
        and candidate_file.strip()
        and looks_like_image_file_name(
            seg_data.get("name") or seg_data.get("file_name") or candidate_file
        )
    ):
        state.image_refs.append(candidate_file.strip())


def _parse_onebot_node_segment(
    seg_data: dict[Any, Any],
    state: _OneBotSegmentParseState,
    *,
    forward_depth: int,
    settings: QuotedMessageParserSettings,
) -> None:
    raw_content = seg_data.get("content") or seg_data.get("message") or []
    nested_text, nested_forward_ids, nested_images = (
        _extract_text_forward_ids_and_images_from_forward_nodes(
            [
                {
                    "sender": {
                        "nickname": seg_data.get("nickname") or seg_data.get("name"),
                        "user_id": seg_data.get("user_id") or seg_data.get("uin"),
                    },
                    "message": raw_content,
                }
            ],
            depth=forward_depth + 1,
            settings=settings,
        )
    )
    if nested_text:
        state.text_parts.append(nested_text)
    state.forward_ids.extend(nested_forward_ids)
    state.image_refs.extend(nested_images)


def _parse_onebot_forward_segment(
    seg_data: dict[Any, Any],
    state: _OneBotSegmentParseState,
    *,
    forward_depth: int,
    settings: QuotedMessageParserSettings,
) -> None:
    nested_nodes = seg_data.get("content")
    forward_id = seg_data.get("id") or seg_data.get("message_id")
    if isinstance(nested_nodes, list) and nested_nodes:
        nested_text, nested_forward_ids, nested_images = (
            _extract_text_forward_ids_and_images_from_forward_nodes(
                nested_nodes,
                depth=forward_depth + 1,
                settings=settings,
            )
        )
        if nested_text:
            state.text_parts.append(nested_text)
        if nested_forward_ids:
            state.forward_ids.extend(nested_forward_ids)
        if nested_images:
            state.image_refs.extend(nested_images)
    elif isinstance(forward_id, (str, int)) and str(forward_id):
        state.forward_ids.append(str(forward_id))


def _parse_onebot_json_segment(
    seg_data: dict[Any, Any],
    state: _OneBotSegmentParseState,
    *,
    forward_depth: int,
    settings: QuotedMessageParserSettings,
) -> None:
    del forward_depth, settings
    raw_json = seg_data.get("data")
    if isinstance(raw_json, str) and raw_json.strip():
        multimsg_text = _extract_text_from_multimsg_json(raw_json.replace("&#44;", ","))
        state.text_parts.append(multimsg_text or "[JSON]")


_COMPLEX_ONEBOT_SEGMENT_PARSERS = {
    "image": _parse_onebot_image_segment,
    "file": _parse_onebot_file_segment,
    "node": _parse_onebot_node_segment,
    "forward": _parse_onebot_forward_segment,
    "forward_msg": _parse_onebot_forward_segment,
    "nodes": _parse_onebot_forward_segment,
    "json": _parse_onebot_json_segment,
}


def _parse_onebot_segments(
    segments: list[Any],
    *,
    forward_depth: int = 0,
    settings: QuotedMessageParserSettings = SETTINGS,
) -> ParsedOneBotPayload:
    state = _OneBotSegmentParseState([], [], [])
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        seg_type = seg.get("type")
        if not isinstance(seg_type, str):
            continue
        seg_data = seg.get("data", {}) if isinstance(seg.get("data"), dict) else {}
        parser = _COMPLEX_ONEBOT_SEGMENT_PARSERS.get(seg_type)
        if parser is not None:
            parser(
                seg_data,
                state,
                forward_depth=forward_depth,
                settings=settings,
            )
            continue
        if text := _parse_simple_onebot_segment(seg_type, seg_data):
            state.text_parts.append(text)

    return _build_parsed_payload(
        _join_text_parts(state.text_parts),
        state.forward_ids,
        normalize_and_dedupe_strings(state.image_refs),
    )


def _extract_text_forward_ids_and_images_from_forward_nodes(
    nodes: list[Any],
    *,
    depth: int = 0,
    settings: QuotedMessageParserSettings = SETTINGS,
) -> tuple[str | None, list[str], list[str]]:
    if not isinstance(nodes, list) or depth > settings.max_forward_node_depth:
        return None, [], []

    texts: list[str] = []
    forward_ids: list[str] = []
    image_refs: list[str] = []
    indent = "  " * depth

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_data = node
        if node.get("type") == "node" and isinstance(node.get("data"), dict):
            node_data = node["data"]

        sender = node_data.get("sender")
        if not isinstance(sender, dict):
            sender = {}
        sender_name = (
            sender.get("nickname")
            or sender.get("card")
            or sender.get("user_id")
            or node_data.get("nickname")
            or node_data.get("name")
            or node_data.get("user_id")
            or "Unknown User"
        )

        raw_content = node_data.get("message") or node_data.get("content") or []
        chain: list[Any] = []
        if isinstance(raw_content, list):
            chain = raw_content
        elif isinstance(raw_content, str):
            raw_content = raw_content.strip()
            if raw_content:
                try:
                    parsed = json.loads(raw_content)
                except Exception:
                    parsed = None
                if isinstance(parsed, list):
                    chain = parsed
                else:
                    chain = [{"type": "text", "data": {"text": raw_content}}]

        parsed_segments = _parse_onebot_segments(
            chain,
            forward_depth=depth,
            settings=settings,
        )
        node_text = parsed_segments["text"]
        node_forward_ids = parsed_segments["forward_ids"]
        node_images = parsed_segments["image_refs"]
        if node_text:
            texts.append(f"{indent}{sender_name}: {node_text}")
        if node_forward_ids:
            forward_ids.extend(node_forward_ids)
        if node_images:
            image_refs.extend(node_images)

    return (
        "\n".join(texts).strip() or None,
        normalize_and_dedupe_strings(forward_ids),
        normalize_and_dedupe_strings(image_refs),
    )


def _parse_onebot_get_msg_payload(
    payload: dict[str, Any],
    *,
    settings: QuotedMessageParserSettings = SETTINGS,
) -> ParsedOneBotPayload:
    data = _unwrap_onebot_data(payload)
    segments = data.get("message") or data.get("messages")
    if isinstance(segments, list):
        return _parse_onebot_segments(segments, settings=settings)

    text: str | None = None
    if isinstance(segments, str) and segments.strip():
        text = segments.strip()
    else:
        raw = data.get("raw_message")
        if isinstance(raw, str) and raw.strip():
            text = raw.strip()
    return _build_parsed_payload(text)


def _parse_onebot_get_forward_payload(
    payload: dict[str, Any],
    *,
    settings: QuotedMessageParserSettings = SETTINGS,
) -> ParsedOneBotPayload:
    data = _unwrap_onebot_data(payload)
    nodes = (
        data.get("messages")
        or data.get("message")
        or data.get("nodes")
        or data.get("nodeList")
    )
    if not isinstance(nodes, list):
        return _build_parsed_payload(None)

    text, forward_ids, image_refs = (
        _extract_text_forward_ids_and_images_from_forward_nodes(
            nodes,
            settings=settings,
        )
    )
    return _build_parsed_payload(text, forward_ids, image_refs)


class ReplyChainParser:
    def __init__(self, settings: QuotedMessageParserSettings = SETTINGS):
        self._settings = settings

    @staticmethod
    def find_first_reply_component(event: AstrMessageEvent) -> Reply | None:
        return _find_first_reply_component(event)

    @staticmethod
    def is_forward_placeholder_only_text(text: str | None) -> bool:
        return _is_forward_placeholder_only_text(text)

    def extract_text_from_reply_component(
        self,
        reply: Reply,
        *,
        depth: int = 0,
    ) -> str | None:
        return _extract_text_from_reply_component(
            reply,
            depth=depth,
            settings=self._settings,
        )

    def extract_image_refs_from_reply_component(
        self,
        reply: Reply,
        *,
        depth: int = 0,
    ) -> list[str]:
        return _extract_image_refs_from_reply_component(
            reply,
            depth=depth,
            settings=self._settings,
        )


class OneBotPayloadParser:
    def __init__(self, settings: QuotedMessageParserSettings = SETTINGS):
        self._settings = settings

    def parse_get_msg_payload(self, payload: dict[str, Any]) -> ParsedOneBotPayload:
        return _parse_onebot_get_msg_payload(payload, settings=self._settings)

    def parse_get_forward_payload(
        self,
        payload: dict[str, Any],
    ) -> ParsedOneBotPayload:
        return _parse_onebot_get_forward_payload(payload, settings=self._settings)
