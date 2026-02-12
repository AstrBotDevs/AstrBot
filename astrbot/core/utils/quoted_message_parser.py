from __future__ import annotations

import json
import os
import re
from typing import Any

from astrbot import logger
from astrbot.core.message.components import (
    At,
    AtAll,
    File,
    Forward,
    Image,
    Node,
    Nodes,
    Plain,
    Reply,
    Video,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent

_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
}

_FORWARD_PLACEHOLDER_PATTERN = re.compile(
    r"^(?:[\(\[]?[^\]:\)]*[\)\]]?\s*:\s*)?\[(?:forward message|转发消息|合并转发)\]$",
    flags=re.IGNORECASE,
)


def _find_first_reply_component(event: AstrMessageEvent) -> Reply | None:
    for comp in event.message_obj.message:
        if isinstance(comp, Reply):
            return comp
    return None


def _dedupe_keep_order(items: list[str]) -> list[str]:
    uniq: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def _join_text_parts(parts: list[str]) -> str | None:
    text = "".join(parts).strip()
    return text or None


def _is_forward_placeholder_only_text(text: str | None) -> bool:
    if not isinstance(text, str):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    return all(_FORWARD_PLACEHOLDER_PATTERN.match(line) for line in lines)


def _looks_like_image_file_name(name: str) -> bool:
    if not isinstance(name, str) or not name.strip():
        return False
    _, ext = os.path.splitext(name.strip().lower())
    return ext in _IMAGE_EXTENSIONS


def _normalize_image_ref(image_ref: str) -> str | None:
    if not isinstance(image_ref, str):
        return None
    value = image_ref.strip()
    if not value:
        return None
    lower_value = value.lower()

    if lower_value.startswith(("http://", "https://")):
        return value
    if lower_value.startswith("base64://") or lower_value.startswith("data:image/"):
        return value
    if lower_value.startswith("file://"):
        file_path = value[7:]
        if file_path.startswith("/") and len(file_path) > 3 and file_path[2] == ":":
            file_path = file_path[1:]
        if file_path and os.path.exists(file_path):
            return os.path.abspath(file_path)
        return None
    if os.path.exists(value):
        return os.path.abspath(value)
    return None


def _extract_image_refs_from_component_chain(
    chain: list[Any] | None,
    *,
    depth: int = 0,
) -> list[str]:
    if not isinstance(chain, list) or depth > 4:
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
                _extract_image_refs_from_reply_component(seg, depth=depth + 1)
            )
        elif isinstance(seg, Node):
            image_refs.extend(
                _extract_image_refs_from_component_chain(
                    seg.content,
                    depth=depth + 1,
                )
            )
        elif isinstance(seg, Nodes):
            for node in seg.nodes:
                image_refs.extend(
                    _extract_image_refs_from_component_chain(
                        node.content,
                        depth=depth + 1,
                    )
                )

    return _dedupe_keep_order(image_refs)


def _extract_text_from_component_chain(
    chain: list[Any] | None,
    *,
    depth: int = 0,
) -> str | None:
    if not isinstance(chain, list) or depth > 4:
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
        elif isinstance(seg, Video):
            parts.append("[Video]")
        elif isinstance(seg, File):
            file_name = seg.name or "file"
            parts.append(f"[File:{file_name}]")
        elif isinstance(seg, Forward):
            parts.append("[Forward Message]")
        elif isinstance(seg, Reply):
            nested = _extract_text_from_reply_component(seg, depth=depth + 1)
            if nested:
                parts.append(nested)
        elif isinstance(seg, Node):
            node_sender = seg.name or seg.uin or "Unknown User"
            node_text = _extract_text_from_component_chain(
                seg.content,
                depth=depth + 1,
            )
            if node_text:
                parts.append(f"{node_sender}: {node_text}")
        elif isinstance(seg, Nodes):
            for node in seg.nodes:
                node_sender = node.name or node.uin or "Unknown User"
                node_text = _extract_text_from_component_chain(
                    node.content,
                    depth=depth + 1,
                )
                if node_text:
                    parts.append(f"{node_sender}: {node_text}")

    return _join_text_parts(parts)


def _extract_image_refs_from_reply_component(
    reply: Reply,
    *,
    depth: int = 0,
) -> list[str]:
    for attr in ("chain", "message", "origin", "content"):
        payload = getattr(reply, attr, None)
        image_refs = _extract_image_refs_from_component_chain(payload, depth=depth)
        if image_refs:
            return image_refs
    return []


def _extract_text_from_reply_component(reply: Reply, *, depth: int = 0) -> str | None:
    for attr in ("chain", "message", "origin", "content"):
        payload = getattr(reply, attr, None)
        text = _extract_text_from_component_chain(payload, depth=depth)
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
    if parsed.get("config", {}).get("forward") != 1:
        return None

    detail = parsed.get("meta", {}).get("detail", {}) or {}
    news_items = detail.get("news", []) or []
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


def _extract_text_forward_ids_and_images_from_onebot_segments(
    segments: list[Any],
) -> tuple[str | None, list[str], list[str]]:
    text_parts: list[str] = []
    forward_ids: list[str] = []
    image_refs: list[str] = []

    for seg in segments:
        if not isinstance(seg, dict):
            continue

        seg_type = seg.get("type")
        seg_data = seg.get("data", {}) if isinstance(seg.get("data"), dict) else {}

        if seg_type in ("text", "plain"):
            text = seg_data.get("text")
            if isinstance(text, str) and text:
                text_parts.append(text)
        elif seg_type == "image":
            text_parts.append("[Image]")
            candidate = seg_data.get("url") or seg_data.get("file")
            if isinstance(candidate, str) and candidate.strip():
                image_refs.append(candidate.strip())
        elif seg_type == "video":
            text_parts.append("[Video]")
        elif seg_type == "file":
            file_name = (
                seg_data.get("name")
                or seg_data.get("file_name")
                or seg_data.get("file")
                or "file"
            )
            text_parts.append(f"[File:{file_name}]")
            candidate_url = seg_data.get("url")
            if (
                isinstance(candidate_url, str)
                and candidate_url.strip()
                and _looks_like_image_file_name(candidate_url)
            ):
                image_refs.append(candidate_url.strip())
            candidate_file = seg_data.get("file")
            if (
                isinstance(candidate_file, str)
                and candidate_file.strip()
                and _looks_like_image_file_name(
                    seg_data.get("name") or seg_data.get("file_name") or candidate_file
                )
            ):
                image_refs.append(candidate_file.strip())
        elif seg_type in ("forward", "forward_msg", "nodes"):
            fid = seg_data.get("id") or seg_data.get("message_id")
            if isinstance(fid, (str, int)) and str(fid):
                forward_ids.append(str(fid))
            else:
                nested_nodes = seg_data.get("content")
                nested_text, nested_images = (
                    _extract_text_and_images_from_forward_nodes(
                        nested_nodes if isinstance(nested_nodes, list) else [],
                        depth=1,
                    )
                )
                if nested_text:
                    text_parts.append(nested_text)
                if nested_images:
                    image_refs.extend(nested_images)
        elif seg_type == "json":
            raw_json = seg_data.get("data")
            if isinstance(raw_json, str) and raw_json.strip():
                raw_json = raw_json.replace("&#44;", ",")
                multimsg_text = _extract_text_from_multimsg_json(raw_json)
                if multimsg_text:
                    text_parts.append(multimsg_text)

    return _join_text_parts(text_parts), forward_ids, _dedupe_keep_order(image_refs)


def _extract_text_and_images_from_forward_nodes(
    nodes: list[Any],
    *,
    depth: int = 0,
) -> tuple[str | None, list[str]]:
    if not isinstance(nodes, list) or depth > 6:
        return None, []

    texts: list[str] = []
    image_refs: list[str] = []
    indent = "  " * depth

    for node in nodes:
        if not isinstance(node, dict):
            continue

        sender = node.get("sender") if isinstance(node.get("sender"), dict) else {}
        sender_name = (
            sender.get("nickname")
            or sender.get("card")
            or sender.get("user_id")
            or "Unknown User"
        )

        raw_content = node.get("message") or node.get("content") or []
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

        node_text, _forward_ids, node_images = (
            _extract_text_forward_ids_and_images_from_onebot_segments(chain)
        )
        if node_text:
            texts.append(f"{indent}{sender_name}: {node_text}")
        if node_images:
            image_refs.extend(node_images)

        for seg in chain:
            if not isinstance(seg, dict):
                continue
            seg_type = seg.get("type")
            if seg_type != "forward":
                continue
            seg_data = seg.get("data", {}) if isinstance(seg.get("data"), dict) else {}
            nested_nodes = seg_data.get("content")
            nested_text, nested_images = _extract_text_and_images_from_forward_nodes(
                nested_nodes if isinstance(nested_nodes, list) else [],
                depth=depth + 1,
            )
            if nested_text:
                texts.append(nested_text)
            if nested_images:
                image_refs.extend(nested_images)

    return "\n".join(texts).strip() or None, _dedupe_keep_order(image_refs)


def _extract_text_from_onebot_get_msg_payload(payload: dict[str, Any]) -> str | None:
    data = _unwrap_onebot_data(payload)
    segments = data.get("message") or data.get("messages")
    if isinstance(segments, list):
        text, _forward_ids, _image_refs = (
            _extract_text_forward_ids_and_images_from_onebot_segments(segments)
        )
        return text
    if isinstance(segments, str) and segments.strip():
        return segments.strip()
    raw = data.get("raw_message")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _extract_image_refs_from_onebot_get_msg_payload(
    payload: dict[str, Any],
) -> list[str]:
    data = _unwrap_onebot_data(payload)
    segments = data.get("message") or data.get("messages")
    if not isinstance(segments, list):
        return []
    _text, _forward_ids, image_refs = (
        _extract_text_forward_ids_and_images_from_onebot_segments(segments)
    )
    return image_refs


def _extract_forward_ids_from_onebot_get_msg_payload(
    payload: dict[str, Any],
) -> list[str]:
    data = _unwrap_onebot_data(payload)
    segments = data.get("message") or data.get("messages")
    if not isinstance(segments, list):
        return []
    _text, forward_ids, _image_refs = (
        _extract_text_forward_ids_and_images_from_onebot_segments(segments)
    )
    return forward_ids


def _extract_text_from_onebot_get_forward_payload(
    payload: dict[str, Any],
) -> str | None:
    data = _unwrap_onebot_data(payload)
    nodes = (
        data.get("messages")
        or data.get("message")
        or data.get("nodes")
        or data.get("nodeList")
    )
    if not isinstance(nodes, list):
        return None
    text, _image_refs = _extract_text_and_images_from_forward_nodes(nodes)
    return text


def _extract_image_refs_from_onebot_get_forward_payload(
    payload: dict[str, Any],
) -> list[str]:
    data = _unwrap_onebot_data(payload)
    nodes = (
        data.get("messages")
        or data.get("message")
        or data.get("nodes")
        or data.get("nodeList")
    )
    if not isinstance(nodes, list):
        return []
    _text, image_refs = _extract_text_and_images_from_forward_nodes(nodes)
    return image_refs


def _get_call_action(event: AstrMessageEvent):
    bot = getattr(event, "bot", None)
    api = getattr(bot, "api", None)
    call_action = getattr(api, "call_action", None)
    if not callable(call_action):
        return None
    return call_action


async def _call_action_try_params(
    event: AstrMessageEvent,
    action: str,
    params_list: list[dict[str, Any]],
) -> dict[str, Any] | None:
    call_action = _get_call_action(event)
    if call_action is None:
        return None

    for params in params_list:
        try:
            result = await call_action(action, **params)
            if isinstance(result, dict):
                return result
        except Exception as exc:
            logger.debug(
                "quoted_message_parser: action %s failed with params %s: %s",
                action,
                {k: str(v)[:64] for k, v in params.items()},
                exc,
            )
    return None


async def _call_action_compat(
    event: AstrMessageEvent,
    action: str,
    message_id: str,
) -> dict[str, Any] | None:
    if not message_id.strip():
        return None

    params_list: list[dict[str, Any]] = [
        {"message_id": message_id},
        {"id": message_id},
    ]
    if message_id.isdigit():
        int_id = int(message_id)
        params_list.extend([{"message_id": int_id}, {"id": int_id}])
    return await _call_action_try_params(event, action, params_list)


def _unwrap_action_response(ret: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(ret, dict):
        return {}
    data = ret.get("data")
    if isinstance(data, dict):
        return data
    return ret


def _build_image_id_candidates(image_ref: str) -> list[str]:
    candidates: list[str] = [image_ref]
    base_name, ext = os.path.splitext(image_ref)
    if ext and base_name and base_name not in candidates:
        if ext.lower() in _IMAGE_EXTENSIONS:
            candidates.append(base_name)
    return candidates


def _build_image_resolve_actions(
    event: AstrMessageEvent,
    image_ref: str,
) -> list[tuple[str, dict[str, Any]]]:
    actions: list[tuple[str, dict[str, Any]]] = []
    candidates = _build_image_id_candidates(image_ref)

    for candidate in candidates:
        actions.extend(
            [
                ("get_image", {"file": candidate}),
                ("get_image", {"file_id": candidate}),
                ("get_image", {"id": candidate}),
                ("get_image", {"image": candidate}),
                ("get_file", {"file_id": candidate}),
                ("get_file", {"file": candidate}),
            ]
        )

    try:
        group_id = event.get_group_id()
    except Exception:
        group_id = None
    group_id_value = group_id
    if isinstance(group_id, str) and group_id.isdigit():
        group_id_value = int(group_id)

    if group_id_value:
        for candidate in candidates:
            actions.append(
                (
                    "get_group_file_url",
                    {"group_id": group_id_value, "file_id": candidate},
                )
            )
    for candidate in candidates:
        actions.append(("get_private_file_url", {"file_id": candidate}))

    return actions


async def _resolve_onebot_image_ref(
    event: AstrMessageEvent,
    image_ref: str,
) -> str | None:
    resolved = _normalize_image_ref(image_ref)
    if resolved:
        return resolved

    actions = _build_image_resolve_actions(event, image_ref)
    for action, params in actions:
        ret = await _call_action_try_params(event, action, [params])
        data = _unwrap_action_response(ret)

        url = data.get("url")
        if isinstance(url, str):
            normalized = _normalize_image_ref(url)
            if normalized:
                return normalized

        file_value = data.get("file")
        if isinstance(file_value, str):
            if file_value.startswith("base64://") or file_value.startswith(
                "data:image/"
            ):
                return file_value
            normalized = _normalize_image_ref(file_value)
            if normalized:
                return normalized

    return None


async def _resolve_image_refs_for_llm(
    event: AstrMessageEvent,
    image_refs: list[str],
) -> list[str]:
    resolved: list[str] = []
    unresolved: list[str] = []

    for image_ref in _dedupe_keep_order(image_refs):
        normalized = _normalize_image_ref(image_ref)
        if normalized:
            resolved.append(normalized)
        else:
            unresolved.append(image_ref)

    for image_ref in unresolved:
        resolved_ref = await _resolve_onebot_image_ref(event, image_ref)
        if resolved_ref:
            resolved.append(resolved_ref)

    return _dedupe_keep_order(resolved)


async def extract_quoted_message_text(
    event: AstrMessageEvent,
    reply_component: Reply | None = None,
) -> str | None:
    reply = reply_component or _find_first_reply_component(event)
    if not reply:
        return None

    embedded_text = _extract_text_from_reply_component(reply)
    if embedded_text and not _is_forward_placeholder_only_text(embedded_text):
        return embedded_text

    reply_id = getattr(reply, "id", None)
    if reply_id is None:
        return embedded_text
    reply_id_str = str(reply_id).strip()
    if not reply_id_str:
        return embedded_text

    msg_payload = await _call_action_compat(event, "get_msg", reply_id_str)
    if not msg_payload:
        return embedded_text

    text_parts: list[str] = []
    direct_text = _extract_text_from_onebot_get_msg_payload(msg_payload)
    if direct_text:
        text_parts.append(direct_text)

    forward_ids = _extract_forward_ids_from_onebot_get_msg_payload(msg_payload)
    for forward_id in forward_ids:
        forward_payload = await _call_action_compat(
            event,
            "get_forward_msg",
            forward_id,
        )
        if not forward_payload:
            continue
        forward_text = _extract_text_from_onebot_get_forward_payload(forward_payload)
        if forward_text:
            text_parts.append(forward_text)

    return "\n".join(text_parts).strip() or embedded_text


async def extract_quoted_message_images(
    event: AstrMessageEvent,
    reply_component: Reply | None = None,
) -> list[str]:
    reply = reply_component or _find_first_reply_component(event)
    if not reply:
        return []

    image_refs = _extract_image_refs_from_reply_component(reply)
    if image_refs:
        return await _resolve_image_refs_for_llm(event, image_refs)

    reply_id = getattr(reply, "id", None)
    if reply_id is None:
        return []
    reply_id_str = str(reply_id).strip()
    if not reply_id_str:
        return []

    msg_payload = await _call_action_compat(event, "get_msg", reply_id_str)
    if not msg_payload:
        return []

    image_refs = _extract_image_refs_from_onebot_get_msg_payload(msg_payload)
    forward_ids = _extract_forward_ids_from_onebot_get_msg_payload(msg_payload)

    for forward_id in forward_ids:
        forward_payload = await _call_action_compat(
            event,
            "get_forward_msg",
            forward_id,
        )
        if not forward_payload:
            continue
        image_refs.extend(
            _extract_image_refs_from_onebot_get_forward_payload(forward_payload)
        )

    return await _resolve_image_refs_for_llm(event, image_refs)
