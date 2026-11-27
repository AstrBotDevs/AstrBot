from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from astrbot import logger
from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import Forward, Node, Nodes
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from .chain_parser import (
    _extract_image_refs_from_component_chain,
    _extract_text_from_component_chain,
    extract_onebot_forward_nodes,
    extract_onebot_node_fields,
    parse_onebot_segments,
)
from .image_resolver import ImageResolver
from .onebot_client import OneBotClient
from .settings import SETTINGS, QuotedMessageParserSettings

PARSED_FORWARDS_EXTRA_KEY = "_astrbot_parsed_forwards"
COMPANION_FORWARD_INJECTED_EXTRA_KEY = "_companion_forward_injected"
FORWARD_COMPONENT_TYPES = (Forward, Node, Nodes)
FORWARD_CONTENT_HEADER = "[转发聊天记录]"
FORWARD_CONTENT_UNAVAILABLE = "[转发聊天记录（无法拉取详情）]"
_FORWARD_NESTED_LIMIT_PLACEHOLDER = "[转发聊天记录（已达嵌套上限）]"
_TRUNCATION_SUFFIX = "\n...（内容过长，已截断）"
_FORWARD_SEGMENT_TYPES = frozenset({"forward", "forward_msg", "nodes"})


@dataclass(slots=True)
class _FragmentResult:
    lines: list[str] = field(default_factory=list)
    image_refs: list[str] = field(default_factory=list)
    node_count: int = 0
    truncated: bool = False


def has_forward_components(event: AstrMessageEvent) -> bool:
    """Return whether ``event`` carries any top-level Forward/Node/Nodes component."""
    message_obj = getattr(event, "message_obj", None)
    components = getattr(message_obj, "message", None)
    if not isinstance(components, Sequence):
        return False
    return any(isinstance(comp, FORWARD_COMPONENT_TYPES) for comp in components)


def _get_event_extra(event: AstrMessageEvent, key: str) -> Any:
    get_extra = getattr(event, "get_extra", None)
    if callable(get_extra):
        return get_extra(key)
    return None


def _set_event_extra(event: AstrMessageEvent, key: str, value: Any) -> None:
    set_extra = getattr(event, "set_extra", None)
    if callable(set_extra):
        set_extra(key, value)


def is_forward_content_injected(
    event: AstrMessageEvent,
    extra_user_content_parts: Sequence[Any] | None = None,
) -> bool:
    """Return whether forward content has already been injected for this event."""
    if _get_event_extra(event, COMPANION_FORWARD_INJECTED_EXTRA_KEY):
        return True
    if not extra_user_content_parts:
        return False
    return any(
        isinstance(part, TextPart) and part.text.startswith("[转发聊天记录")
        for part in extra_user_content_parts
    )


def format_forward_content_part(parsed: Mapping[str, Any]) -> str:
    """Format a parsed forward payload into a clearly attributed user-context block."""
    combined_text = parsed.get("combined_text")
    text = combined_text.strip() if isinstance(combined_text, str) else ""
    if not text:
        return FORWARD_CONTENT_UNAVAILABLE
    if text.startswith("[转发聊天记录"):
        return text
    return f"{FORWARD_CONTENT_HEADER}\n{text}"


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    if max_chars <= len(_TRUNCATION_SUFFIX):
        return text[:max_chars], True
    keep = max_chars - len(_TRUNCATION_SUFFIX)
    return text[:keep].rstrip() + _TRUNCATION_SUFFIX, True


def _read_cached_forwards(event: AstrMessageEvent) -> dict[str, Any] | None:
    """Normalize a pre-populated v1 ``_astrbot_parsed_forwards`` cache without RPC."""
    raw = _get_event_extra(event, PARSED_FORWARDS_EXTRA_KEY)
    if not isinstance(raw, Mapping) or raw.get("version") != 1:
        return None

    raw_cards = raw.get("cards")
    raw_combined = raw.get("combined_text")
    if not isinstance(raw_combined, str) and not isinstance(raw_cards, list):
        return None

    cards: list[dict[str, Any]] = []
    card_texts: list[str] = []
    card_images: list[str] = []
    card_nodes = 0
    if isinstance(raw_cards, list):
        for item in raw_cards:
            if not isinstance(item, Mapping):
                continue
            card = dict(item)
            cards.append(card)
            summary = card.get("summary_text") or card.get("text")
            if isinstance(summary, str) and summary.strip():
                card_texts.append(summary.strip())
            if isinstance(card.get("image_urls"), list):
                card_images.extend(
                    ref for ref in card["image_urls"] if isinstance(ref, str)
                )
            node_count = card.get("node_count")
            if isinstance(node_count, int) and not isinstance(node_count, bool):
                card_nodes += max(node_count, 0)

    if isinstance(raw_combined, str):
        combined_text = raw_combined.strip()
    elif len(card_texts) <= 1:
        combined_text = card_texts[0] if card_texts else ""
    else:
        combined_text = "\n\n".join(
            f"[转发记录 {idx}]\n{text}" for idx, text in enumerate(card_texts, start=1)
        )

    raw_images = raw.get("image_urls")
    image_urls = normalize_and_dedupe_strings(
        [ref for ref in raw_images if isinstance(ref, str)]
        if isinstance(raw_images, list)
        else card_images
    )

    raw_total_nodes = raw.get("total_nodes")
    total_nodes = (
        max(raw_total_nodes, 0)
        if isinstance(raw_total_nodes, int) and not isinstance(raw_total_nodes, bool)
        else card_nodes
    )

    return {
        "version": 1,
        "source": str(raw.get("source") or "external"),
        "cards": cards,
        "combined_text": combined_text,
        "total_nodes": total_nodes,
        "image_urls": image_urls,
        "truncated": bool(raw.get("truncated", False)),
    }


class ForwardMessageExtractor:
    """Extract top-level Forward/Node/Nodes components into a shared structured payload."""

    def __init__(
        self,
        event: AstrMessageEvent,
        settings: QuotedMessageParserSettings = SETTINGS,
    ) -> None:
        self._event = event
        self._settings = settings
        self._client = OneBotClient(event, settings=settings)
        self._image_resolver = ImageResolver(event, self._client)
        self._fetch_count = 0
        self._fetch_limit_warned = False
        self._payload_cache: dict[str, dict[str, Any] | None] = {}
        self._resolved_image_cache: dict[str, str | None] = {}

    async def extract(self) -> dict[str, Any] | None:
        message_obj = getattr(self._event, "message_obj", None)
        components = getattr(message_obj, "message", None)
        if not isinstance(components, Sequence):
            return None

        top_level_forwards = [
            comp for comp in components if isinstance(comp, FORWARD_COMPONENT_TYPES)
        ]
        if not top_level_forwards:
            return None

        message_id_raw = getattr(message_obj, "message_id", None)
        message_id = (
            str(message_id_raw).strip()
            if message_id_raw is not None and str(message_id_raw).strip()
            else None
        )

        cards: list[dict[str, Any]] = []
        all_image_urls: list[str] = []
        total_nodes = 0
        any_truncated = False

        for comp in top_level_forwards:
            forward_id = ""
            if isinstance(comp, Forward):
                raw_fid = getattr(comp, "id", None)
                forward_id = str(raw_fid).strip() if raw_fid is not None else ""
                fragment = await self._expand_forward_component(
                    comp,
                    depth=0,
                    ancestors=frozenset(),
                )
            elif isinstance(comp, Node):
                fragment = await self._parse_component_nodes(
                    [comp],
                    depth=0,
                    ancestors=frozenset(),
                )
            else:
                fragment = await self._parse_component_nodes(
                    list(comp.nodes),
                    depth=0,
                    ancestors=frozenset(),
                )

            resolved_images = await self._resolve_image_refs(fragment.image_refs)
            raw_card_text = "\n".join(fragment.lines).strip()
            card_truncated = fragment.truncated
            if not raw_card_text:
                if resolved_images:
                    raw_card_text = "[Image]"
                else:
                    raw_card_text = FORWARD_CONTENT_UNAVAILABLE

            card_text, text_truncated = _truncate_text(
                raw_card_text,
                self._settings.max_forward_chars,
            )
            card_truncated = card_truncated or text_truncated
            any_truncated = any_truncated or card_truncated
            total_nodes += fragment.node_count
            all_image_urls.extend(resolved_images)

            card_entry: dict[str, Any] = {
                "forward_id": forward_id,
                "node_count": fragment.node_count,
                "truncated": card_truncated,
                "summary_text": card_text,
                "image_urls": resolved_images,
            }
            if message_id is not None:
                card_entry["message_id"] = message_id
            cards.append(card_entry)

        if len(cards) == 1:
            combined_raw = cards[0]["summary_text"]
        else:
            combined_raw = "\n\n".join(
                f"[转发记录 {idx}]\n{card['summary_text']}"
                for idx, card in enumerate(cards, start=1)
            )

        combined_text, combined_truncated = _truncate_text(
            combined_raw,
            self._settings.max_forward_chars,
        )
        any_truncated = any_truncated or combined_truncated

        payload: dict[str, Any] = {
            "version": 1,
            "source": "astrbot_core",
            "cards": cards,
            "combined_text": combined_text,
            "total_nodes": total_nodes,
            "image_urls": normalize_and_dedupe_strings(all_image_urls),
            "truncated": any_truncated,
        }
        _set_event_extra(self._event, PARSED_FORWARDS_EXTRA_KEY, payload)
        return payload

    async def _resolve_image_refs(self, raw_refs: list[str]) -> list[str]:
        deduped = normalize_and_dedupe_strings(raw_refs)
        if not deduped:
            return []

        resolved_urls: list[str] = []
        for ref in deduped:
            if ref not in self._resolved_image_cache:
                resolved = await self._image_resolver.resolve_for_llm([ref])
                self._resolved_image_cache[ref] = resolved[0] if resolved else None
            cached_url = self._resolved_image_cache[ref]
            if cached_url:
                resolved_urls.append(cached_url)
        return normalize_and_dedupe_strings(resolved_urls)

    async def _expand_forward_component(
        self,
        comp: Forward,
        *,
        depth: int,
        ancestors: frozenset[str],
    ) -> _FragmentResult:
        inline_content = getattr(comp, "content", None)
        if isinstance(inline_content, list) and inline_content:
            if all(isinstance(item, Node) for item in inline_content):
                return await self._parse_component_nodes(
                    inline_content,
                    depth=depth,
                    ancestors=ancestors,
                )
            return await self._parse_onebot_node_list(
                inline_content,
                depth=depth,
                ancestors=ancestors,
            )

        raw_fid = getattr(comp, "id", None)
        forward_id = str(raw_fid).strip() if raw_fid is not None else ""
        if not forward_id:
            return _FragmentResult()
        return await self._fetch_and_parse_forward_id(
            forward_id,
            depth=depth,
            ancestors=ancestors,
        )

    async def _fetch_and_parse_forward_id(
        self,
        forward_id: str,
        *,
        depth: int,
        ancestors: frozenset[str],
    ) -> _FragmentResult:
        if depth > self._settings.max_forward_node_depth:
            indent = "  " * depth
            return _FragmentResult(
                lines=[f"{indent}{_FORWARD_NESTED_LIMIT_PLACEHOLDER}"],
                truncated=True,
            )
        if forward_id in ancestors:
            return _FragmentResult()

        if forward_id in self._payload_cache:
            payload = self._payload_cache[forward_id]
        else:
            if self._fetch_count >= self._settings.max_forward_fetch:
                if (
                    not self._fetch_limit_warned
                    and self._settings.max_forward_fetch > 0
                ):
                    self._fetch_limit_warned = True
                    logger.warning(
                        "quoted_message_parser: stop fetching nested forward messages after %d hops",
                        self._settings.max_forward_fetch,
                    )
                if depth > 0:
                    indent = "  " * depth
                    return _FragmentResult(
                        lines=[f"{indent}{_FORWARD_NESTED_LIMIT_PLACEHOLDER}"],
                        truncated=True,
                    )
                return _FragmentResult(truncated=True)

            self._fetch_count += 1
            payload = await self._client.get_forward_msg(forward_id)
            self._payload_cache[forward_id] = payload

        if not payload:
            if depth > 0:
                indent = "  " * depth
                return _FragmentResult(
                    lines=[f"{indent}{FORWARD_CONTENT_UNAVAILABLE}"],
                )
            return _FragmentResult()

        nodes = extract_onebot_forward_nodes(payload)
        if not nodes:
            if self._settings.warn_on_action_failure:
                logger.warning(
                    "quoted_message_parser: empty or unparseable forward payload for id=%s",
                    forward_id[:64],
                )
            if depth > 0:
                indent = "  " * depth
                return _FragmentResult(
                    lines=[f"{indent}{FORWARD_CONTENT_UNAVAILABLE}"],
                )
            return _FragmentResult()

        return await self._parse_onebot_node_list(
            nodes,
            depth=depth,
            ancestors=ancestors | {forward_id},
        )

    async def _parse_onebot_node_list(
        self,
        nodes: list[Any],
        *,
        depth: int,
        ancestors: frozenset[str],
    ) -> _FragmentResult:
        if depth > self._settings.max_forward_node_depth:
            indent = "  " * depth
            return _FragmentResult(
                lines=[f"{indent}{_FORWARD_NESTED_LIMIT_PLACEHOLDER}"],
                truncated=True,
            )

        result = _FragmentResult()
        indent = "  " * depth

        for node in nodes:
            if not isinstance(node, dict):
                continue

            sender_name, chain = extract_onebot_node_fields(node)
            normal_segments: list[Any] = []
            nested_forward_segments: list[dict[str, Any]] = []
            for seg in chain:
                if isinstance(seg, dict) and seg.get("type") in _FORWARD_SEGMENT_TYPES:
                    nested_forward_segments.append(seg)
                else:
                    normal_segments.append(seg)

            parsed = parse_onebot_segments(
                normal_segments,
                depth=depth,
                settings=self._settings,
            )
            node_text = parsed["text"]
            result.image_refs.extend(parsed["image_refs"])

            has_node_content = bool(
                node_text or parsed["image_refs"] or nested_forward_segments
            )
            if has_node_content:
                result.node_count += 1

            if node_text:
                result.lines.append(f"{indent}{sender_name}: {node_text}")
            elif nested_forward_segments:
                result.lines.append(f"{indent}{sender_name}: {FORWARD_CONTENT_HEADER}")

            for nested_seg in nested_forward_segments:
                seg_data = (
                    nested_seg.get("data", {})
                    if isinstance(nested_seg.get("data"), dict)
                    else {}
                )
                nested_nodes = seg_data.get("content")
                if isinstance(nested_nodes, list) and nested_nodes:
                    nested_fragment = await self._parse_onebot_node_list(
                        nested_nodes,
                        depth=depth + 1,
                        ancestors=ancestors,
                    )
                else:
                    raw_fid = seg_data.get("id") or seg_data.get("message_id")
                    nested_fid = str(raw_fid).strip() if raw_fid is not None else ""
                    if not nested_fid:
                        continue
                    nested_fragment = await self._fetch_and_parse_forward_id(
                        nested_fid,
                        depth=depth + 1,
                        ancestors=ancestors,
                    )

                result.lines.extend(nested_fragment.lines)
                result.image_refs.extend(nested_fragment.image_refs)
                result.node_count += nested_fragment.node_count
                result.truncated = result.truncated or nested_fragment.truncated

        return result

    async def _parse_component_nodes(
        self,
        nodes: list[Node],
        *,
        depth: int,
        ancestors: frozenset[str],
    ) -> _FragmentResult:
        if depth > self._settings.max_forward_node_depth:
            indent = "  " * depth
            return _FragmentResult(
                lines=[f"{indent}{_FORWARD_NESTED_LIMIT_PLACEHOLDER}"],
                truncated=True,
            )

        result = _FragmentResult()
        indent = "  " * depth

        for node in nodes:
            if not isinstance(node, Node):
                continue

            sender_name = str(node.name or node.uin or "Unknown User")
            content = node.content if isinstance(node.content, list) else []
            normal_parts: list[Any] = []
            nested_parts: list[Forward | Node | Nodes] = []
            for seg in content:
                if isinstance(seg, FORWARD_COMPONENT_TYPES):
                    nested_parts.append(seg)
                else:
                    normal_parts.append(seg)

            node_text = _extract_text_from_component_chain(
                normal_parts,
                depth=0,
                settings=self._settings,
            )
            node_images = _extract_image_refs_from_component_chain(
                normal_parts,
                depth=0,
                settings=self._settings,
            )
            result.image_refs.extend(node_images)

            has_node_content = bool(node_text or node_images or nested_parts)
            if has_node_content:
                result.node_count += 1

            if node_text:
                result.lines.append(f"{indent}{sender_name}: {node_text}")
            elif nested_parts:
                result.lines.append(f"{indent}{sender_name}: {FORWARD_CONTENT_HEADER}")

            for nested in nested_parts:
                if isinstance(nested, Forward):
                    nested_fragment = await self._expand_forward_component(
                        nested,
                        depth=depth + 1,
                        ancestors=ancestors,
                    )
                elif isinstance(nested, Node):
                    nested_fragment = await self._parse_component_nodes(
                        [nested],
                        depth=depth + 1,
                        ancestors=ancestors,
                    )
                else:
                    nested_fragment = await self._parse_component_nodes(
                        list(nested.nodes),
                        depth=depth + 1,
                        ancestors=ancestors,
                    )
                result.lines.extend(nested_fragment.lines)
                result.image_refs.extend(nested_fragment.image_refs)
                result.node_count += nested_fragment.node_count
                result.truncated = result.truncated or nested_fragment.truncated

        return result


async def extract_forward_messages(
    event: AstrMessageEvent,
    settings: QuotedMessageParserSettings | None = None,
) -> dict[str, Any] | None:
    """Extract top-level forward messages, reusing ``_astrbot_parsed_forwards`` if present."""
    if not has_forward_components(event):
        return None
    cached = _read_cached_forwards(event)
    if cached is not None:
        return cached
    return await ForwardMessageExtractor(event, settings=settings or SETTINGS).extract()
