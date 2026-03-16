import datetime as dt
import hashlib
import json
import re
import typing as T
from dataclasses import dataclass, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import UUID

from astrbot import logger
from astrbot.core.config.tool_loop_defaults import DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES

_DEDUP_PREVIEW_LIMIT = 180
_DEDUP_PREVIEW_MIN_LIMIT = 3
_DEDUP_MESSAGE_TEMPLATE = (
    "[tool-result-deduplicated] Tool `{tool_name}` returned unchanged output for "
    "{repeat_total} consecutive calls with the same arguments. Full repeated output "
    "is omitted to reduce context growth. Latest preview: {preview}"
)
_TOOL_ERROR_PREFIX_RE = re.compile(
    r"^(error|err|failed|failure|exception|traceback|错误|异常|失败)\s*[:：\-]?",
    re.IGNORECASE,
)
_TOOL_ERROR_CONTAINS_MARKERS = (
    "traceback (most recent call last)",
    "tool handler parameter mismatch",
    "argument contract violation",
    "missing required tool arguments",
    "no compatible arguments for this tool",
)


def _stable_type_name(value: T.Any) -> str:
    cls = value.__class__
    return f"{cls.__module__}.{cls.__qualname__}"


def _canonicalize_tool_arg_value(
    value: T.Any,
    *,
    _seen: set[int] | None = None,
) -> T.Any:
    if _seen is None:
        _seen = set()

    if value is None or isinstance(value, bool | int | float | str):
        return value

    if isinstance(value, bytes | bytearray | memoryview):
        return {
            "__type__": _stable_type_name(value),
            "hex": bytes(value).hex(),
        }

    if isinstance(value, dt.datetime | dt.date | dt.time):
        return {
            "__type__": _stable_type_name(value),
            "iso": value.isoformat(),
        }

    if isinstance(value, Path):
        return {
            "__type__": _stable_type_name(value),
            "path": str(value),
        }

    if isinstance(value, UUID | Decimal):
        return {
            "__type__": _stable_type_name(value),
            "value": str(value),
        }

    if isinstance(value, Enum):
        return {
            "__type__": _stable_type_name(value),
            "name": value.name,
            "value": _canonicalize_tool_arg_value(value.value, _seen=_seen),
        }

    obj_id = id(value)
    if obj_id in _seen:
        return {
            "__type__": _stable_type_name(value),
            "__recursive__": True,
        }

    added_to_seen = False
    try:
        _seen.add(obj_id)
        added_to_seen = True
        if isinstance(value, dict):
            normalized_items: list[tuple[str, T.Any]] = []
            for key, item in value.items():
                normalized_key = json.dumps(
                    _canonicalize_tool_arg_value(key, _seen=_seen),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                normalized_items.append(
                    (
                        normalized_key,
                        _canonicalize_tool_arg_value(item, _seen=_seen),
                    )
                )
            normalized_items.sort(key=lambda kv: kv[0])
            return dict(normalized_items)

        if isinstance(value, list | tuple):
            return [_canonicalize_tool_arg_value(item, _seen=_seen) for item in value]

        if isinstance(value, set | frozenset):
            normalized_items = [
                _canonicalize_tool_arg_value(item, _seen=_seen) for item in value
            ]
            normalized_items.sort(
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return normalized_items

        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            return {
                "__type__": _stable_type_name(value),
                "value": _canonicalize_tool_arg_value(dumped, _seen=_seen),
            }

        dict_dump = getattr(value, "dict", None)
        if callable(dict_dump):
            dumped = dict_dump()
            return {
                "__type__": _stable_type_name(value),
                "value": _canonicalize_tool_arg_value(dumped, _seen=_seen),
            }

        if is_dataclass(value) and not isinstance(value, type):
            attrs: dict[str, T.Any] = {}
            for key in sorted(vars(value)):
                if key.startswith("_"):
                    continue
                attrs[key] = _canonicalize_tool_arg_value(getattr(value, key), _seen=_seen)
            return {
                "__type__": _stable_type_name(value),
                "attrs": attrs,
            }

        if hasattr(value, "__dict__"):
            attrs = {}
            for key in sorted(vars(value)):
                if key.startswith("_"):
                    continue
                attrs[key] = _canonicalize_tool_arg_value(getattr(value, key), _seen=_seen)
            return {
                "__type__": _stable_type_name(value),
                "attrs": attrs,
            }

        slots = getattr(value, "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        if slots:
            attrs = {}
            for slot_name in sorted(slots):
                if not isinstance(slot_name, str):
                    continue
                if hasattr(value, slot_name):
                    attrs[slot_name] = _canonicalize_tool_arg_value(
                        getattr(value, slot_name),
                        _seen=_seen,
                    )
            return {
                "__type__": _stable_type_name(value),
                "attrs": attrs,
            }

        return {"__type__": _stable_type_name(value)}
    finally:
        if added_to_seen:
            _seen.remove(obj_id)


@dataclass(slots=True)
class ToolResultDedupState:
    result_hash: str
    repeat_count: int = 0


@dataclass(slots=True)
class ToolResultGuardConfig:
    deduplicate_repeated_tool_results: bool
    tool_result_dedup_max_entries: int | None
    tool_error_repeat_guard_threshold: int | None


@dataclass(slots=True)
class GuardedToolResult:
    content: str
    tools_disabled: bool = False
    notice_message: str | None = None


class ToolResultGuard:
    def __init__(self, config: ToolResultGuardConfig) -> None:
        self._config = config
        self._tool_result_dedup: dict[str, ToolResultDedupState] = {}
        self._tool_error_repeat_counts: dict[str, int] = {}
        self._tool_error_repeat_guard_triggered = False

    @property
    def dedup_map(self) -> dict[str, ToolResultDedupState]:
        return self._tool_result_dedup

    @property
    def error_repeat_counts(self) -> dict[str, int]:
        return self._tool_error_repeat_counts

    @property
    def error_repeat_guard_triggered(self) -> bool:
        return self._tool_error_repeat_guard_triggered

    def normalize_tool_args_for_signature(self, tool_args: dict[str, T.Any]) -> str:
        normalized_args = _canonicalize_tool_arg_value(tool_args)
        try:
            return json.dumps(
                normalized_args,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            logger.warning(
                "Failed to normalize tool args for signature, fallback to type-only marker. args_type=%s",
                _stable_type_name(tool_args),
            )
            return json.dumps(
                {
                    "__type__": _stable_type_name(tool_args),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )

    def _build_tool_signature(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, T.Any],
    ) -> str:
        return f"{tool_name}:{self.normalize_tool_args_for_signature(tool_args)}"

    @staticmethod
    def is_tool_error_content(content: str) -> bool:
        normalized = content.strip()
        if not normalized:
            return False

        if _TOOL_ERROR_PREFIX_RE.match(normalized):
            return True

        lowered = normalized.lower()
        return any(marker in lowered for marker in _TOOL_ERROR_CONTAINS_MARKERS)

    @staticmethod
    def _compact_tool_result_preview(
        content: str,
        limit: int = _DEDUP_PREVIEW_LIMIT,
    ) -> str:
        normalized = " ".join(content.strip().split())
        if len(normalized) <= limit:
            return normalized
        if limit <= _DEDUP_PREVIEW_MIN_LIMIT:
            return normalized[:limit]
        return f"{normalized[: limit - _DEDUP_PREVIEW_MIN_LIMIT]}..."

    def _prune_tool_result_dedup_if_needed(self) -> None:
        max_entries = self._config.tool_result_dedup_max_entries
        if max_entries is None:
            return

        while len(self._tool_result_dedup) > max_entries:
            try:
                oldest_key = next(iter(self._tool_result_dedup))
            except StopIteration:
                break
            self._tool_result_dedup.pop(oldest_key, None)

    def _prune_tool_error_repeat_counts_if_needed(self) -> None:
        max_entries = self._config.tool_result_dedup_max_entries
        if max_entries is None:
            max_entries = DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES

        while len(self._tool_error_repeat_counts) > max_entries:
            try:
                oldest_key = next(iter(self._tool_error_repeat_counts))
            except StopIteration:
                break
            self._tool_error_repeat_counts.pop(oldest_key, None)

    def deduplicate_tool_result_content(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, T.Any],
        content: str,
    ) -> str:
        if not content:
            return content

        signature = self._build_tool_signature(tool_name=tool_name, tool_args=tool_args)
        content_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()

        state = self._tool_result_dedup.get(signature)
        if state is None or state.result_hash != content_hash:
            self._tool_result_dedup[signature] = ToolResultDedupState(
                result_hash=content_hash,
                repeat_count=0,
            )
            self._prune_tool_result_dedup_if_needed()
            return content

        state.repeat_count += 1
        repeat_total = state.repeat_count + 1
        preview = self._compact_tool_result_preview(content, limit=_DEDUP_PREVIEW_LIMIT)
        logger.info(
            "Deduplicated repeated tool output: tool=%s repeats=%s",
            tool_name,
            repeat_total,
        )
        return _DEDUP_MESSAGE_TEMPLATE.format(
            tool_name=tool_name,
            repeat_total=repeat_total,
            preview=preview,
        )

    def _check_and_apply_tool_error_repeat_guard(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, T.Any],
        content: str,
    ) -> GuardedToolResult:
        if self._tool_error_repeat_guard_triggered:
            return GuardedToolResult(content=content)

        threshold = self._config.tool_error_repeat_guard_threshold
        if threshold is None:
            return GuardedToolResult(content=content)

        signature = self._build_tool_signature(tool_name=tool_name, tool_args=tool_args)
        if not self.is_tool_error_content(content):
            self._tool_error_repeat_counts.pop(signature, None)
            return GuardedToolResult(content=content)

        repeat_count = self._tool_error_repeat_counts.get(signature, 0) + 1
        self._tool_error_repeat_counts[signature] = repeat_count
        self._prune_tool_error_repeat_counts_if_needed()
        if repeat_count < threshold:
            return GuardedToolResult(content=content)

        self._tool_error_repeat_guard_triggered = True
        self._tool_error_repeat_counts.clear()
        preview = self._compact_tool_result_preview(content, limit=_DEDUP_PREVIEW_LIMIT)
        logger.warning(
            "Tool error repeat guard activated: tool=%s repeats=%s",
            tool_name,
            repeat_count,
        )

        return GuardedToolResult(
            content=content,
            tools_disabled=True,
            notice_message=(
                "[SYSTEM NOTICE] Tool call error loop detected. "
                f"Tool `{tool_name}` with the same arguments has failed "
                f"{repeat_count} times consecutively. "
                "To prevent context bloat and wasted tool calls, all tools are now disabled for this run. "
                "Do not call tools again; provide the best possible answer to the user based on current information. "
                f"Latest error preview: {preview}"
            ),
        )

    def process(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, T.Any],
        content: str,
    ) -> GuardedToolResult:
        guard_result = self._check_and_apply_tool_error_repeat_guard(
            tool_name=tool_name,
            tool_args=tool_args,
            content=content,
        )
        output = guard_result.content

        if self._config.deduplicate_repeated_tool_results:
            output = self.deduplicate_tool_result_content(
                tool_name=tool_name,
                tool_args=tool_args,
                content=output,
            )

        guard_result.content = output
        return guard_result
