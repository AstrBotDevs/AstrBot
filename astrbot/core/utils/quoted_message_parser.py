from __future__ import annotations

import json
import os
import re
from typing import Any, TypedDict
from urllib.parse import urlsplit

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
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

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

_MAX_COMPONENT_CHAIN_DEPTH = 4
_MAX_FORWARD_NODE_DEPTH = 6
_MAX_FORWARD_FETCH = 32

_FORWARD_PLACEHOLDER_PATTERN = re.compile(
    r"^(?:[\(\[]?[^\]:\)]*[\)\]]?\s*:\s*)?\[(?:forward message|转发消息|合并转发)\]$",
    flags=re.IGNORECASE,
)


class ParsedOneBotMessage(TypedDict):
    text: str | None
    forward_ids: list[str]
    image_refs: list[str]


def _find_first_reply_component(event: AstrMessageEvent) -> Reply | None:
    for comp in event.message_obj.message:
        if isinstance(comp, Reply):
            return comp
    return None


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
    normalized_name = _normalize_file_like_url(name)
    if not isinstance(normalized_name, str) or not normalized_name.strip():
        return False
    _, ext = os.path.splitext(normalized_name.strip().lower())
    return ext in _IMAGE_EXTENSIONS


def _normalize_file_like_url(path: str | None) -> str | None:
    if path is None:
        return None
    if not isinstance(path, str):
        return None
    if "?" not in path and "#" not in path:
        return path
    try:
        split = urlsplit(path)
    except Exception:
        return path
    return split.path or path


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
    if not isinstance(chain, list) or depth > _MAX_COMPONENT_CHAIN_DEPTH:
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

    return normalize_and_dedupe_strings(image_refs)


def _extract_text_from_component_chain(
    chain: list[Any] | None,
    *,
    depth: int = 0,
) -> str | None:
    if not isinstance(chain, list) or depth > _MAX_COMPONENT_CHAIN_DEPTH:
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
                and _looks_like_image_file_name(_normalize_file_like_url(candidate_url))
            ):
                image_refs.append(candidate_url.strip())
            candidate_file = seg_data.get("file")
            if (
                isinstance(candidate_file, str)
                and candidate_file.strip()
                and _looks_like_image_file_name(
                    _normalize_file_like_url(
                        seg_data.get("name")
                        or seg_data.get("file_name")
                        or candidate_file
                    )
                )
            ):
                image_refs.append(candidate_file.strip())
        elif seg_type in ("forward", "forward_msg", "nodes"):
            fid = seg_data.get("id") or seg_data.get("message_id")
            if isinstance(fid, (str, int)) and str(fid):
                forward_ids.append(str(fid))
            else:
                nested_nodes = seg_data.get("content")
                nested_text, nested_forward_ids, nested_images = (
                    _extract_text_forward_ids_and_images_from_forward_nodes(
                        nested_nodes if isinstance(nested_nodes, list) else [],
                        depth=1,
                    )
                )
                if nested_text:
                    text_parts.append(nested_text)
                if nested_forward_ids:
                    forward_ids.extend(nested_forward_ids)
                if nested_images:
                    image_refs.extend(nested_images)
        elif seg_type == "json":
            raw_json = seg_data.get("data")
            if isinstance(raw_json, str) and raw_json.strip():
                raw_json = raw_json.replace("&#44;", ",")
                multimsg_text = _extract_text_from_multimsg_json(raw_json)
                if multimsg_text:
                    text_parts.append(multimsg_text)

    return (
        _join_text_parts(text_parts),
        forward_ids,
        normalize_and_dedupe_strings(image_refs),
    )


def _extract_text_forward_ids_and_images_from_forward_nodes(
    nodes: list[Any],
    *,
    depth: int = 0,
) -> tuple[str | None, list[str], list[str]]:
    if not isinstance(nodes, list) or depth > _MAX_FORWARD_NODE_DEPTH:
        return None, [], []

    texts: list[str] = []
    forward_ids: list[str] = []
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

        node_text, node_forward_ids, node_images = (
            _extract_text_forward_ids_and_images_from_onebot_segments(chain)
        )
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
) -> ParsedOneBotMessage:
    data = _unwrap_onebot_data(payload)
    segments = data.get("message") or data.get("messages")
    if isinstance(segments, list):
        text, forward_ids, image_refs = (
            _extract_text_forward_ids_and_images_from_onebot_segments(segments)
        )
        return {
            "text": text,
            "forward_ids": forward_ids,
            "image_refs": image_refs,
        }

    text: str | None = None
    if isinstance(segments, str) and segments.strip():
        text = segments.strip()
    else:
        raw = data.get("raw_message")
        if isinstance(raw, str) and raw.strip():
            text = raw.strip()
    return {
        "text": text,
        "forward_ids": [],
        "image_refs": [],
    }


def _parse_onebot_get_forward_payload(
    payload: dict[str, Any],
) -> ParsedOneBotMessage:
    data = _unwrap_onebot_data(payload)
    nodes = (
        data.get("messages")
        or data.get("message")
        or data.get("nodes")
        or data.get("nodeList")
    )
    if not isinstance(nodes, list):
        return {
            "text": None,
            "forward_ids": [],
            "image_refs": [],
        }
    text, forward_ids, image_refs = (
        _extract_text_forward_ids_and_images_from_forward_nodes(nodes)
    )
    return {
        "text": text,
        "forward_ids": forward_ids,
        "image_refs": image_refs,
    }


def _unwrap_action_response(ret: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(ret, dict):
        return {}
    data = ret.get("data")
    if isinstance(data, dict):
        return data
    return ret


class OneBotClient:
    def __init__(self, event: AstrMessageEvent):
        self._event = event
        self._call_action = self._resolve_call_action(event)

    @staticmethod
    def _resolve_call_action(event: AstrMessageEvent):
        bot = getattr(event, "bot", None)
        api = getattr(bot, "api", None)
        call_action = getattr(api, "call_action", None)
        if not callable(call_action):
            return None
        return call_action

    async def _call_action_try_params(
        self,
        action: str,
        params_list: list[dict[str, Any]],
        *,
        warn_on_all_failed: bool = True,
    ) -> dict[str, Any] | None:
        if self._call_action is None:
            return None

        last_error: Exception | None = None
        last_params: dict[str, Any] | None = None
        for params in params_list:
            try:
                result = await self._call_action(action, **params)
                if isinstance(result, dict):
                    return result
            except Exception as exc:
                last_error = exc
                last_params = params
                logger.debug(
                    "quoted_message_parser: action %s failed with params %s: %s",
                    action,
                    {k: str(v)[:64] for k, v in params.items()},
                    exc,
                )
        if warn_on_all_failed and last_error is not None:
            logger.warning(
                "quoted_message_parser: all attempts failed for action %s, "
                "last_params=%s, error=%s",
                action,
                (
                    {k: str(v)[:64] for k, v in last_params.items()}
                    if isinstance(last_params, dict)
                    else None
                ),
                last_error,
            )
        return None

    async def call(
        self,
        action: str,
        params: dict[str, Any],
        *,
        warn_on_all_failed: bool = False,
        unwrap_data: bool = True,
    ) -> dict[str, Any] | None:
        ret = await self._call_action_try_params(
            action,
            [params],
            warn_on_all_failed=warn_on_all_failed,
        )
        if not unwrap_data:
            return ret
        return _unwrap_action_response(ret)

    async def _call_action_compat(
        self,
        action: str,
        message_id: str | int,
    ) -> dict[str, Any] | None:
        message_id_str = str(message_id).strip()
        if not message_id_str:
            return None

        params_list: list[dict[str, Any]] = [
            {"message_id": message_id_str},
            {"id": message_id_str},
        ]
        if message_id_str.isdigit():
            int_id = int(message_id_str)
            params_list.extend([{"message_id": int_id}, {"id": int_id}])
        return await self._call_action_try_params(action, params_list)

    async def get_msg(self, message_id: str | int) -> dict[str, Any] | None:
        return await self._call_action_compat("get_msg", message_id)

    async def get_forward_msg(self, forward_id: str | int) -> dict[str, Any] | None:
        return await self._call_action_compat("get_forward_msg", forward_id)


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


class ImageResolver:
    def __init__(
        self,
        event: AstrMessageEvent,
        onebot_client: OneBotClient | None = None,
    ):
        self._event = event
        self._client = onebot_client or OneBotClient(event)

    async def resolve_for_llm(self, image_refs: list[str]) -> list[str]:
        resolved: list[str] = []
        unresolved: list[str] = []

        for image_ref in normalize_and_dedupe_strings(image_refs):
            normalized = _normalize_image_ref(image_ref)
            if normalized:
                resolved.append(normalized)
            else:
                unresolved.append(image_ref)

        for image_ref in unresolved:
            resolved_ref = await self._resolve_one(image_ref)
            if resolved_ref:
                resolved.append(resolved_ref)

        return normalize_and_dedupe_strings(resolved)

    async def _resolve_one(self, image_ref: str) -> str | None:
        resolved = _normalize_image_ref(image_ref)
        if resolved:
            return resolved

        actions = _build_image_resolve_actions(self._event, image_ref)
        for action, params in actions:
            data = await self._client.call(
                action,
                params,
                warn_on_all_failed=False,
                unwrap_data=True,
            )
            if not isinstance(data, dict):
                continue

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

        logger.warning(
            "quoted_message_parser: failed to resolve quoted image ref=%s after %d actions",
            image_ref[:128],
            len(actions),
        )
        return None


async def _collect_text_and_images_from_forward_ids(
    onebot_client: OneBotClient,
    forward_ids: list[str],
    *,
    max_fetch: int = _MAX_FORWARD_FETCH,
) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    image_refs: list[str] = []
    pending: list[str] = []
    seen: set[str] = set()

    for fid in forward_ids:
        if not isinstance(fid, str):
            continue
        cleaned = fid.strip()
        if cleaned:
            pending.append(cleaned)

    fetch_count = 0
    while pending and fetch_count < max_fetch:
        current_id = pending.pop(0)
        if current_id in seen:
            continue
        seen.add(current_id)
        fetch_count += 1

        forward_payload = await onebot_client.get_forward_msg(current_id)
        if not forward_payload:
            continue

        parsed = _parse_onebot_get_forward_payload(forward_payload)
        if parsed["text"]:
            texts.append(parsed["text"])
        if parsed["image_refs"]:
            image_refs.extend(parsed["image_refs"])
        for nested_id in parsed["forward_ids"]:
            if nested_id not in seen:
                pending.append(nested_id)

    if pending:
        logger.warning(
            "quoted_message_parser: stop fetching nested forward messages after %d hops",
            max_fetch,
        )

    return texts, normalize_and_dedupe_strings(image_refs)


class QuotedMessageExtractor:
    def __init__(self, event: AstrMessageEvent):
        self._event = event
        self._client = OneBotClient(event)
        self._image_resolver = ImageResolver(event, self._client)

    async def text(self, reply_component: Reply | None = None) -> str | None:
        reply = reply_component or _find_first_reply_component(self._event)
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

        msg_payload = await self._client.get_msg(reply_id_str)
        if not msg_payload:
            return embedded_text

        parsed = _parse_onebot_get_msg_payload(msg_payload)
        text_parts: list[str] = []
        direct_text = parsed["text"]
        if direct_text:
            text_parts.append(direct_text)

        (
            forward_texts,
            _forward_images,
        ) = await _collect_text_and_images_from_forward_ids(
            self._client,
            parsed["forward_ids"],
        )
        text_parts.extend(forward_texts)

        return "\n".join(text_parts).strip() or embedded_text

    async def images(self, reply_component: Reply | None = None) -> list[str]:
        reply = reply_component or _find_first_reply_component(self._event)
        if not reply:
            return []

        image_refs = list(_extract_image_refs_from_reply_component(reply))

        reply_id = getattr(reply, "id", None)
        if reply_id is None:
            return await self._image_resolver.resolve_for_llm(image_refs)
        reply_id_str = str(reply_id).strip()
        if not reply_id_str:
            return await self._image_resolver.resolve_for_llm(image_refs)

        msg_payload = await self._client.get_msg(reply_id_str)
        if not msg_payload:
            return await self._image_resolver.resolve_for_llm(image_refs)

        parsed = _parse_onebot_get_msg_payload(msg_payload)
        image_refs.extend(parsed["image_refs"])

        (
            _forward_texts,
            forward_images,
        ) = await _collect_text_and_images_from_forward_ids(
            self._client,
            parsed["forward_ids"],
        )
        image_refs.extend(forward_images)

        return await self._image_resolver.resolve_for_llm(image_refs)


async def extract_quoted_message_text(
    event: AstrMessageEvent,
    reply_component: Reply | None = None,
) -> str | None:
    return await QuotedMessageExtractor(event).text(reply_component)


async def extract_quoted_message_images(
    event: AstrMessageEvent,
    reply_component: Reply | None = None,
) -> list[str]:
    return await QuotedMessageExtractor(event).images(reply_component)
