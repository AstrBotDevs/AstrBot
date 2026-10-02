"""Record observed provider calls with independent usage and attribution fields."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import wraps
from typing import Any

from astrbot import logger
from astrbot.core.provider.entities import TokenUsage
from astrbot.core.provider.provider import provider_stats_managed_by_agent


@dataclass(frozen=True, slots=True)
class UsageContext:
    session_umo: str | None = None
    trace_id: str | None = None
    plugin_id: str | None = None
    origin_type: str | None = None
    conversation_id: str | None = None
    request_kind: str | None = None


_current_usage_context: ContextVar[UsageContext] = ContextVar(
    "current_usage_context", default=UsageContext()
)
_active_providers: ContextVar[frozenset[tuple[int, int]]] = ContextVar(
    "active_usage_providers", default=frozenset()
)


@contextmanager
def usage_scope(**metadata: str | None) -> Iterator[UsageContext]:
    """Temporarily bind attribution to provider calls in the current task.

    Args:
        **metadata: UsageContext fields to set for nested calls.

    Yields:
        The effective immutable usage context.
    """
    context = replace(_current_usage_context.get(), **metadata)
    token = _current_usage_context.set(context)
    try:
        yield context
    finally:
        _current_usage_context.reset(token)


def event_usage_scope(
    event: Any,
    plugin_id: str | None = None,
    origin_type: str = "chat",
    conversation_id: str | None = None,
):
    """Bind a real message event to subsequent provider calls.

    Args:
        event: AstrBot message event with a unified origin and trace span.
        plugin_id: Plugin that initiated the call, if known.
        origin_type: Provenance of the call.
        conversation_id: Optional conversation identifier.

    Returns:
        A context manager for the event's usage scope.
    """
    current = _current_usage_context.get()
    trace = getattr(event, "trace", None)
    return usage_scope(
        session_umo=getattr(event, "unified_msg_origin", None) or current.session_umo,
        trace_id=getattr(trace, "span_id", None) or current.trace_id,
        plugin_id=plugin_id or current.plugin_id,
        origin_type=origin_type
        if event is not None
        else current.origin_type or origin_type,
        conversation_id=conversation_id or current.conversation_id,
    )


async def record_usage(
    provider: Any,
    db: Any,
    *,
    usage: TokenUsage | None,
    status: str,
    start_time: float,
    end_time: float,
    request_kind: str = "text",
    model: str | None = None,
    request_id: str | None = None,
    time_to_first_token: float = 0.0,
    usage_status: str | None = None,
    _context: UsageContext | None = None,
) -> None:
    """Write one observed call without changing its business result.

    Args:
        provider: Provider instance that made the call.
        db: AstrBot database instance.
        usage: Provider reported token usage, or None when unavailable.
        status: Completed, error, or aborted call status.
        start_time: Unix timestamp at invocation start.
        end_time: Unix timestamp at invocation end.
        request_kind: Provider operation kind.
        model: Actual response model, when known.
        request_id: Stable idempotency key for this call.
        time_to_first_token: Seconds until first streamed response.
        usage_status: Explicit usage completeness override.
    """
    context = _context or _current_usage_context.get()
    provider_config = getattr(provider, "provider_config", {}) or {}
    usage_status = usage_status or (
        "missing"
        if usage is None
        else "partial"
        if getattr(usage, "is_partial", False)
        else "reported"
    )
    token_usage = usage or TokenUsage()
    try:
        await db.insert_provider_stat(
            umo=context.session_umo or "",
            conversation_id=context.conversation_id,
            provider_id=provider_config.get("id", ""),
            provider_model=model or provider.get_model(),
            status=status,
            stats={
                "request_id": request_id or str(uuid.uuid4()),
                "trace_id": context.trace_id,
                "session_umo": context.session_umo,
                "source_id": provider_config.get("provider_source_id") or None,
                "plugin_id": context.plugin_id,
                "request_kind": request_kind,
                "usage_status": usage_status,
                "origin_type": context.origin_type or "background",
                "stat_version": 1,
                "token_usage": {
                    "input_other": token_usage.input_other,
                    "input_cached": token_usage.input_cached,
                    "output": token_usage.output,
                },
                "start_time": start_time,
                "end_time": end_time,
                "time_to_first_token": time_to_first_token,
            },
            agent_type="provider",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Persist provider usage failed: %s", exc, exc_info=True)


def instrument_provider(provider: Any, db: Any) -> Any:
    """Observe public text calls on a managed provider instance.

    Args:
        provider: Provider instance to instrument in place.
        db: Database for the usage ledger.

    Returns:
        The same provider instance.
    """
    original_text_chat = getattr(provider, "text_chat", None)
    if (
        original_text_chat is not None
        and getattr(original_text_chat, "_astrbot_usage_wrapped", False) is not True
    ):

        @wraps(original_text_chat)
        async def wrapped_text_chat(*args: Any, **kwargs: Any):
            provider_key = (id(asyncio.current_task()), id(provider))
            if provider_key in _active_providers.get():
                return await original_text_chat(*args, **kwargs)
            call_context = _current_usage_context.get()
            active_token = _active_providers.set(
                _active_providers.get() | {provider_key}
            )
            legacy_token = provider_stats_managed_by_agent.set(True)
            start_time = time.time()
            response = None
            usage = None
            status = "completed"
            try:
                response = await original_text_chat(*args, **kwargs)
                usage = getattr(response, "usage", None)
                if response is None or getattr(response, "role", None) == "err":
                    status = "error"
                return response
            except BaseException as exc:
                status = (
                    "aborted" if isinstance(exc, asyncio.CancelledError) else "error"
                )
                usage = getattr(exc, "_astrbot_token_usage", None)
                raise
            finally:
                provider_stats_managed_by_agent.reset(legacy_token)
                _active_providers.reset(active_token)
                raw_completion = getattr(response, "raw_completion", None)
                actual_model = (
                    getattr(response, "model", None)
                    or (
                        raw_completion.get("model")
                        if isinstance(raw_completion, dict)
                        else getattr(raw_completion, "model", None)
                    )
                    or kwargs.get("model")
                )
                await record_usage(
                    provider,
                    db,
                    usage=usage,
                    status=status,
                    start_time=start_time,
                    end_time=time.time(),
                    request_kind=call_context.request_kind or "text",
                    model=actual_model,
                    usage_status="partial"
                    if status == "aborted" and usage is not None
                    else None,
                    _context=call_context,
                )

        wrapped_text_chat._astrbot_usage_wrapped = True
        provider.text_chat = wrapped_text_chat

    original_stream = getattr(provider, "text_chat_stream", None)
    if (
        original_stream is not None
        and getattr(original_stream, "_astrbot_usage_wrapped", False) is not True
    ):

        @wraps(original_stream)
        async def wrapped_stream(*args: Any, **kwargs: Any):
            provider_key = (id(asyncio.current_task()), id(provider))
            if provider_key in _active_providers.get():
                async for response in original_stream(*args, **kwargs):
                    yield response
                return
            call_context = _current_usage_context.get()
            stream = original_stream(*args, **kwargs)
            start_time = time.time()
            first_token_time = 0.0
            usage = None
            status = "completed"
            response = None
            received_final = False
            try:
                while True:
                    provider_key = (id(asyncio.current_task()), id(provider))
                    scope_token = _current_usage_context.set(call_context)
                    active_token = _active_providers.set(
                        _active_providers.get() | {provider_key}
                    )
                    legacy_token = provider_stats_managed_by_agent.set(True)
                    try:
                        response = await anext(stream)
                    except StopAsyncIteration:
                        break
                    finally:
                        provider_stats_managed_by_agent.reset(legacy_token)
                        _active_providers.reset(active_token)
                        _current_usage_context.reset(scope_token)
                    if first_token_time == 0.0:
                        first_token_time = time.time() - start_time
                    if getattr(response, "usage", None) is not None:
                        usage = response.usage
                    if not getattr(response, "is_chunk", False):
                        received_final = True
                    if getattr(response, "role", None) == "err":
                        status = "error"
                    yield response
                if not received_final:
                    status = "error"
            except GeneratorExit:
                if not received_final:
                    status = "aborted"
                raise
            except BaseException as exc:
                if isinstance(exc, asyncio.CancelledError):
                    if not received_final:
                        status = "aborted"
                else:
                    status = "error"
                usage = getattr(exc, "_astrbot_token_usage", None) or usage
                raise
            finally:
                provider_key = (id(asyncio.current_task()), id(provider))
                scope_token = _current_usage_context.set(call_context)
                active_token = _active_providers.set(
                    _active_providers.get() | {provider_key}
                )
                legacy_token = provider_stats_managed_by_agent.set(True)
                try:
                    await stream.aclose()
                finally:
                    provider_stats_managed_by_agent.reset(legacy_token)
                    _active_providers.reset(active_token)
                    _current_usage_context.reset(scope_token)
                    raw_completion = getattr(response, "raw_completion", None)
                    await record_usage(
                        provider,
                        db,
                        usage=usage,
                        status=status,
                        start_time=start_time,
                        end_time=time.time(),
                        request_kind=call_context.request_kind or "text",
                        model=getattr(response, "model", None)
                        or (
                            raw_completion.get("model")
                            if isinstance(raw_completion, dict)
                            else getattr(raw_completion, "model", None)
                        )
                        or kwargs.get("model"),
                        time_to_first_token=first_token_time,
                        usage_status="partial"
                        if status in ("aborted", "error")
                        and not received_final
                        and usage is not None
                        else None,
                        _context=call_context,
                    )

        wrapped_stream._astrbot_usage_wrapped = True
        provider.text_chat_stream = wrapped_stream

    provider._usage_recording_enabled = True
    provider._usage_recording_db = db
    return provider
