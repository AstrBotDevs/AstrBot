from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, TypedDict, cast

from astrbot import logger
from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import star_map, star_registry
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata, star_handlers_registry


class DryRunBlockedSideEffect(RuntimeError):
    def __init__(self, action: str, detail: str | None = None) -> None:
        super().__init__(detail or action)
        self.action = action
        self.detail = detail or ""


@dataclass
class DryRunBlockedAction:
    action: str
    reason: str


@dataclass
class DryRunHandlerDiff:
    prompt_before: str
    prompt_after: str
    system_prompt_before: str
    system_prompt_after: str
    extra_user_content_parts_before_len: int
    extra_user_content_parts_after_len: int

    def to_summary(self) -> dict[str, Any]:
        return {
            "prompt": {
                "changed": self.prompt_before != self.prompt_after,
                "before_len": len(self.prompt_before or ""),
                "after_len": len(self.prompt_after or ""),
            },
            "system_prompt": {
                "changed": self.system_prompt_before != self.system_prompt_after,
                "before_len": len(self.system_prompt_before or ""),
                "after_len": len(self.system_prompt_after or ""),
            },
            "extra_user_content_parts": {
                "changed": self.extra_user_content_parts_before_len != self.extra_user_content_parts_after_len,
                "before_len": int(self.extra_user_content_parts_before_len),
                "after_len": int(self.extra_user_content_parts_after_len),
            },
        }


@dataclass
class DryRunHandlerRecord:
    plugin: dict[str, Any]
    handler: dict[str, Any]
    priority: int
    status: Literal["executed", "blocked", "errored", "skipped"]
    blocked: list[DryRunBlockedAction] = field(default_factory=list)
    error: str | None = None
    stop_event: bool = False
    diff: dict[str, Any] | None = None


class SystemPromptSegmentSource(TypedDict):
    plugin: str
    handler: str
    priority: int
    field: str
    mutation: str
    status: str


class SystemPromptSegment(TypedDict):
    text: str
    source: SystemPromptSegmentSource | None
    # Optional: a segment may be derived from persona prompt but affected by multiple plugins.
    # Backward compatible: older UI can keep reading `source`.
    sources: list[SystemPromptSegmentSource] | None


def _serialize_handler_record(r: DryRunHandlerRecord) -> dict[str, Any]:
    return {
        "plugin": r.plugin,
        "handler": r.handler,
        "priority": int(r.priority),
        "status": str(r.status),
        "blocked": [{"action": b.action, "reason": b.reason} for b in (r.blocked or [])],
        "error": r.error,
        "stop_event": bool(r.stop_event),
        "diff": r.diff,
    }


def _common_prefix_suffix_len(before: str, after: str) -> tuple[int, int]:
    # longest common prefix
    i = 0
    while i < len(before) and i < len(after) and before[i] == after[i]:
        i += 1

    # longest common suffix (avoid overlapping with prefix)
    j = 0
    while (
        j < len(before) - i
        and j < len(after) - i
        and before[-(j + 1)] == after[-(j + 1)]
    ):
        j += 1

    return i, j


def _segments_join(segments: list[SystemPromptSegment]) -> str:
    return "".join(str(s.get("text") or "") for s in (segments or []))


def _segments_to_char_stream(
    segments: list[SystemPromptSegment],
) -> list[tuple[str, SystemPromptSegmentSource | None, list[SystemPromptSegmentSource] | None]]:
    out: list[tuple[str, SystemPromptSegmentSource | None, list[SystemPromptSegmentSource] | None]] = []
    for seg in segments or []:
        text = str(seg.get("text") or "")
        if not text:
            continue
        src = seg.get("source")
        # Important: force single-source segments; multi-source mixing breaks UI expectations.
        for ch in text:
            out.append((ch, src, None))
    return out


def _char_stream_to_segments(
    chars: list[tuple[str, SystemPromptSegmentSource | None, list[SystemPromptSegmentSource] | None]],
) -> list[SystemPromptSegment]:
    out: list[SystemPromptSegment] = []
    if not chars:
        return out

    cur_text: list[str] = []
    cur_src: SystemPromptSegmentSource | None = None

    def flush() -> None:
        nonlocal cur_text, cur_src
        if not cur_text:
            return
        out.append({"text": "".join(cur_text), "source": cur_src, "sources": None})
        cur_text = []

    for ch, src, _srcs in chars:
        if not cur_text:
            cur_text = [ch]
            cur_src = src
            continue

        if cur_src == src:
            cur_text.append(ch)
            continue

        flush()
        cur_text = [ch]
        cur_src = src

    flush()
    return out


def _content_part_key(part: Any) -> str:
    if part is None:
        return ""
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        return json.dumps(part, ensure_ascii=False, sort_keys=True, default=str)
    model_dump = getattr(part, "model_dump", None)
    if callable(model_dump):
        try:
            data = model_dump()
            return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return str(part)
    return str(part)


def _content_part_display(part: Any) -> str:
    if part is None:
        return ""
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if part.get("type") == "text":
            return str(part.get("text") or "")
        return json.dumps(part, ensure_ascii=False, sort_keys=True, default=str)
    model_dump = getattr(part, "model_dump", None)
    if callable(model_dump):
        try:
            data = model_dump()
            if isinstance(data, dict) and data.get("type") == "text":
                return str(data.get("text") or "")
            return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return str(part)
    return str(part)


def _compact_system_segments(segments: list[SystemPromptSegment]) -> list[SystemPromptSegment]:
    out: list[SystemPromptSegment] = []
    for seg in segments or []:
        text = str(seg.get("text") or "")
        if not text:
            continue
        src = seg.get("source")
        if out and out[-1].get("source") == src:
            out[-1]["text"] = str(out[-1].get("text") or "") + text
            continue
        out.append({"text": text, "source": src, "sources": None})
    return out


def _merge_same_plugin_segments(segments: list[SystemPromptSegment]) -> list[SystemPromptSegment]:
    """
    Merge consecutive segments from the same plugin into larger blocks.

    Goal:
    - Reduce fragmentation for UI rendering (e.g. merge multiple meme_manager writes into one block)
    - Keep backward compatibility: always populate `source`; optionally attach `sources` when merged
      segments came from multiple handlers/mutations of the same plugin.

    Rules:
    - Adjacent segments with the same `source.plugin` are merged (even if handler/mutation differs).
    - Whitespace-only segments with no plugin attribution are treated as "neutral glue" and merged
      into the current non-empty plugin block to avoid breaking a continuous paragraph visually.
    """
    if not segments:
        return []

    def is_whitespace_only(text: str) -> bool:
        return bool(text) and (text.strip() == "")

    def get_source(seg: SystemPromptSegment) -> SystemPromptSegmentSource | None:
        src = seg.get("source")
        return cast(SystemPromptSegmentSource | None, src) if isinstance(src, dict) else None

    def plugin_key(src: SystemPromptSegmentSource | None) -> str | None:
        if not src:
            return None
        k = str(src.get("plugin") or "").strip()
        return k or None

    def source_key(src: SystemPromptSegmentSource) -> tuple[str, str, int, str, str, str]:
        return (
            str(src.get("plugin") or ""),
            str(src.get("handler") or ""),
            int(src.get("priority") or 0),
            str(src.get("field") or ""),
            str(src.get("mutation") or ""),
            str(src.get("status") or ""),
        )

    out: list[SystemPromptSegment] = []

    cur_text: list[str] = []
    cur_primary_source: SystemPromptSegmentSource | None = None
    cur_plugin: str | None = None
    cur_sources: list[SystemPromptSegmentSource] = []
    cur_sources_seen: set[tuple[str, str, int, str, str, str]] = set()

    def flush() -> None:
        nonlocal cur_text, cur_primary_source, cur_plugin, cur_sources, cur_sources_seen
        if not cur_text:
            return
        merged_text = "".join(cur_text)
        if not merged_text:
            cur_text = []
            cur_primary_source = None
            cur_plugin = None
            cur_sources = []
            cur_sources_seen = set()
            return

        merged_sources = cur_sources if len(cur_sources) > 1 else None
        out.append({"text": merged_text, "source": cur_primary_source, "sources": merged_sources})

        cur_text = []
        cur_primary_source = None
        cur_plugin = None
        cur_sources = []
        cur_sources_seen = set()

    for seg in segments:
        text = str(seg.get("text") or "")
        if not text:
            continue

        src = get_source(seg)
        seg_plugin = plugin_key(src)

        # "Neutral glue": keep whitespace-only unknown segments inside current plugin block
        # to avoid breaking a continuous paragraph into multiple UI blocks.
        if seg_plugin is None and is_whitespace_only(text) and cur_plugin is not None:
            cur_text.append(text)
            continue

        if not cur_text:
            cur_text = [text]
            cur_primary_source = src
            cur_plugin = seg_plugin
            if src is not None:
                k = source_key(src)
                cur_sources_seen.add(k)
                cur_sources.append(src)
            continue

        if seg_plugin == cur_plugin:
            cur_text.append(text)
            if cur_primary_source is None and src is not None:
                cur_primary_source = src
            if src is not None:
                k = source_key(src)
                if k not in cur_sources_seen:
                    cur_sources_seen.add(k)
                    cur_sources.append(src)
            continue

        flush()
        cur_text = [text]
        cur_primary_source = src
        cur_plugin = seg_plugin
        if src is not None:
            k = source_key(src)
            cur_sources_seen.add(k)
            cur_sources.append(src)

    flush()
    return out


def _neutralize_whitespace_segments(segments: list[SystemPromptSegment]) -> list[SystemPromptSegment]:
    """
    Normalize whitespace-only segments for UI rendering.

    - Whitespace-only segments should not carry attribution, so the UI can render them fully transparent.
    - Preserve the original whitespace exactly (including newlines/indentation) to keep prompt layout intact.
    """
    out: list[SystemPromptSegment] = []
    for seg in segments or []:
        text = str(seg.get("text") or "")
        if not text:
            continue
        if text.strip() == "":
            out.append({"text": text, "source": None, "sources": None})
            continue
        out.append({"text": text, "source": seg.get("source"), "sources": seg.get("sources")})
    return _compact_system_segments(out)


def _ensure_boundary(segments: list[SystemPromptSegment], index: int) -> list[SystemPromptSegment]:
    if index <= 0:
        return segments
    total = sum(len(str(s.get("text") or "")) for s in (segments or []))
    if index >= total:
        return segments

    out: list[SystemPromptSegment] = []
    pos = 0
    for seg in segments or []:
        text = str(seg.get("text") or "")
        src = seg.get("source")
        nxt = pos + len(text)
        if index <= pos or index >= nxt:
            out.append({"text": text, "source": src, "sources": None})
            pos = nxt
            continue

        cut = index - pos
        left = text[:cut]
        right = text[cut:]
        if left:
            out.append({"text": left, "source": src, "sources": None})
        if right:
            out.append({"text": right, "source": src, "sources": None})
        pos = nxt
    return out


def _apply_system_prompt_change(
    *,
    segments: list[SystemPromptSegment],
    before: str,
    after: str,
    plugin: str,
    handler: str,
    priority: int,
    status: str,
    inserted_override: list[SystemPromptSegment] | None = None,
) -> tuple[list[SystemPromptSegment], bool]:
    """
    Update system prompt segments with character-level provenance tracking.

    Key rule for overwrite/replace:
    - Only the longest common prefix/suffix is considered "preserved";
      the middle region is attributed to current handler as a continuous write.
    This avoids false "preservation" caused by incidental substring matches.
    """
    if before == after:
        return segments, False

    # Keep segments in sync with `before`
    if _segments_join(segments) != before:
        segments = [{"text": before, "source": None, "sources": None}] if before else []

    # Special-case: inserted_override is used to precisely attribute persona prompt insertion.
    # Keep the original boundary-based insertion logic for this scenario.
    if inserted_override is not None:
        prefix_len, suffix_len = _common_prefix_suffix_len(before, after)
        before_mid_end = len(before) - suffix_len

        start = prefix_len
        end = before_mid_end

        segments = _ensure_boundary(segments, start)
        segments = _ensure_boundary(segments, end)

        out: list[SystemPromptSegment] = []
        pos = 0
        inserted = False

        insert_segments: list[SystemPromptSegment] = []
        for seg in inserted_override or []:
            if str(seg.get("text") or ""):
                insert_segments.append(seg)

        for seg in segments or []:
            text = str(seg.get("text") or "")
            seg_len = len(text)

            if not inserted and pos == start:
                out.extend(insert_segments)
                inserted = True

            # Drop replaced range [start, end)
            if pos >= start and pos < end:
                pos += seg_len
                continue

            out.append({"text": text, "source": seg.get("source"), "sources": seg.get("sources")})
            pos += seg_len

        if not inserted and start == pos and insert_segments:
            out.extend(insert_segments)

        out = _compact_system_segments(out)
        if _segments_join(out) != after:
            return ([{"text": after, "source": None, "sources": None}] if after else []), True
        return out, False

    # Prefix/suffix anchored character attribution (prevents accidental mid-string matches)
    prefix_len, suffix_len = _common_prefix_suffix_len(before, after)
    before_mid_end = len(before) - suffix_len
    after_mid_end = len(after) - suffix_len
    before_mid = before[prefix_len:before_mid_end]
    after_mid = after[prefix_len:after_mid_end]

    before_chars = _segments_to_char_stream(segments)
    if len(before_chars) != len(before):
        segments = [{"text": before, "source": None, "sources": None}] if before else []
        before_chars = _segments_to_char_stream(segments)

    out_chars: list[tuple[str, SystemPromptSegmentSource | None, list[SystemPromptSegmentSource] | None]] = []

    def build_handler_source(mutation: str) -> SystemPromptSegmentSource:
        return {
            "plugin": str(plugin),
            "handler": str(handler),
            "priority": int(priority),
            "field": "system_prompt",
            "mutation": str(mutation or "unknown"),
            "status": str(status),
        }

    # Preserved prefix
    if prefix_len > 0:
        out_chars.extend(before_chars[:prefix_len])

    # Middle region: insertion/deletion/replace
    if before_mid == "" and after_mid != "":
        if prefix_len == 0 and suffix_len == len(before):
            mutation = "prepend"
        elif prefix_len == len(before) and suffix_len == 0:
            mutation = "append"
        else:
            mutation = "insert"
        src = build_handler_source(mutation)
        for ch in after_mid:
            out_chars.append((ch, src, None))
    elif before_mid != "" and after_mid == "":
        # deletion: no output chars to attribute
        pass
    elif before_mid != "" and after_mid != "":
        src = build_handler_source("replace")
        for ch in after_mid:
            out_chars.append((ch, src, None))

    # Preserved suffix
    if suffix_len > 0:
        out_chars.extend(before_chars[len(before) - suffix_len :])

    out = _compact_system_segments(_char_stream_to_segments(out_chars))
    if _segments_join(out) != after:
        return ([{"text": after, "source": None, "sources": None}] if after else []), True
    return out, False


def _plugin_ref(module_path: str) -> dict[str, Any]:
    meta = star_map.get(module_path)
    if meta and meta.name:
        return {
            "name": meta.name,
            "display_name": meta.display_name,
            "reserved": bool(meta.reserved),
            "activated": bool(meta.activated),
            "version": meta.version,
            "repo": meta.repo,
        }
    return {
        "name": module_path,
        "display_name": None,
        "reserved": True,
        "activated": True,
        "version": None,
        "repo": None,
    }


def _handler_ref(handler: StarHandlerMetadata) -> dict[str, Any]:
    return {
        "handler_full_name": handler.handler_full_name,
        "handler_name": handler.handler_name,
        "handler_module_path": handler.handler_module_path,
    }


def _priority(handler: StarHandlerMetadata) -> int:
    p = handler.extras_configs.get("priority", 0)
    try:
        return int(p)
    except Exception:
        return 0


class DryRunAstrMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        *,
        umo: str,
        message_str: str,
        plugins_name: list[str] | None,
    ) -> None:
        # UMO format: platform:message_type:session_id
        parts = [p for p in str(umo or "").split(":") if p is not None]
        platform_id = (parts[0] if len(parts) >= 1 else "") or "unknown"
        session_id = (parts[-1] if len(parts) >= 3 else "") or "preview"

        platform_meta = PlatformMetadata(
            name=platform_id,
            description="preview",
            id=platform_id,
            support_streaming_message=False,
        )

        message_obj = AstrBotMessage()
        message_obj.type = MessageType.FRIEND_MESSAGE
        message_obj.self_id = "preview_bot"
        message_obj.session_id = session_id
        message_obj.message_id = "preview"
        message_obj.sender = MessageMember(user_id="preview_user", nickname="preview_user")
        message_obj.message = [Plain(message_str)]
        message_obj.message_str = message_str
        message_obj.raw_message = None

        super().__init__(
            message_str=message_str,
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id=session_id,
        )
        self.unified_msg_origin = umo
        self.plugins_name = plugins_name

        # Align with typical pipeline state where LLM request happens after waking stage.
        self.is_wake = True
        self.is_at_or_wake_command = True

        self._dry_run_blocked: list[DryRunBlockedAction] = []
        self._dry_run_stop_count = 0

    def clear_dry_run_blocked_actions(self) -> None:
        self._dry_run_blocked.clear()

    @property
    def dry_run_blocked_actions(self) -> list[DryRunBlockedAction]:
        return list(self._dry_run_blocked)

    @property
    def dry_run_stop_count(self) -> int:
        return self._dry_run_stop_count

    def stop_event(self):
        self._dry_run_stop_count += 1
        return super().stop_event()

    def request_llm(self, *args, **kwargs) -> ProviderRequest:  # type: ignore[override]
        self._dry_run_blocked.append(
            DryRunBlockedAction(
                action="request_llm",
                reason="预览 Dry-run 禁止创建/触发新的 LLM 请求（避免副作用/费用）。",
            )
        )
        raise DryRunBlockedSideEffect("request_llm", "dry-run blocked")

    async def send(self, *args, **kwargs):  # type: ignore[override]
        self._dry_run_blocked.append(
            DryRunBlockedAction(
                action="send",
                reason="预览 Dry-run 禁止向平台发送消息（避免副作用）。",
            )
        )
        raise DryRunBlockedSideEffect("send", "dry-run blocked")

    async def send_streaming(self, *args, **kwargs):  # type: ignore[override]
        self._dry_run_blocked.append(
            DryRunBlockedAction(
                action="send_streaming",
                reason="预览 Dry-run 禁止流式发送（避免副作用）。",
            )
        )
        raise DryRunBlockedSideEffect("send_streaming", "dry-run blocked")

    async def react(self, *args, **kwargs):  # type: ignore[override]
        self._dry_run_blocked.append(
            DryRunBlockedAction(
                action="react",
                reason="预览 Dry-run 禁止平台交互（避免副作用）。",
            )
        )
        raise DryRunBlockedSideEffect("react", "dry-run blocked")


def compute_effective_plugins_name_for_preview(
    *,
    umo: str,
    plugin_set: list[str] | None,
) -> list[str] | None:
    """
    Determine plugins_name used by star_handlers_registry filtering.
    - `None` means allow all (except disabled/!activated via registry itself).
    - `[]` means allow no non-reserved plugins (reserved plugins may still run).
    """
    if plugin_set is None:
        allowed: list[str] = []
        for meta in star_registry:
            if not meta.activated:
                continue
            if meta.reserved:
                continue
            if not meta.name:
                continue
            if SessionPluginManager.is_plugin_enabled_for_session(umo, meta.name):
                allowed.append(meta.name)
        allowed = sorted(set(allowed))
        return allowed

    # Respect explicit plugin_set allowlist, then apply session-level enable/disable
    filtered = [n for n in plugin_set if n and SessionPluginManager.is_plugin_enabled_for_session(umo, n)]
    return sorted(set(filtered))


def _sort_handlers_for_llm_request(handlers: Iterable[StarHandlerMetadata]) -> list[StarHandlerMetadata]:
    return sorted(
        list(handlers),
        key=lambda h: (-_priority(h), str(h.handler_full_name or "")),
    )


def _iter_effective_llm_request_handlers(
    *,
    plugins_name: list[str] | None,
) -> list[StarHandlerMetadata]:
    handlers = star_handlers_registry.get_handlers_by_event_type(
        EventType.OnLLMRequestEvent,
        plugins_name=plugins_name,
    )
    return _sort_handlers_for_llm_request(handlers)


async def dry_run_execute_on_llm_request(
    *,
    event: DryRunAstrMessageEvent,
    req: ProviderRequest,
    persona_prompt_text: str | None = None,
    persona_prompt_sources: list[SystemPromptSegmentSource] | None = None,
    debug: bool = False,
) -> tuple[list[DryRunHandlerRecord], list[str], list[SystemPromptSegment]]:
    records: list[DryRunHandlerRecord] = []
    warnings: list[str] = []

    system_segments: list[SystemPromptSegment] = []
    initial_system = str(req.system_prompt or "")
    if initial_system:
        system_segments = [{"text": initial_system, "source": None, "sources": None}]

    extra_user_segments: list[SystemPromptSegment] = []
    initial_extra_parts = list(getattr(req, "extra_user_content_parts", []) or [])
    if initial_extra_parts:
        extra_user_segments = [{"text": _content_part_display(p), "source": None, "sources": None} for p in initial_extra_parts if _content_part_display(p)]

    if debug:
        logger.info(
            "prompt_preview: dry_run_execute_on_llm_request: initial system_prompt len=%s; persona_text_len=%s; persona_sources=%s; extra_user_parts=%s",
            len(initial_system),
            len(str(persona_prompt_text or "")),
            len(list(persona_prompt_sources or [])),
            len(initial_extra_parts),
        )

    handlers = _iter_effective_llm_request_handlers(plugins_name=event.plugins_name)

    for handler in handlers:
        if not handler.enabled:
            continue

        plugin_ref = _plugin_ref(handler.handler_module_path)
        handler_ref = _handler_ref(handler)
        pr = _priority(handler)

        event.clear_dry_run_blocked_actions()
        stop_count_before = event.dry_run_stop_count

        before_prompt = str(req.prompt or "")
        before_system = str(req.system_prompt or "")
        before_extra_parts = list(getattr(req, "extra_user_content_parts", []) or [])
        before_extra_keys = [_content_part_key(p) for p in before_extra_parts]

        record = DryRunHandlerRecord(
            plugin=plugin_ref,
            handler=handler_ref,
            priority=pr,
            status="executed",
        )

        started_at = time.time()
        try:
            awaitable = handler.handler(event, req)
            if awaitable is not None:
                # All OnLLMRequestEvent handlers are expected to be coroutine functions.
                # Still, we keep this defensive await for custom plugins.
                await awaitable
        except DryRunBlockedSideEffect as e:
            record.status = "blocked"
            record.blocked = event.dry_run_blocked_actions or [
                DryRunBlockedAction(action=e.action, reason="预览 Dry-run 阻止了副作用调用。")
            ]
            record.error = f"{e.__class__.__name__}: {str(e)}"
            warnings.append(
                f"{plugin_ref.get('name')} - {handler_ref.get('handler_name')}：副作用被阻止（{e.action}）。"
            )
        except BaseException as e:  # noqa: BLE001
            record.status = "errored"
            record.error = f"{e.__class__.__name__}: {e}"
            warnings.append(
                f"{plugin_ref.get('name')} - {handler_ref.get('handler_name')}：执行异常（{e.__class__.__name__}）。"
            )
            logger.error("prompt preview dry-run: handler error: %s", record.error, exc_info=True)

        after_prompt = str(req.prompt or "")
        after_system = str(req.system_prompt or "")
        after_extra_parts = list(getattr(req, "extra_user_content_parts", []) or [])
        after_extra_keys = [_content_part_key(p) for p in after_extra_parts]

        diff = DryRunHandlerDiff(
            prompt_before=before_prompt,
            prompt_after=after_prompt,
            system_prompt_before=before_system,
            system_prompt_after=after_system,
            extra_user_content_parts_before_len=len(before_extra_parts),
            extra_user_content_parts_after_len=len(after_extra_parts),
        )
        record.diff = diff.to_summary()

        if before_extra_keys != after_extra_keys:
            handler_source: SystemPromptSegmentSource = {
                "plugin": str(plugin_ref.get("name") or ""),
                "handler": str(handler_ref.get("handler_name") or ""),
                "priority": int(pr),
                "field": "extra_user_content_parts",
                "mutation": "replace",
                "status": str(record.status),
            }

            appended = False
            if len(after_extra_keys) >= len(before_extra_keys) and after_extra_keys[: len(before_extra_keys)] == before_extra_keys:
                # pure append
                new_parts = after_extra_parts[len(before_extra_parts) :]
                appended_source: SystemPromptSegmentSource = {
                    "plugin": handler_source["plugin"],
                    "handler": handler_source["handler"],
                    "priority": handler_source["priority"],
                    "field": handler_source["field"],
                    "mutation": "append",
                    "status": handler_source["status"],
                }
                for p in new_parts:
                    txt = _content_part_display(p)
                    if not txt:
                        continue
                    extra_user_segments.append({"text": txt, "source": appended_source, "sources": None})
                appended = True

            if not appended:
                warnings.append(
                    f"{plugin_ref.get('name')} - {handler_ref.get('handler_name')}：extra_user_content_parts 发生非 append 变更（不可精确归因），已重置为不可归因段。"
                )
                extra_user_segments = [{"text": _content_part_display(p), "source": None, "sources": None} for p in after_extra_parts if _content_part_display(p)]

            extra_user_segments = _compact_system_segments(extra_user_segments)

            if debug:
                logger.info(
                    "prompt_preview: extra_user_content_parts now len=%s; appended=%s",
                    len(after_extra_parts),
                    appended,
                )

        if before_system != after_system:
            if _segments_join(system_segments) != before_system:
                warnings.append(
                    "system_prompt 分段归因发生不同步（可能由非标准修改导致），已重置为不可归因段以保持一致性。"
                )
                system_segments = [{"text": before_system, "source": None, "sources": None}] if before_system else []

            inserted_override: list[SystemPromptSegment] | None = None
            persona_text = str(persona_prompt_text or "")
            persona_sources = list(persona_prompt_sources or [])

            if persona_text and persona_sources:
                prefix_len, suffix_len = _common_prefix_suffix_len(before_system, after_system)
                before_mid_end = len(before_system) - suffix_len
                after_mid_end = len(after_system) - suffix_len
                before_mid = before_system[prefix_len:before_mid_end]
                after_mid = after_system[prefix_len:after_mid_end]

                pure_insertion = (before_mid == "") and (after_mid != "")
                if debug:
                    logger.info(
                        "prompt_preview: system_prompt changed by %s/%s P%s status=%s; before_len=%s after_len=%s; prefix=%s suffix=%s; pure_insertion=%s; persona_in_after_mid=%s",
                        plugin_ref.get("name"),
                        handler_ref.get("handler_name"),
                        pr,
                        record.status,
                        len(before_system),
                        len(after_system),
                        prefix_len,
                        suffix_len,
                        pure_insertion,
                        bool(persona_text and (persona_text in after_mid)),
                    )

                if pure_insertion and persona_text in after_mid:
                    idx = after_mid.find(persona_text)
                    left = after_mid[:idx]
                    mid = persona_text
                    right = after_mid[idx + len(persona_text) :]

                    primary: SystemPromptSegmentSource | None = None
                    influencer: SystemPromptSegmentSource | None = None

                    for s in persona_sources or []:
                        try:
                            if not isinstance(s, dict):
                                continue
                            plugin_name = str(s.get("plugin") or "")
                            if plugin_name.startswith("persona:") and primary is None:
                                primary = cast(SystemPromptSegmentSource, s)
                                continue
                            if plugin_name and not plugin_name.startswith("persona:"):
                                influencer = cast(SystemPromptSegmentSource, s)
                        except Exception:
                            continue

                    if primary is None and persona_sources:
                        try:
                            primary = cast(SystemPromptSegmentSource, persona_sources[0])
                        except Exception:
                            primary = None

                    persona_seg: SystemPromptSegment = {
                        "text": mid,
                        "source": primary,
                        # Important: do NOT attach multi-sources here; UI should show a single origin per segment.
                        "sources": None,
                    }

                    # If persona insertion contains extra text around persona_text, attribute it to the influencer
                    # (e.g. meme_manager overwrote/extended persona_prompt). This makes the UI show different colors
                    # and clicking a segment shows only its own source.
                    insert_mutation = "unknown"
                    if prefix_len == 0 and suffix_len == len(before_system):
                        insert_mutation = "prepend"
                    elif prefix_len == len(before_system) and suffix_len == 0:
                        insert_mutation = "append"

                    handler_source: SystemPromptSegmentSource = {
                        "plugin": str(plugin_ref.get("name") or ""),
                        "handler": str(handler_ref.get("handler_name") or ""),
                        "priority": int(pr),
                        "field": "system_prompt",
                        "mutation": insert_mutation,
                        "status": str(record.status),
                    }

                    side_source = influencer or handler_source

                    inserted_override = []
                    if left:
                        inserted_override.append({"text": left, "source": side_source, "sources": None})
                    inserted_override.append(persona_seg)
                    if right:
                        inserted_override.append({"text": right, "source": side_source, "sources": None})

                    if debug:
                        logger.info(
                            "prompt_preview: persona insertion detected: left_len=%s persona_len=%s right_len=%s; persona_sources=%s; side_source_plugin=%s; handler_mutation=%s",
                            len(left),
                            len(mid),
                            len(right),
                            len(persona_sources),
                            (side_source or {}).get("plugin") if isinstance(side_source, dict) else None,
                            insert_mutation,
                        )

            updated, fallback = _apply_system_prompt_change(
                segments=system_segments,
                before=before_system,
                after=after_system,
                plugin=str(plugin_ref.get("name") or ""),
                handler=str(handler_ref.get("handler_name") or ""),
                priority=int(pr),
                status=str(record.status),
                inserted_override=inserted_override,
            )
            system_segments = updated

            if debug:
                head = system_segments[:3]
                logger.info(
                    "prompt_preview: system_segments now len=%s; head=%s",
                    len(system_segments),
                    [
                        {
                            "text_len": len(str(s.get("text") or "")),
                            "source_plugin": (s.get("source") or {}).get("plugin") if isinstance(s.get("source"), dict) else None,
                            "source_field": (s.get("source") or {}).get("field") if isinstance(s.get("source"), dict) else None,
                            "sources_len": len(s.get("sources") or []) if isinstance(s.get("sources"), list) else 0,
                        }
                        for s in head
                    ],
                )

            if fallback:
                warnings.append(
                    f"{plugin_ref.get('name')} - {handler_ref.get('handler_name')}：system_prompt 分段归因失败，已回退为不可归因段。"
                )

        stop_now = event.is_stopped()
        stop_called = event.dry_run_stop_count > stop_count_before
        if stop_now or stop_called:
            record.stop_event = True
            if stop_now:
                warnings.append(
                    f"{plugin_ref.get('name')} - {handler_ref.get('handler_name')}：触发 stop_event，后续 hooks 将不再执行。"
                )

        if event.dry_run_blocked_actions:
            record.blocked = event.dry_run_blocked_actions
            if record.status == "executed":
                record.status = "blocked"
                warnings.append(
                    f"{plugin_ref.get('name')} - {handler_ref.get('handler_name')}：发生被阻止的副作用调用（见详情）。"
                )

        elapsed_ms = int((time.time() - started_at) * 1000)
        if elapsed_ms >= 1500:
            warnings.append(
                f"{plugin_ref.get('name')} - {handler_ref.get('handler_name')}：dry-run 执行耗时 {elapsed_ms}ms。"
            )

        records.append(record)

        if stop_now:
            break

    # Keep return contract (3-tuple), attach extra segments to req for snapshot rendering.
    try:
        setattr(req, "_prompt_preview_extra_user_content_segments", _compact_system_segments(extra_user_segments))
    except Exception:
        pass

    return records, warnings, system_segments


def build_prompt_preview_render_result(
    *,
    umo: str,
    req: ProviderRequest,
    preview_prompt: str,
    contexts_source: str,
    contexts_note: str,
    render_handlers: list[DryRunHandlerRecord],
    render_warnings: list[str],
    rendered_system_prompt_segments: list[SystemPromptSegment] | None = None,
    rendered_extra_user_content_segments: list[SystemPromptSegment] | None = None,
) -> dict[str, Any]:
    rendered_prompt = str(req.prompt or "")
    rendered_system_prompt = str(req.system_prompt or "")

    if not rendered_prompt.strip():
        rendered_prompt = preview_prompt
        render_warnings = list(render_warnings) + [
            "最终 Prompt 为空，已回退为 preview_prompt（预览保证非空；真实运行结果可能不同）。"
        ]

    result: dict[str, Any] = {
        # Backward compatible fields (existing UI reads these)
        "prompt": rendered_prompt,
        "system_prompt": rendered_system_prompt,
        "contexts": {
            "present": bool(req.contexts),
            "source": contexts_source,
            "count": len(req.contexts or []),
            "note": contexts_note,
        },
        # New optional fields (must be JSON-serializable)
        "rendered_prompt": rendered_prompt,
        "rendered_system_prompt": rendered_system_prompt,
        "render_warnings": [str(x) for x in (render_warnings or []) if str(x).strip()],
        "render_executed_handlers": [_serialize_handler_record(r) for r in (render_handlers or [])],
    }

    if rendered_system_prompt_segments is not None:
        segs = _compact_system_segments(list(rendered_system_prompt_segments))
        segs = _merge_same_plugin_segments(segs)
        result["rendered_system_prompt_segments"] = _neutralize_whitespace_segments(segs)

    if rendered_extra_user_content_segments is None:
        rendered_extra_user_content_segments = getattr(req, "_prompt_preview_extra_user_content_segments", None)

    if rendered_extra_user_content_segments is not None:
        segs = _compact_system_segments(list(rendered_extra_user_content_segments))
        segs = _merge_same_plugin_segments(segs)
        result["rendered_extra_user_content_segments"] = _neutralize_whitespace_segments(segs)

    return result