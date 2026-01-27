from __future__ import annotations

import functools
import inspect
import sys
from typing import Any

from astrbot.core import logger as astrbot_logger
from astrbot.core.star.star_handler import StarHandlerMetadata

from .ast_scan import (
    StaticScanResult,
    _format_parse_error,
    _NameCallScanner,
    _parse_source_compat,
    _RiskScanner,
    _SelfCallScanner,
)

logger = astrbot_logger

_LOGGED_SOURCE_FAILURES: set[str] = set()


def _unwrap_callable(obj: Any) -> Any:
    while isinstance(obj, functools.partial):
        obj = obj.func
    return inspect.unwrap(obj)


def _try_get_source(handler: StarHandlerMetadata) -> tuple[str | None, str | None]:
    try:
        fn = _unwrap_callable(handler.handler)
        return inspect.getsource(fn), None
    except Exception as err:
        handler_full_name = getattr(handler, "handler_full_name", "<unknown>")
        handler_module_path = getattr(handler, "handler_module_path", "<unknown>")
        reason = f"{err.__class__.__name__}: {err}"

        key = f"{handler_full_name}|{handler_module_path}|{err.__class__.__name__}"
        if key not in _LOGGED_SOURCE_FAILURES:
            _LOGGED_SOURCE_FAILURES.add(key)
            logger.warning(
                "pipeline snapshot: failed to get source; handler=%s module=%s py=%s; %s",
                handler_full_name,
                handler_module_path,
                sys.version.split()[0],
                reason,
                exc_info=True,
            )
        else:
            logger.debug(
                "pipeline snapshot: failed to get source (suppressed); handler=%s module=%s; %s",
                handler_full_name,
                handler_module_path,
                reason,
                exc_info=True,
            )

        return None, reason


def _fallback_risks_from_metadata(
    handler: StarHandlerMetadata,
    *,
    reason: str,
) -> StaticScanResult:
    risks: list[dict[str, Any]] = [
        {
            "type": "unknown_source",
            "level": "info",
            "summary": "AST 解析失败，已降级为保守分析。",
            "details": reason,
        }
    ]

    event_name = getattr(getattr(handler, "event_type", None), "name", "") or ""
    llm_mutations: dict[str, str] = {
        "prompt": "none",
        "system_prompt": "none",
        "persona_prompt": "none",
    }

    if event_name == "OnLLMRequestEvent":
        llm_mutations = {
            "prompt": "unknown",
            "system_prompt": "unknown",
            "persona_prompt": "unknown",
        }
        risks.append(
            {
                "type": "may_mutate_prompt",
                "level": "info",
                "summary": "处于 LLM 请求前阶段（OnLLMRequestEvent），可能修改 request.prompt。",
            }
        )
        risks.append(
            {
                "type": "may_mutate_system_prompt",
                "level": "info",
                "summary": "处于 LLM 请求前阶段（OnLLMRequestEvent），可能修改 request.system_prompt。",
            }
        )

    if event_name == "OnCallingFuncToolEvent":
        risks.append(
            {
                "type": "may_call_tools",
                "level": "info",
                "summary": "处于函数工具调用阶段（OnCallingFuncToolEvent），可能触发或影响工具调用。",
            }
        )

    if event_name == "OnDecoratingResultEvent":
        risks.append(
            {
                "type": "may_set_result",
                "level": "info",
                "summary": "处于回复装饰阶段（OnDecoratingResultEvent），可能修改最终回复内容。",
            }
        )

    return StaticScanResult(risks=risks, llm_mutations=llm_mutations, effects=[])


def scan_static_risks(
    handler: StarHandlerMetadata,
    *,
    debug: bool = False,
) -> StaticScanResult:
    """
    Returns:
      - risks: StaticRiskFlag[] (backward compatible)
      - llm_mutations: legacy summary for prompt/system_prompt/persona_prompt (backward compatible)
      - effects: richer effects[] summary (new)

    兼容性：
      - 仍支持 `risks, llm_mutations = scan_static_risks(...)` 的 2 元解包。
      - 新增 `effects` 可通过返回对象的 `.effects` 访问。
    约束：源码不可得或 AST 解析失败时，必须降级为 unknown_source，不报错。
    """
    src, src_err = _try_get_source(handler)
    if not src:
        return StaticScanResult(
            risks=[
                {
                    "type": "unknown_source",
                    "level": "info",
                    "summary": "无法获取源码，已降级为 unknown_source。",
                    "details": src_err or "inspect.getsource returned empty",
                },
            ],
            llm_mutations={
                "prompt": "unknown",
                "system_prompt": "unknown",
                "persona_prompt": "unknown",
            },
            effects=[],
        )

    try:
        tree = _parse_source_compat(src)
    except Exception as err:
        reason = _format_parse_error(err)
        logger.warning(
            "pipeline snapshot: AST parse failed; handler=%s module=%s py=%s; %s",
            getattr(handler, "handler_full_name", "<unknown>"),
            getattr(handler, "handler_module_path", "<unknown>"),
            sys.version.split()[0],
            reason,
            exc_info=True,
        )
        return _fallback_risks_from_metadata(handler, reason=reason)

    v = _RiskScanner()
    v.visit(tree)

    if debug:
        logger.debug(
            "pipeline snapshot debug: ast scan; handler=%s module=%s calls=%s assigns=%s aug_assigns=%s yields_result=%s persona_prompt_overwrite=%s persona_prompt_append=%s stop_event_confidence=%s stop_event_reason=%s stop_event_sites=%s effects_len=%s",
            getattr(handler, "handler_full_name", "<unknown>"),
            getattr(handler, "handler_module_path", "<unknown>"),
            sorted(v.calls),
            sorted(v.assigns),
            sorted(v.aug_assigns),
            v.yields_result,
            v.persona_prompt_overwrite,
            v.persona_prompt_append,
            v.stop_event_confidence,
            v.stop_event_confidence_reason,
            v.stop_event_sites,
            len(v.effects),
        )

    risks: list[dict[str, Any]] = []

    if "stop_event" in v.calls:
        stop_confidence = v.stop_event_confidence or "low"
        stop_reason = v.stop_event_confidence_reason or "unknown"

        risks.append(
            {
                "type": "may_stop_event",
                "level": "warn",
                "summary": "可能调用 event.stop_event() 中断后续处理。",
                "confidence": stop_confidence,
                "confidence_reason": stop_reason,
            },
        )
        risks.append(
            {
                "type": "stop_blocks_pipeline_risk",
                "level": "warn",
                "summary": "Stop 可能导致后续 hook/阶段不执行。",
                "confidence": stop_confidence,
                "confidence_reason": stop_reason,
            },
        )

    if "send" in v.calls:
        risks.append(
            {
                "type": "may_send_directly",
                "level": "warn",
                "summary": "可能直接调用 event.send() 发送消息。",
            },
        )

    if "set_result" in v.calls or v.yields_result:
        risks.append(
            {
                "type": "may_set_result",
                "level": "info",
                "summary": "可能设置事件结果（event.set_result / yield MessageEventResult）。",
            },
        )

    if "request_llm" in v.calls:
        risks.append(
            {
                "type": "may_request_llm",
                "level": "info",
                "summary": "可能触发 LLM 请求。",
            },
        )

    llm_mutations: dict[str, str] = {
        "prompt": "none",
        "system_prompt": "none",
        "persona_prompt": "none",
    }
    for field in ("prompt", "system_prompt"):
        if field in v.assigns:
            llm_mutations[field] = "overwrite"
        elif field in v.aug_assigns:
            llm_mutations[field] = "append"
        else:
            llm_mutations[field] = "none"

    if v.persona_prompt_overwrite:
        llm_mutations["persona_prompt"] = "overwrite"
    elif v.persona_prompt_append:
        llm_mutations["persona_prompt"] = "append"
    else:
        llm_mutations["persona_prompt"] = "none"

    if llm_mutations["prompt"] in {"append", "overwrite"}:
        risks.append(
            {
                "type": "may_mutate_prompt",
                "level": "info",
                "summary": "可能修改 request.prompt。",
            },
        )

    if llm_mutations["system_prompt"] in {"append", "overwrite"}:
        risks.append(
            {
                "type": "may_mutate_system_prompt",
                "level": "info",
                "summary": "可能修改 request.system_prompt。",
            },
        )

    if llm_mutations["persona_prompt"] in {"append", "overwrite"}:
        risks.append(
            {
                "type": "may_modify_persona_prompt",
                "level": "info",
                "summary": "可能修改 persona.prompt（persona['prompt']/persona.prompt）。",
            },
        )

    if any(r["type"] == "may_send_directly" for r in risks) and any(
        r["type"] == "may_set_result" for r in risks
    ):
        risks.append(
            {
                "type": "duplicate_send_risk",
                "level": "warn",
                "summary": "同时存在 send 与 set_result，可能导致重复发送。",
            },
        )

    return StaticScanResult(risks=risks, llm_mutations=llm_mutations, effects=v.effects)


def scan_static_self_calls_from_callable(
    fn: Any,
    *,
    debug: bool = False,
    label: str | None = None,
    module_path: str | None = None,
) -> tuple[set[str], str | None]:
    """
    静态扫描 callable 中的 `self.xxx()` 调用点，返回被调用的方法名集合。
    约束：源码不可得或 AST 解析失败时返回空集合，不抛异常。
    """
    try:
        raw = _unwrap_callable(fn)
        src = inspect.getsource(raw)
    except Exception as err:
        reason = f"{err.__class__.__name__}: {err}"
        key = f"callable_calls|{label or getattr(fn, '__name__', '<unknown>')}|{module_path or getattr(fn, '__module__', '<unknown>')}|{err.__class__.__name__}"
        if key not in _LOGGED_SOURCE_FAILURES:
            _LOGGED_SOURCE_FAILURES.add(key)
            logger.warning(
                "pipeline snapshot: failed to get source for callable calls; label=%s module=%s py=%s; %s",
                label or getattr(fn, "__name__", "<unknown>"),
                module_path or getattr(fn, "__module__", "<unknown>"),
                sys.version.split()[0],
                reason,
                exc_info=True,
            )
        return set(), reason

    if not src:
        return set(), "inspect.getsource returned empty"

    try:
        tree = _parse_source_compat(src)
    except Exception as err:
        reason = _format_parse_error(err)
        logger.warning(
            "pipeline snapshot: AST parse failed for callable calls; label=%s module=%s py=%s; %s",
            label or getattr(fn, "__name__", "<unknown>"),
            module_path or getattr(fn, "__module__", "<unknown>"),
            sys.version.split()[0],
            reason,
            exc_info=True,
        )
        return set(), reason

    v = _SelfCallScanner()
    v.visit(tree)

    if debug:
        logger.debug(
            "pipeline snapshot debug: ast scan callable calls; label=%s module=%s calls=%s",
            label or getattr(fn, "__name__", "<unknown>"),
            module_path or getattr(fn, "__module__", "<unknown>"),
            sorted(v.calls),
        )

    return v.calls, None


def scan_static_name_calls_from_callable(
    fn: Any,
    *,
    debug: bool = False,
    label: str | None = None,
    module_path: str | None = None,
) -> tuple[set[str], str | None]:
    """
    静态扫描 callable 中的 `foo()` 调用点（Name 调用），返回被调用的函数名集合。
    约束：源码不可得或 AST 解析失败时返回空集合，不抛异常。
    """
    try:
        raw = _unwrap_callable(fn)
        src = inspect.getsource(raw)
    except Exception as err:
        reason = f"{err.__class__.__name__}: {err}"
        key = f"callable_name_calls|{label or getattr(fn, '__name__', '<unknown>')}|{module_path or getattr(fn, '__module__', '<unknown>')}|{err.__class__.__name__}"
        if key not in _LOGGED_SOURCE_FAILURES:
            _LOGGED_SOURCE_FAILURES.add(key)
            logger.warning(
                "pipeline snapshot: failed to get source for callable name calls; label=%s module=%s py=%s; %s",
                label or getattr(fn, "__name__", "<unknown>"),
                module_path or getattr(fn, "__module__", "<unknown>"),
                sys.version.split()[0],
                reason,
                exc_info=True,
            )
        return set(), reason

    if not src:
        return set(), "inspect.getsource returned empty"

    try:
        tree = _parse_source_compat(src)
    except Exception as err:
        reason = _format_parse_error(err)
        logger.warning(
            "pipeline snapshot: AST parse failed for callable name calls; label=%s module=%s py=%s; %s",
            label or getattr(fn, "__name__", "<unknown>"),
            module_path or getattr(fn, "__module__", "<unknown>"),
            sys.version.split()[0],
            reason,
            exc_info=True,
        )
        return set(), reason

    v = _NameCallScanner()
    v.visit(tree)

    if debug:
        logger.debug(
            "pipeline snapshot debug: ast scan callable name calls; label=%s module=%s calls=%s",
            label or getattr(fn, "__name__", "<unknown>"),
            module_path or getattr(fn, "__module__", "<unknown>"),
            sorted(v.calls),
        )

    return v.calls, None


def scan_static_mutations_from_callable(
    fn: Any,
    *,
    debug: bool = False,
    label: str | None = None,
    module_path: str | None = None,
) -> tuple[dict[str, str], str | None]:
    """
    对任意 callable 做与 scan_static_risks() 相同的 AST 扫描，返回 prompt/system_prompt/persona_prompt 的静态修改信息。
    约束：源码不可得或 AST 解析失败时返回 unknown，不抛异常。
    """
    try:
        raw = _unwrap_callable(fn)
        src = inspect.getsource(raw)
    except Exception as err:
        reason = f"{err.__class__.__name__}: {err}"
        key = f"callable|{label or getattr(fn, '__name__', '<unknown>')}|{module_path or getattr(fn, '__module__', '<unknown>')}|{err.__class__.__name__}"
        if key not in _LOGGED_SOURCE_FAILURES:
            _LOGGED_SOURCE_FAILURES.add(key)
            logger.warning(
                "pipeline snapshot: failed to get source for callable; label=%s module=%s py=%s; %s",
                label or getattr(fn, "__name__", "<unknown>"),
                module_path or getattr(fn, "__module__", "<unknown>"),
                sys.version.split()[0],
                reason,
                exc_info=True,
            )
        return {
            "prompt": "unknown",
            "system_prompt": "unknown",
            "persona_prompt": "unknown",
        }, reason
    if not src:
        return {
            "prompt": "unknown",
            "system_prompt": "unknown",
            "persona_prompt": "unknown",
        }, "inspect.getsource returned empty"

    try:
        tree = _parse_source_compat(src)
    except Exception as err:
        reason = _format_parse_error(err)
        logger.warning(
            "pipeline snapshot: AST parse failed for callable; label=%s module=%s py=%s; %s",
            label or getattr(fn, "__name__", "<unknown>"),
            module_path or getattr(fn, "__module__", "<unknown>"),
            sys.version.split()[0],
            reason,
            exc_info=True,
        )
        return {
            "prompt": "unknown",
            "system_prompt": "unknown",
            "persona_prompt": "unknown",
        }, reason

    v = _RiskScanner()
    v.visit(tree)

    if debug:
        logger.debug(
            "pipeline snapshot debug: ast scan callable; label=%s module=%s calls=%s assigns=%s aug_assigns=%s yields_result=%s persona_prompt_overwrite=%s persona_prompt_append=%s",
            label or getattr(fn, "__name__", "<unknown>"),
            module_path or getattr(fn, "__module__", "<unknown>"),
            sorted(v.calls),
            sorted(v.assigns),
            sorted(v.aug_assigns),
            v.yields_result,
            v.persona_prompt_overwrite,
            v.persona_prompt_append,
        )

    mutations: dict[str, str] = {
        "prompt": "none",
        "system_prompt": "none",
        "persona_prompt": "none",
    }
    for field in ("prompt", "system_prompt"):
        if field in v.assigns:
            mutations[field] = "overwrite"
        elif field in v.aug_assigns:
            mutations[field] = "append"
        else:
            mutations[field] = "none"

    if v.persona_prompt_overwrite:
        mutations["persona_prompt"] = "overwrite"
    elif v.persona_prompt_append:
        mutations["persona_prompt"] = "append"
    else:
        mutations["persona_prompt"] = "none"

    return mutations, None


__all__ = [
    "scan_static_risks",
    "scan_static_mutations_from_callable",
    "scan_static_self_calls_from_callable",
    "scan_static_name_calls_from_callable",
    "StaticScanResult",
]
