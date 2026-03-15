import asyncio
import copy
import datetime as dt
import hashlib
import json
import re
import sys
import time
import traceback
import typing as T
from dataclasses import dataclass, field, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import UUID

from mcp.types import (
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    TextContent,
    TextResourceContents,
)

from astrbot import logger
from astrbot.core.agent.message import ImageURLPart, TextPart, ThinkPart
from astrbot.core.agent.tool import ToolSet
from astrbot.core.agent.tool_image_cache import tool_image_cache
from astrbot.core.message.components import Json
from astrbot.core.message.message_event_result import (
    MessageChain,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
    ToolCallsResult,
)
from astrbot.core.provider.provider import Provider

from ..context.compressor import ContextCompressor
from ..context.config import ContextConfig
from ..context.manager import ContextManager
from ..context.token_counter import TokenCounter
from ..hooks import BaseAgentRunHooks
from ..message import AssistantMessageSegment, Message, ToolCallMessageSegment
from ..response import AgentResponseData, AgentStats
from ..run_context import ContextWrapper, TContext
from ..tool_executor import BaseFunctionToolExecutor
from .base import AgentResponse, AgentState, BaseAgentRunner

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


@dataclass(slots=True)
class _HandleFunctionToolsResult:
    kind: T.Literal["message_chain", "tool_call_result_blocks", "cached_image"]
    message_chain: MessageChain | None = None
    tool_call_result_blocks: list[ToolCallMessageSegment] | None = None
    cached_image: T.Any = None

    @classmethod
    def from_message_chain(cls, chain: MessageChain) -> "_HandleFunctionToolsResult":
        return cls(kind="message_chain", message_chain=chain)

    @classmethod
    def from_tool_call_result_blocks(
        cls, blocks: list[ToolCallMessageSegment]
    ) -> "_HandleFunctionToolsResult":
        return cls(kind="tool_call_result_blocks", tool_call_result_blocks=blocks)

    @classmethod
    def from_cached_image(cls, image: T.Any) -> "_HandleFunctionToolsResult":
        return cls(kind="cached_image", cached_image=image)


@dataclass(slots=True)
class FollowUpTicket:
    seq: int
    text: str
    consumed: bool = False
    resolved: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(slots=True)
class _ToolResultDedupState:
    result_hash: str
    repeat_count: int = 0


_DEDUP_PREVIEW_LIMIT = 180
_DEDUP_PREVIEW_MIN_LIMIT = 3
_DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES = 1024
_DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD = 8
_DEDUP_MESSAGE_TEMPLATE = (
    "[tool-result-deduplicated] Tool `{tool_name}` returned unchanged output for "
    "{repeat_total} consecutive calls with the same arguments. Full repeated output "
    "is omitted to reduce context growth. Latest preview: {preview}"
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
    _seen.add(obj_id)
    try:
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
            return {k: v for k, v in normalized_items}

        if isinstance(value, list | tuple):
            return [
                _canonicalize_tool_arg_value(item, _seen=_seen)
                for item in value
            ]

        if isinstance(value, set | frozenset):
            normalized_items = [
                _canonicalize_tool_arg_value(item, _seen=_seen)
                for item in value
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
                attrs[key] = _canonicalize_tool_arg_value(
                    getattr(value, key),
                    _seen=_seen,
                )
            return {
                "__type__": _stable_type_name(value),
                "attrs": attrs,
            }

        if hasattr(value, "__dict__"):
            attrs: dict[str, T.Any] = {}
            for key in sorted(vars(value)):
                if key.startswith("_"):
                    continue
                attrs[key] = _canonicalize_tool_arg_value(
                    getattr(value, key),
                    _seen=_seen,
                )
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
        _seen.remove(obj_id)


class ToolLoopAgentRunner(BaseAgentRunner[TContext]):
    @staticmethod
    def _normalize_tool_param_name_for_matching(name: str) -> str:
        """Normalize common arg-name variants (camelCase/kebab-case) to snake_case."""
        normalized = name.replace("-", "_")
        normalized = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", normalized)
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
        return normalized.lower()

    @staticmethod
    def _is_missing_like(value: T.Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False

    @staticmethod
    def _schema_type_tokens(schema: dict[str, T.Any] | None) -> set[str]:
        if not isinstance(schema, dict):
            return set()
        type_val = schema.get("type")
        if isinstance(type_val, str):
            return {type_val}
        if isinstance(type_val, list):
            return {str(t) for t in type_val if isinstance(t, str)}
        return set()

    @classmethod
    def _coerce_tool_value_by_schema(
        cls,
        *,
        value: T.Any,
        schema: dict[str, T.Any] | None,
    ) -> T.Any:
        tokens = cls._schema_type_tokens(schema)
        if not tokens:
            return value

        if "boolean" in tokens:
            if isinstance(value, bool):
                return value
            if isinstance(value, int | float):
                return bool(value)
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "y", "on"}:
                    return True
                if lowered in {"false", "0", "no", "n", "off", ""}:
                    return False

        if "integer" in tokens:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float) and value.is_integer():
                return int(value)
            if isinstance(value, str):
                stripped = value.strip()
                if re.fullmatch(r"[+-]?\d+", stripped):
                    try:
                        return int(stripped)
                    except ValueError:
                        pass

        if "number" in tokens:
            if isinstance(value, int | float) and not isinstance(value, bool):
                return value
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    try:
                        return float(stripped)
                    except ValueError:
                        pass

        if "string" in tokens and not isinstance(value, str):
            if isinstance(value, bool | int | float):
                return str(value)

        return value

    @classmethod
    def _coerce_tool_params_by_schema(
        cls,
        *,
        params: dict[str, T.Any],
        params_schema: dict[str, T.Any] | None,
    ) -> tuple[dict[str, T.Any], dict[str, tuple[T.Any, T.Any]]]:
        if not isinstance(params_schema, dict):
            return params, {}
        properties = params_schema.get("properties")
        if not isinstance(properties, dict):
            return params, {}

        coerced_params = dict(params)
        changed: dict[str, tuple[T.Any, T.Any]] = {}
        for key, value in params.items():
            schema = properties.get(key)
            if not isinstance(schema, dict):
                continue
            coerced = cls._coerce_tool_value_by_schema(value=value, schema=schema)
            if coerced is not value and coerced != value:
                changed[key] = (value, coerced)
                coerced_params[key] = coerced
        return coerced_params, changed

    def _get_persona_custom_error_message(self) -> str | None:
        """Read persona-level custom error message from event extras when available."""
        event = getattr(self.run_context.context, "event", None)
        return extract_persona_custom_error_message_from_event(event)

    @override
    async def reset(
        self,
        provider: Provider,
        request: ProviderRequest,
        run_context: ContextWrapper[TContext],
        tool_executor: BaseFunctionToolExecutor[TContext],
        agent_hooks: BaseAgentRunHooks[TContext],
        streaming: bool = False,
        # enforce max turns, will discard older turns when exceeded BEFORE compression
        # -1 means no limit
        enforce_max_turns: int = -1,
        # llm compressor
        llm_compress_instruction: str | None = None,
        llm_compress_keep_recent: int = 0,
        llm_compress_provider: Provider | None = None,
        # truncate by turns compressor
        truncate_turns: int = 1,
        # customize
        custom_token_counter: TokenCounter | None = None,
        custom_compressor: ContextCompressor | None = None,
        tool_schema_mode: str | None = "full",
        fallback_providers: list[Provider] | None = None,
        deduplicate_repeated_tool_results: bool = True,
        tool_result_dedup_max_entries: int | None = _DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES,
        tool_error_repeat_guard_threshold: int | None = _DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD,
        **kwargs: T.Any,
    ) -> None:
        self.req = request
        self.streaming = streaming
        self.enforce_max_turns = enforce_max_turns
        self.llm_compress_instruction = llm_compress_instruction
        self.llm_compress_keep_recent = llm_compress_keep_recent
        self.llm_compress_provider = llm_compress_provider
        self.truncate_turns = truncate_turns
        self.custom_token_counter = custom_token_counter
        self.custom_compressor = custom_compressor
        # we will do compress when:
        # 1. before requesting LLM
        # TODO: 2. after LLM output a tool call
        self.context_config = ContextConfig(
            # <=0 will never do compress
            max_context_tokens=provider.provider_config.get("max_context_tokens", 0),
            # enforce max turns before compression
            enforce_max_turns=self.enforce_max_turns,
            truncate_turns=self.truncate_turns,
            llm_compress_instruction=self.llm_compress_instruction,
            llm_compress_keep_recent=self.llm_compress_keep_recent,
            llm_compress_provider=self.llm_compress_provider,
            custom_token_counter=self.custom_token_counter,
            custom_compressor=self.custom_compressor,
        )
        self.context_manager = ContextManager(self.context_config)

        self.provider = provider
        self.fallback_providers: list[Provider] = []
        seen_provider_ids: set[str] = {str(provider.provider_config.get("id", ""))}
        for fallback_provider in fallback_providers or []:
            fallback_id = str(fallback_provider.provider_config.get("id", ""))
            if fallback_provider is provider:
                continue
            if fallback_id and fallback_id in seen_provider_ids:
                continue
            self.fallback_providers.append(fallback_provider)
            if fallback_id:
                seen_provider_ids.add(fallback_id)
        self.final_llm_resp = None
        self._state = AgentState.IDLE
        self.tool_executor = tool_executor
        self.agent_hooks = agent_hooks
        self.run_context = run_context
        self._stop_requested = False
        self._aborted = False
        self._pending_follow_ups: list[FollowUpTicket] = []
        self._follow_up_seq = 0
        # This cache tracks repeated tool results. Bound it to keep long-running
        # sessions from accumulating stale signatures indefinitely.
        self._tool_result_dedup: dict[str, _ToolResultDedupState] = {}
        self._deduplicate_repeated_tool_results = deduplicate_repeated_tool_results
        self._tool_result_dedup_max_entries = (
            self._normalize_tool_result_dedup_max_entries(
                tool_result_dedup_max_entries
            )
        )
        self._tool_error_repeat_guard_threshold = (
            self._normalize_tool_error_repeat_guard_threshold(
                tool_error_repeat_guard_threshold
            )
        )
        self._tool_error_repeat_counts: dict[str, int] = {}
        self._tool_error_repeat_guard_triggered = False

        # These two are used for tool schema mode handling
        # We now have two modes:
        # - "full": use full tool schema for LLM calls, default.
        # - "skills_like": use light tool schema for LLM calls, and re-query with param-only schema when needed.
        #   Light tool schema does not include tool parameters.
        #   This can reduce token usage when tools have large descriptions.
        # See #4681
        self.tool_schema_mode = tool_schema_mode
        self._tool_schema_param_set = None
        self._skill_like_raw_tool_set = None
        if tool_schema_mode == "skills_like":
            tool_set = self.req.func_tool
            if not tool_set:
                return
            self._skill_like_raw_tool_set = tool_set
            light_set = tool_set.get_light_tool_set()
            self._tool_schema_param_set = tool_set.get_param_only_tool_set()
            # MODIFIE the req.func_tool to use light tool schemas
            self.req.func_tool = light_set

        messages = []
        # append existing messages in the run context
        for msg in request.contexts:
            m = Message.model_validate(msg)
            if isinstance(msg, dict) and msg.get("_no_save"):
                m._no_save = True
            messages.append(m)
        if request.prompt is not None:
            m = await request.assemble_context()
            messages.append(Message.model_validate(m))
        if request.system_prompt:
            messages.insert(
                0,
                Message(role="system", content=request.system_prompt),
            )
        self.run_context.messages = messages

        self.stats = AgentStats()
        self.stats.start_time = time.time()

    async def _iter_llm_responses(
        self, *, include_model: bool = True
    ) -> T.AsyncGenerator[LLMResponse, None]:
        """Yields chunks *and* a final LLMResponse."""
        payload = {
            "contexts": self.run_context.messages,  # list[Message]
            "func_tool": self.req.func_tool,
            "session_id": self.req.session_id,
            "extra_user_content_parts": self.req.extra_user_content_parts,  # list[ContentPart]
        }
        if include_model:
            # For primary provider we keep explicit model selection if provided.
            payload["model"] = self.req.model
        if self.streaming:
            stream = self.provider.text_chat_stream(**payload)
            async for resp in stream:  # type: ignore
                yield resp
        else:
            yield await self.provider.text_chat(**payload)

    async def _iter_llm_responses_with_fallback(
        self,
    ) -> T.AsyncGenerator[LLMResponse, None]:
        """Wrap _iter_llm_responses with provider fallback handling."""
        candidates = [self.provider, *self.fallback_providers]
        total_candidates = len(candidates)
        last_exception: Exception | None = None
        last_err_response: LLMResponse | None = None

        for idx, candidate in enumerate(candidates):
            candidate_id = candidate.provider_config.get("id", "<unknown>")
            is_last_candidate = idx == total_candidates - 1
            if idx > 0:
                logger.warning(
                    "Switched from %s to fallback chat provider: %s",
                    self.provider.provider_config.get("id", "<unknown>"),
                    candidate_id,
                )
            self.provider = candidate
            has_stream_output = False
            try:
                async for resp in self._iter_llm_responses(include_model=idx == 0):
                    if resp.is_chunk:
                        has_stream_output = True
                        yield resp
                        continue

                    if (
                        resp.role == "err"
                        and not has_stream_output
                        and (not is_last_candidate)
                    ):
                        last_err_response = resp
                        logger.warning(
                            "Chat Model %s returns error response, trying fallback to next provider.",
                            candidate_id,
                        )
                        break

                    yield resp
                    return

                if has_stream_output:
                    return
            except Exception as exc:  # noqa: BLE001
                last_exception = exc
                logger.warning(
                    "Chat Model %s request error: %s",
                    candidate_id,
                    exc,
                    exc_info=True,
                )
                continue

        if last_err_response:
            yield last_err_response
            return
        if last_exception:
            yield LLMResponse(
                role="err",
                completion_text=(
                    "All chat models failed: "
                    f"{type(last_exception).__name__}: {last_exception}"
                ),
            )
            return
        yield LLMResponse(
            role="err",
            completion_text="All available chat models are unavailable.",
        )

    def _simple_print_message_role(self, tag: str = ""):
        roles = []
        for message in self.run_context.messages:
            roles.append(message.role)
        logger.debug(f"{tag} RunCtx.messages -> [{len(roles)}] {','.join(roles)}")

    def follow_up(
        self,
        *,
        message_text: str,
    ) -> FollowUpTicket | None:
        """Queue a follow-up message for the next tool result."""
        if self.done():
            return None
        text = (message_text or "").strip()
        if not text:
            return None
        ticket = FollowUpTicket(seq=self._follow_up_seq, text=text)
        self._follow_up_seq += 1
        self._pending_follow_ups.append(ticket)
        return ticket

    def _resolve_unconsumed_follow_ups(self) -> None:
        if not self._pending_follow_ups:
            return
        follow_ups = self._pending_follow_ups
        self._pending_follow_ups = []
        for ticket in follow_ups:
            ticket.resolved.set()

    def _consume_follow_up_notice(self) -> str:
        if not self._pending_follow_ups:
            return ""
        follow_ups = self._pending_follow_ups
        self._pending_follow_ups = []
        for ticket in follow_ups:
            ticket.consumed = True
            ticket.resolved.set()
        follow_up_lines = "\n".join(
            f"{idx}. {ticket.text}" for idx, ticket in enumerate(follow_ups, start=1)
        )
        return (
            "\n\n[SYSTEM NOTICE] User sent follow-up messages while tool execution "
            "was in progress. Prioritize these follow-up instructions in your next "
            "actions. In your very next action, briefly acknowledge to the user "
            "that their follow-up message(s) were received before continuing.\n"
            f"{follow_up_lines}"
        )

    def _merge_follow_up_notice(self, content: str) -> str:
        notice = self._consume_follow_up_notice()
        if not notice:
            return content
        return f"{content}{notice}"

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

    @staticmethod
    def _normalize_tool_result_dedup_max_entries(
        max_entries: int | None,
    ) -> int | None:
        if max_entries is None:
            return None
        if isinstance(max_entries, bool):
            logger.warning(
                "Invalid tool_result_dedup_max_entries=%s, fallback to %s.",
                max_entries,
                _DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES,
            )
            return _DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES
        try:
            normalized = int(max_entries)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid tool_result_dedup_max_entries=%s, fallback to %s.",
                max_entries,
                _DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES,
            )
            return _DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES
        if normalized <= 0:
            return None
        return normalized

    @staticmethod
    def _normalize_tool_error_repeat_guard_threshold(
        threshold: int | None,
    ) -> int | None:
        if threshold is None:
            return None
        if isinstance(threshold, bool):
            logger.warning(
                "Invalid tool_error_repeat_guard_threshold=%s, fallback to %s.",
                threshold,
                _DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD,
            )
            return _DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD
        try:
            normalized = int(threshold)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid tool_error_repeat_guard_threshold=%s, fallback to %s.",
                threshold,
                _DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD,
            )
            return _DEFAULT_TOOL_ERROR_REPEAT_GUARD_THRESHOLD
        if normalized <= 0:
            return None
        return normalized

    @staticmethod
    def _normalize_tool_args_for_signature(tool_args: dict[str, T.Any]) -> str:
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
        return f"{tool_name}:{self._normalize_tool_args_for_signature(tool_args=tool_args)}"

    @staticmethod
    def _is_tool_error_content(content: str) -> bool:
        normalized = content.strip().lower()
        return normalized.startswith("error:")

    def _prune_tool_result_dedup_if_needed(self) -> None:
        """Bound dedup cache size for long-running sessions."""
        max_entries = self._tool_result_dedup_max_entries
        if max_entries is None:
            return

        while len(self._tool_result_dedup) > max_entries:
            try:
                oldest_key = next(iter(self._tool_result_dedup))
            except StopIteration:
                break
            self._tool_result_dedup.pop(oldest_key, None)

    def _prune_tool_error_repeat_counts_if_needed(self) -> None:
        max_entries = self._tool_result_dedup_max_entries
        if max_entries is None:
            max_entries = _DEFAULT_TOOL_RESULT_DEDUP_MAX_ENTRIES

        while len(self._tool_error_repeat_counts) > max_entries:
            try:
                oldest_key = next(iter(self._tool_error_repeat_counts))
            except StopIteration:
                break
            self._tool_error_repeat_counts.pop(oldest_key, None)

    def _check_and_apply_tool_error_repeat_guard(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, T.Any],
        content: str,
    ) -> None:
        if self._tool_error_repeat_guard_triggered:
            return
        threshold = self._tool_error_repeat_guard_threshold
        if threshold is None:
            return

        signature = self._build_tool_signature(tool_name=tool_name, tool_args=tool_args)
        if not self._is_tool_error_content(content):
            self._tool_error_repeat_counts.pop(signature, None)
            return

        repeat_count = self._tool_error_repeat_counts.get(signature, 0) + 1
        self._tool_error_repeat_counts[signature] = repeat_count
        self._prune_tool_error_repeat_counts_if_needed()
        if repeat_count < threshold:
            return

        self._tool_error_repeat_guard_triggered = True
        self._tool_error_repeat_counts.clear()
        if self.req:
            self.req.func_tool = None

        preview = self._compact_tool_result_preview(content, limit=_DEDUP_PREVIEW_LIMIT)
        logger.warning(
            "Tool error repeat guard activated: tool=%s repeats=%s",
            tool_name,
            repeat_count,
        )
        self.run_context.messages.append(
            Message(
                role="user",
                content=(
                    "[SYSTEM NOTICE] Tool call error loop detected. "
                    f"Tool `{tool_name}` with the same arguments has failed "
                    f"{repeat_count} times consecutively. "
                    "To prevent context bloat and wasted tool calls, all tools are now disabled for this run. "
                    "Do not call tools again; provide the best possible answer to the user based on current information. "
                    f"Latest error preview: {preview}"
                ),
            )
        )

    def _deduplicate_tool_result_content(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, T.Any],
        content: str,
    ) -> str:
        if not content:
            return content

        signature = self._build_tool_signature(tool_name=tool_name, tool_args=tool_args)
        content_hash = hashlib.sha256(
            content.encode("utf-8", errors="replace")
        ).hexdigest()

        state = self._tool_result_dedup.get(signature)
        if state is None or state.result_hash != content_hash:
            self._tool_result_dedup[signature] = _ToolResultDedupState(
                result_hash=content_hash,
                repeat_count=0,
            )
            self._prune_tool_result_dedup_if_needed()
            return content

        state.repeat_count += 1
        repeat_total = state.repeat_count + 1
        preview = self._compact_tool_result_preview(
            content,
            limit=_DEDUP_PREVIEW_LIMIT,
        )
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

    @staticmethod
    def _find_missing_required_tool_params(
        *,
        tool: T.Any,
        provided_params: dict[str, T.Any],
    ) -> list[str]:
        params_schema = getattr(tool, "parameters", None)
        if not isinstance(params_schema, dict):
            return []
        required = params_schema.get("required")
        if not isinstance(required, list):
            return []

        missing: list[str] = []
        for field_name in required:
            if not isinstance(field_name, str):
                continue
            if field_name not in provided_params:
                missing.append(field_name)
                continue
            value = provided_params.get(field_name)
            if ToolLoopAgentRunner._is_missing_like(value):
                missing.append(field_name)
        return missing

    @staticmethod
    def _validate_anyof_oneof_contract(
        *,
        tool: T.Any,
        provided_params: dict[str, T.Any],
    ) -> str | None:
        params_schema = getattr(tool, "parameters", None)
        if not isinstance(params_schema, dict):
            return None

        def _extract_required_groups(key: str) -> list[list[str]]:
            groups_raw = params_schema.get(key)
            if not isinstance(groups_raw, list):
                return []
            groups: list[list[str]] = []
            for item in groups_raw:
                if not isinstance(item, dict):
                    continue
                req = item.get("required")
                if not isinstance(req, list):
                    continue
                normalized = [f for f in req if isinstance(f, str) and f]
                if normalized:
                    groups.append(normalized)
            return groups

        def _is_group_satisfied(group: list[str]) -> bool:
            for field in group:
                if field not in provided_params:
                    return False
                if ToolLoopAgentRunner._is_missing_like(provided_params.get(field)):
                    return False
            return True

        anyof_groups = _extract_required_groups("anyOf")
        if anyof_groups and not any(_is_group_satisfied(g) for g in anyof_groups):
            group_text = " or ".join(
                "[" + ", ".join(group) + "]" for group in anyof_groups
            )
            return (
                "error: Argument contract violation (anyOf). "
                f"At least one argument group is required: {group_text}."
            )

        oneof_groups = _extract_required_groups("oneOf")
        if oneof_groups:
            satisfied = sum(1 for g in oneof_groups if _is_group_satisfied(g))
            if satisfied != 1:
                group_text = " | ".join(
                    "[" + ", ".join(group) + "]" for group in oneof_groups
                )
                return (
                    "error: Argument contract violation (oneOf). "
                    "Exactly one argument group must be provided. "
                    f"Available groups: {group_text}."
                )

        return None

    @override
    async def step(self):
        """Process a single step of the agent.
        This method should return the result of the step.
        """
        if not self.req:
            raise ValueError("Request is not set. Please call reset() first.")

        if self._state == AgentState.IDLE:
            try:
                await self.agent_hooks.on_agent_begin(self.run_context)
            except Exception as e:
                logger.error(f"Error in on_agent_begin hook: {e}", exc_info=True)

        # 开始处理，转换到运行状态
        self._transition_state(AgentState.RUNNING)
        llm_resp_result = None

        # do truncate and compress
        token_usage = self.req.conversation.token_usage if self.req.conversation else 0
        self._simple_print_message_role("[BefCompact]")
        self.run_context.messages = await self.context_manager.process(
            self.run_context.messages, trusted_token_usage=token_usage
        )
        self._simple_print_message_role("[AftCompact]")

        async for llm_response in self._iter_llm_responses_with_fallback():
            if llm_response.is_chunk:
                # update ttft
                if self.stats.time_to_first_token == 0:
                    self.stats.time_to_first_token = time.time() - self.stats.start_time

                if llm_response.result_chain:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(chain=llm_response.result_chain),
                    )
                elif llm_response.completion_text:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain().message(llm_response.completion_text),
                        ),
                    )
                elif llm_response.reasoning_content:
                    yield AgentResponse(
                        type="streaming_delta",
                        data=AgentResponseData(
                            chain=MessageChain(type="reasoning").message(
                                llm_response.reasoning_content,
                            ),
                        ),
                    )
                if self._stop_requested:
                    llm_resp_result = LLMResponse(
                        role="assistant",
                        completion_text="[SYSTEM: User actively interrupted the response generation. Partial output before interruption is preserved.]",
                        reasoning_content=llm_response.reasoning_content,
                        reasoning_signature=llm_response.reasoning_signature,
                    )
                    break
                continue
            llm_resp_result = llm_response

            if not llm_response.is_chunk and llm_response.usage:
                # only count the token usage of the final response for computation purpose
                self.stats.token_usage += llm_response.usage
                if self.req.conversation:
                    self.req.conversation.token_usage = llm_response.usage.total
            break  # got final response

        if not llm_resp_result:
            if self._stop_requested:
                llm_resp_result = LLMResponse(role="assistant", completion_text="")
            else:
                return

        if self._stop_requested:
            logger.info("Agent execution was requested to stop by user.")
            llm_resp = llm_resp_result
            if llm_resp.role != "assistant":
                llm_resp = LLMResponse(
                    role="assistant",
                    completion_text="[SYSTEM: User actively interrupted the response generation. Partial output before interruption is preserved.]",
                )
            self.final_llm_resp = llm_resp
            self._aborted = True
            self._transition_state(AgentState.DONE)
            self.stats.end_time = time.time()

            parts = []
            if llm_resp.reasoning_content or llm_resp.reasoning_signature:
                parts.append(
                    ThinkPart(
                        think=llm_resp.reasoning_content,
                        encrypted=llm_resp.reasoning_signature,
                    )
                )
            if llm_resp.completion_text:
                parts.append(TextPart(text=llm_resp.completion_text))
            if parts:
                self.run_context.messages.append(
                    Message(role="assistant", content=parts)
                )

            try:
                await self.agent_hooks.on_agent_done(self.run_context, llm_resp)
            except Exception as e:
                logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)

            yield AgentResponse(
                type="aborted",
                data=AgentResponseData(chain=MessageChain(type="aborted")),
            )
            self._resolve_unconsumed_follow_ups()
            return

        # 处理 LLM 响应
        llm_resp = llm_resp_result

        if llm_resp.role == "err":
            # 如果 LLM 响应错误，转换到错误状态
            self.final_llm_resp = llm_resp
            self.stats.end_time = time.time()
            self._transition_state(AgentState.ERROR)
            self._resolve_unconsumed_follow_ups()
            custom_error_message = self._get_persona_custom_error_message()
            error_text = custom_error_message or (
                f"LLM 响应错误: {llm_resp.completion_text or '未知错误'}"
            )
            yield AgentResponse(
                type="err",
                data=AgentResponseData(
                    chain=MessageChain().message(error_text),
                ),
            )
            return

        if not llm_resp.tools_call_name:
            # 如果没有工具调用，转换到完成状态
            self.final_llm_resp = llm_resp
            self._transition_state(AgentState.DONE)
            self.stats.end_time = time.time()

            # record the final assistant message
            parts = []
            if llm_resp.reasoning_content or llm_resp.reasoning_signature:
                parts.append(
                    ThinkPart(
                        think=llm_resp.reasoning_content,
                        encrypted=llm_resp.reasoning_signature,
                    )
                )
            if llm_resp.completion_text:
                parts.append(TextPart(text=llm_resp.completion_text))
            if len(parts) == 0:
                logger.warning(
                    "LLM returned empty assistant message with no tool calls."
                )
            self.run_context.messages.append(Message(role="assistant", content=parts))

            # call the on_agent_done hook
            try:
                await self.agent_hooks.on_agent_done(self.run_context, llm_resp)
            except Exception as e:
                logger.error(f"Error in on_agent_done hook: {e}", exc_info=True)
            self._resolve_unconsumed_follow_ups()

        # 返回 LLM 结果
        if llm_resp.result_chain:
            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(chain=llm_resp.result_chain),
            )
        elif llm_resp.completion_text:
            yield AgentResponse(
                type="llm_result",
                data=AgentResponseData(
                    chain=MessageChain().message(llm_resp.completion_text),
                ),
            )

        # 如果有工具调用，还需处理工具调用
        if llm_resp.tools_call_name:
            if self.tool_schema_mode == "skills_like":
                llm_resp, _ = await self._resolve_tool_exec(llm_resp)

            tool_call_result_blocks = []
            cached_images = []  # Collect cached images for LLM visibility
            async for result in self._handle_function_tools(self.req, llm_resp):
                if result.kind == "tool_call_result_blocks":
                    if result.tool_call_result_blocks is not None:
                        tool_call_result_blocks = result.tool_call_result_blocks
                elif result.kind == "cached_image":
                    if result.cached_image is not None:
                        # Collect cached image info
                        cached_images.append(result.cached_image)
                elif result.kind == "message_chain":
                    chain = result.message_chain
                    if chain is None or chain.type is None:
                        # should not happen
                        continue
                    if chain.type == "tool_direct_result":
                        ar_type = "tool_call_result"
                    else:
                        ar_type = chain.type
                    yield AgentResponse(
                        type=ar_type,
                        data=AgentResponseData(chain=chain),
                    )

            # 将结果添加到上下文中
            parts = []
            if llm_resp.reasoning_content or llm_resp.reasoning_signature:
                parts.append(
                    ThinkPart(
                        think=llm_resp.reasoning_content,
                        encrypted=llm_resp.reasoning_signature,
                    )
                )
            if llm_resp.completion_text:
                parts.append(TextPart(text=llm_resp.completion_text))
            if len(parts) == 0:
                parts = None
            tool_calls_result = ToolCallsResult(
                tool_calls_info=AssistantMessageSegment(
                    tool_calls=llm_resp.to_openai_to_calls_model(),
                    content=parts,
                ),
                tool_calls_result=tool_call_result_blocks,
            )
            # record the assistant message with tool calls
            self.run_context.messages.extend(
                tool_calls_result.to_openai_messages_model()
            )

            # If there are cached images and the model supports image input,
            # append a user message with images so LLM can see them
            if cached_images:
                modalities = self.provider.provider_config.get("modalities", [])
                supports_image = "image" in modalities
                if supports_image:
                    # Build user message with images for LLM to review
                    image_parts = []
                    for cached_img in cached_images:
                        img_data = tool_image_cache.get_image_base64_by_path(
                            cached_img.file_path, cached_img.mime_type
                        )
                        if img_data:
                            base64_data, mime_type = img_data
                            image_parts.append(
                                TextPart(
                                    text=f"[Image from tool '{cached_img.tool_name}', path='{cached_img.file_path}']"
                                )
                            )
                            image_parts.append(
                                ImageURLPart(
                                    image_url=ImageURLPart.ImageURL(
                                        url=f"data:{mime_type};base64,{base64_data}",
                                        id=cached_img.file_path,
                                    )
                                )
                            )
                    if image_parts:
                        self.run_context.messages.append(
                            Message(role="user", content=image_parts)
                        )
                        logger.debug(
                            f"Appended {len(cached_images)} cached image(s) to context for LLM review"
                        )

            self.req.append_tool_calls_result(tool_calls_result)

    async def step_until_done(
        self, max_step: int
    ) -> T.AsyncGenerator[AgentResponse, None]:
        """Process steps until the agent is done."""
        step_count = 0
        while not self.done() and step_count < max_step:
            step_count += 1
            async for resp in self.step():
                yield resp

        #  如果循环结束了但是 agent 还没有完成，说明是达到了 max_step
        if not self.done():
            logger.warning(
                f"Agent reached max steps ({max_step}), forcing a final response."
            )
            # 拔掉所有工具
            if self.req:
                self.req.func_tool = None
            # 注入提示词
            self.run_context.messages.append(
                Message(
                    role="user",
                    content="工具调用次数已达到上限，请停止使用工具，并根据已经收集到的信息，对你的任务和发现进行总结，然后直接回复用户。",
                )
            )
            # 再执行最后一步
            async for resp in self.step():
                yield resp

    async def _handle_function_tools(
        self,
        req: ProviderRequest,
        llm_response: LLMResponse,
    ) -> T.AsyncGenerator[_HandleFunctionToolsResult, None]:
        """处理函数工具调用。"""
        tool_call_result_blocks: list[ToolCallMessageSegment] = []
        logger.info(f"Agent 使用工具: {llm_response.tools_call_name}")

        def _append_tool_call_result(
            tool_call_id: str,
            content: str,
            *,
            tool_name: str | None = None,
            tool_args: dict[str, T.Any] | None = None,
        ) -> None:
            output = content
            if tool_name:
                self._check_and_apply_tool_error_repeat_guard(
                    tool_name=tool_name,
                    tool_args=tool_args or {},
                    content=content,
                )
            if self._deduplicate_repeated_tool_results and tool_name:
                output = self._deduplicate_tool_result_content(
                    tool_name=tool_name,
                    tool_args=tool_args or {},
                    content=content,
                )
            tool_call_result_blocks.append(
                ToolCallMessageSegment(
                    role="tool",
                    tool_call_id=tool_call_id,
                    content=self._merge_follow_up_notice(output),
                ),
            )

        # 执行函数调用
        for func_tool_name, func_tool_args, func_tool_id in zip(
            llm_response.tools_call_name,
            llm_response.tools_call_args,
            llm_response.tools_call_ids,
        ):
            yield _HandleFunctionToolsResult.from_message_chain(
                MessageChain(
                    type="tool_call",
                    chain=[
                        Json(
                            data={
                                "id": func_tool_id,
                                "name": func_tool_name,
                                "args": func_tool_args,
                                "ts": time.time(),
                            }
                        )
                    ],
                )
            )
            try:
                if not req.func_tool:
                    return

                if (
                    self.tool_schema_mode == "skills_like"
                    and self._skill_like_raw_tool_set
                ):
                    # in 'skills_like' mode, raw.func_tool is light schema, does not have handler
                    # so we need to get the tool from the raw tool set
                    func_tool = self._skill_like_raw_tool_set.get_tool(func_tool_name)
                else:
                    func_tool = req.func_tool.get_tool(func_tool_name)

                logger.info(f"使用工具：{func_tool_name}，参数：{func_tool_args}")

                if not func_tool:
                    logger.warning(f"未找到指定的工具: {func_tool_name}，将跳过。")
                    _append_tool_call_result(
                        func_tool_id,
                        f"error: Tool {func_tool_name} not found.",
                        tool_name=func_tool_name,
                        tool_args=func_tool_args,
                    )
                    continue

                valid_params = {}  # 参数过滤：只传递函数实际需要的参数

                # 获取实际的 handler 函数
                if func_tool.handler:
                    logger.debug(
                        f"工具 {func_tool_name} 期望的参数: {func_tool.parameters}",
                    )
                    params_schema = (
                        func_tool.parameters
                        if isinstance(func_tool.parameters, dict)
                        else None
                    )
                    if func_tool.parameters and func_tool.parameters.get("properties"):
                        expected_params = set(func_tool.parameters["properties"].keys())
                        alias_mapped_params: dict[str, str] = {}
                        for raw_key, value in func_tool_args.items():
                            if raw_key in expected_params:
                                valid_params[raw_key] = value
                                continue
                            normalized_key = (
                                self._normalize_tool_param_name_for_matching(raw_key)
                            )
                            if (
                                normalized_key in expected_params
                                and normalized_key not in valid_params
                            ):
                                valid_params[normalized_key] = value
                                alias_mapped_params[raw_key] = normalized_key

                        if alias_mapped_params:
                            logger.info(
                                "工具 %s 参数名称已自动映射: %s",
                                func_tool_name,
                                alias_mapped_params,
                            )

                        valid_params, changed_types = self._coerce_tool_params_by_schema(
                            params=valid_params,
                            params_schema=params_schema,
                        )
                        if changed_types:
                            logger.info(
                                "工具 %s 参数类型已自动纠正: %s",
                                func_tool_name,
                                {
                                    k: {"from": repr(v[0]), "to": repr(v[1])}
                                    for k, v in changed_types.items()
                                },
                            )

                    # 记录被忽略的参数
                    ignored_params = set(func_tool_args.keys()) - set(
                        valid_params.keys()
                    )
                    if func_tool.parameters and func_tool.parameters.get("properties"):
                        ignored_params = {
                            k
                            for k in ignored_params
                            if self._normalize_tool_param_name_for_matching(k)
                            not in valid_params
                        }
                    if ignored_params:
                        logger.warning(
                            f"工具 {func_tool_name} 忽略非期望参数: {ignored_params}",
                        )

                    if func_tool_args and not valid_params:
                        _append_tool_call_result(
                            func_tool_id,
                            (
                                "error: No compatible arguments for this tool. "
                                f"Provided arguments={sorted(func_tool_args.keys())}. "
                                "This may indicate a wrong tool selection; "
                                "please re-check tool name and argument schema."
                            ),
                            tool_name=func_tool_name,
                            tool_args=func_tool_args,
                        )
                        continue
                else:
                    # 如果没有 handler（如 MCP 工具），使用所有参数
                    valid_params = func_tool_args

                missing_required = self._find_missing_required_tool_params(
                    tool=func_tool,
                    provided_params=valid_params,
                )
                if missing_required:
                    missing_text = ", ".join(missing_required)
                    logger.warning(
                        "工具 %s 缺少必填参数: %s。原始参数: %s",
                        func_tool_name,
                        missing_text,
                        func_tool_args,
                    )
                    _append_tool_call_result(
                        func_tool_id,
                        (
                            "error: Missing required tool arguments: "
                            f"{missing_text}. "
                            "Please call this tool again with all required arguments."
                        ),
                        tool_name=func_tool_name,
                        tool_args=func_tool_args,
                    )
                    continue

                contract_error = self._validate_anyof_oneof_contract(
                    tool=func_tool,
                    provided_params=valid_params,
                )
                if contract_error:
                    logger.warning(
                        "工具 %s 参数契约校验失败: %s",
                        func_tool_name,
                        contract_error,
                    )
                    _append_tool_call_result(
                        func_tool_id,
                        contract_error,
                        tool_name=func_tool_name,
                        tool_args=func_tool_args,
                    )
                    continue

                try:
                    await self.agent_hooks.on_tool_start(
                        self.run_context,
                        func_tool,
                        valid_params,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_start hook: {e}", exc_info=True)

                executor = self.tool_executor.execute(
                    tool=func_tool,
                    run_context=self.run_context,
                    **valid_params,  # 只传递有效的参数
                )

                _final_resp: CallToolResult | None = None
                async for resp in executor:  # type: ignore
                    if isinstance(resp, CallToolResult):
                        res = resp
                        _final_resp = resp
                        if isinstance(res.content[0], TextContent):
                            _append_tool_call_result(
                                func_tool_id,
                                res.content[0].text,
                                tool_name=func_tool_name,
                                tool_args=valid_params,
                            )
                        elif isinstance(res.content[0], ImageContent):
                            # Cache the image instead of sending directly
                            cached_img = tool_image_cache.save_image(
                                base64_data=res.content[0].data,
                                tool_call_id=func_tool_id,
                                tool_name=func_tool_name,
                                index=0,
                                mime_type=res.content[0].mimeType or "image/png",
                            )
                            _append_tool_call_result(
                                func_tool_id,
                                (
                                    f"Image returned and cached at path='{cached_img.file_path}'. "
                                    f"Review the image below. Use send_message_to_user to send it to the user if satisfied, "
                                    f"with type='image' and path='{cached_img.file_path}'."
                                ),
                                tool_name=func_tool_name,
                                tool_args=valid_params,
                            )
                            # Yield image info for LLM visibility (will be handled in step())
                            yield _HandleFunctionToolsResult.from_cached_image(
                                cached_img
                            )
                        elif isinstance(res.content[0], EmbeddedResource):
                            resource = res.content[0].resource
                            if isinstance(resource, TextResourceContents):
                                _append_tool_call_result(
                                    func_tool_id,
                                    resource.text,
                                    tool_name=func_tool_name,
                                    tool_args=valid_params,
                                )
                            elif (
                                isinstance(resource, BlobResourceContents)
                                and resource.mimeType
                                and resource.mimeType.startswith("image/")
                            ):
                                # Cache the image instead of sending directly
                                cached_img = tool_image_cache.save_image(
                                    base64_data=resource.blob,
                                    tool_call_id=func_tool_id,
                                    tool_name=func_tool_name,
                                    index=0,
                                    mime_type=resource.mimeType,
                                )
                                _append_tool_call_result(
                                    func_tool_id,
                                    (
                                        f"Image returned and cached at path='{cached_img.file_path}'. "
                                        f"Review the image below. Use send_message_to_user to send it to the user if satisfied, "
                                        f"with type='image' and path='{cached_img.file_path}'."
                                    ),
                                    tool_name=func_tool_name,
                                    tool_args=valid_params,
                                )
                                # Yield image info for LLM visibility
                                yield _HandleFunctionToolsResult.from_cached_image(
                                    cached_img
                                )
                            else:
                                _append_tool_call_result(
                                    func_tool_id,
                                    "The tool has returned a data type that is not supported.",
                                    tool_name=func_tool_name,
                                    tool_args=valid_params,
                                )

                    elif resp is None:
                        # Tool 直接请求发送消息给用户
                        # 这里我们将直接结束 Agent Loop
                        # 发送消息逻辑在 ToolExecutor 中处理了
                        logger.warning(
                            f"{func_tool_name} 没有返回值，或者已将结果直接发送给用户。"
                        )
                        self._transition_state(AgentState.DONE)
                        self.stats.end_time = time.time()
                        _append_tool_call_result(
                            func_tool_id,
                            "The tool has no return value, or has sent the result directly to the user.",
                            tool_name=func_tool_name,
                            tool_args=valid_params,
                        )
                    else:
                        # 不应该出现其他类型
                        logger.warning(
                            f"Tool 返回了不支持的类型: {type(resp)}。",
                        )
                        _append_tool_call_result(
                            func_tool_id,
                            "*The tool has returned an unsupported type. Please tell the user to check the definition and implementation of this tool.*",
                            tool_name=func_tool_name,
                            tool_args=valid_params,
                        )

                try:
                    await self.agent_hooks.on_tool_end(
                        self.run_context,
                        func_tool,
                        func_tool_args,
                        _final_resp,
                    )
                except Exception as e:
                    logger.error(f"Error in on_tool_end hook: {e}", exc_info=True)
            except Exception as e:
                logger.warning(traceback.format_exc())
                _append_tool_call_result(
                    func_tool_id,
                    f"error: {e!s}",
                    tool_name=func_tool_name,
                    tool_args=func_tool_args,
                )

        # yield the last tool call result
        if tool_call_result_blocks:
            last_tcr_content = str(tool_call_result_blocks[-1].content)
            yield _HandleFunctionToolsResult.from_message_chain(
                MessageChain(
                    type="tool_call_result",
                    chain=[
                        Json(
                            data={
                                "id": func_tool_id,
                                "ts": time.time(),
                                "result": last_tcr_content,
                            }
                        )
                    ],
                )
            )
            logger.info(f"Tool `{func_tool_name}` Result: {last_tcr_content}")

        # 处理函数调用响应
        if tool_call_result_blocks:
            yield _HandleFunctionToolsResult.from_tool_call_result_blocks(
                tool_call_result_blocks
            )

    def _build_tool_requery_context(
        self, tool_names: list[str]
    ) -> list[dict[str, T.Any]]:
        """Build contexts for re-querying LLM with param-only tool schemas."""
        contexts: list[dict[str, T.Any]] = []
        for msg in self.run_context.messages:
            if hasattr(msg, "model_dump"):
                contexts.append(msg.model_dump())  # type: ignore[call-arg]
            elif isinstance(msg, dict):
                contexts.append(copy.deepcopy(msg))
        instruction = (
            "You have decided to call tool(s): "
            + ", ".join(tool_names)
            + ". Now call the tool(s) with required arguments using the tool schema, "
            "and follow the existing tool-use rules."
        )
        if contexts and contexts[0].get("role") == "system":
            content = contexts[0].get("content") or ""
            contexts[0]["content"] = f"{content}\n{instruction}"
        else:
            contexts.insert(0, {"role": "system", "content": instruction})
        return contexts

    def _build_tool_subset(self, tool_set: ToolSet, tool_names: list[str]) -> ToolSet:
        """Build a subset of tools from the given tool set based on tool names."""
        subset = ToolSet()
        for name in tool_names:
            tool = tool_set.get_tool(name)
            if tool:
                subset.add_tool(tool)
        return subset

    async def _resolve_tool_exec(
        self,
        llm_resp: LLMResponse,
    ) -> tuple[LLMResponse, ToolSet | None]:
        """Used in 'skills_like' tool schema mode to re-query LLM with param-only tool schemas."""
        tool_names = llm_resp.tools_call_name
        if not tool_names:
            return llm_resp, self.req.func_tool
        full_tool_set = self.req.func_tool
        if not isinstance(full_tool_set, ToolSet):
            return llm_resp, self.req.func_tool

        subset = self._build_tool_subset(full_tool_set, tool_names)
        if not subset.tools:
            return llm_resp, full_tool_set

        if isinstance(self._tool_schema_param_set, ToolSet):
            param_subset = self._build_tool_subset(
                self._tool_schema_param_set, tool_names
            )
            if param_subset.tools and tool_names:
                contexts = self._build_tool_requery_context(tool_names)
                requery_resp = await self.provider.text_chat(
                    contexts=contexts,
                    func_tool=param_subset,
                    model=self.req.model,
                    session_id=self.req.session_id,
                )
                if requery_resp:
                    llm_resp = requery_resp

        return llm_resp, subset

    def done(self) -> bool:
        """检查 Agent 是否已完成工作"""
        return self._state in (AgentState.DONE, AgentState.ERROR)

    def request_stop(self) -> None:
        self._stop_requested = True

    def was_aborted(self) -> bool:
        return self._aborted

    def get_final_llm_resp(self) -> LLMResponse | None:
        return self.final_llm_resp
