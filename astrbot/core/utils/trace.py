import asyncio
import contextlib
import functools
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import Any

from astrbot import logger
from astrbot.core import astrbot_config
from astrbot.core.log import LogQueueHandler

# ---------------------------------------------------------------------------
# Context variable — holds the currently active span for the running coroutine.
# Set by the pipeline scheduler (root trace) and updated by sub-stages/decorators.
# ---------------------------------------------------------------------------
_current_span: ContextVar["TraceSpan | None"] = ContextVar(
    "_current_span", default=None
)

_cached_log_broker = None


def _get_log_broker():
    global _cached_log_broker
    if _cached_log_broker is not None:
        return _cached_log_broker
    for handler in logger.handlers:
        if isinstance(handler, LogQueueHandler):
            _cached_log_broker = handler.log_broker
            return _cached_log_broker
    return None


def estimate_tokens(text: str) -> int:
    """Rough token count estimate: CJK chars + (other chars / 4), with 20% buffer."""
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return max(1, int((cjk + other / 4) * 1.2))


class TraceSpan:
    """A single node in the trace tree.

    Root spans (parent_id is None) represent one complete AstrMessageEvent
    processing cycle.  Child spans represent individual pipeline stages, LLM
    calls, tool calls, plugin handler invocations, etc.

    When a root span is finished (via .finish()) the full tree is:
      - broadcast in real-time through LogBroker (WebUI SSE stream)
      - written to the trace log file
      - persisted asynchronously to SQLite
    """

    def __init__(
        self,
        name: str,
        span_type: str = "span",
        parent: "TraceSpan | None" = None,
        # Root-only metadata
        umo: str | None = None,
        sender_name: str | None = None,
        message_outline: str | None = None,
    ) -> None:
        self.span_id: str = str(uuid.uuid4())
        self.parent: TraceSpan | None = parent
        self.trace_id: str = parent.trace_id if parent else self.span_id
        self.parent_id: str | None = parent.span_id if parent else None
        self.name = name
        self.span_type = span_type
        self.started_at: float = time.time()
        self.finished_at: float | None = None
        self.duration_ms: float | None = None
        self.status: str = "running"
        self.input: dict[str, Any] = {}
        self.output: dict[str, Any] = {}
        self.meta: dict[str, Any] = {}
        self.children: list[TraceSpan] = []

        # Root-level fields (meaningful only on the root span)
        self.umo = umo
        self.sender_name = sender_name
        self.message_outline = message_outline

        if parent is not None:
            parent.children.append(self)

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def child(self, name: str, span_type: str = "span", **meta: Any) -> "TraceSpan":
        """Create and return a child span attached to this span."""
        span = TraceSpan(name=name, span_type=span_type, parent=self)
        if meta:
            span.meta.update(meta)
        return span

    def set_input(self, **kwargs: Any) -> None:
        self.input.update(kwargs)

    def set_output(self, **kwargs: Any) -> None:
        self.output.update(kwargs)

    def set_meta(self, **kwargs: Any) -> None:
        self.meta.update(kwargs)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def finish(self, status: str = "ok", **output: Any) -> None:
        """Mark the span as finished.

        If this is the root span, also trigger persistence and broadcast.
        """
        if self.finished_at is not None:
            return  # idempotent
        self.finished_at = time.time()
        self.duration_ms = (self.finished_at - self.started_at) * 1000
        self.status = status
        if output:
            self.output.update(output)
        if self.parent_id is None:
            self._on_root_finish()

    def _on_root_finish(self) -> None:
        if not astrbot_config.get("trace_enable", False):
            return

        # Entire publish path is wrapped so that trace infrastructure errors
        # never propagate into the caller (scheduler, span_context, etc.).
        try:
            trace_dict = self.to_dict()

            # Real-time broadcast for WebUI SSE
            log_broker = _get_log_broker()
            if log_broker:
                log_broker.publish_trace(
                    {
                        "type": "trace_complete",
                        "trace_id": self.trace_id,
                        "umo": self.umo,
                        "sender_name": self.sender_name,
                        "message_outline": self.message_outline,
                        "started_at": self.started_at,
                        "finished_at": self.finished_at,
                        "duration_ms": self.duration_ms,
                        "status": self.status,
                        "input": self.input,
                        "output": self.output,
                        "spans": trace_dict,
                    }
                )

            # Trace file
            trace_logger = logging.getLogger("astrbot.trace")
            trace_logger.info(json.dumps(trace_dict, ensure_ascii=False, default=str))

            # Async SQLite persistence (fire-and-forget)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._persist_to_db(trace_dict))
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"[trace] Failed to publish root trace: {e}")

    async def _persist_to_db(self, trace_dict: dict) -> None:
        try:
            from astrbot.core import db_helper  # avoid circular import at module level

            total_in: list[int] = [0]
            total_out: list[int] = [0]
            self._collect_tokens(total_in, total_out)

            await db_helper.insert_trace(
                {
                    "trace_id": self.trace_id,
                    "umo": self.umo,
                    "sender_name": self.sender_name,
                    "message_outline": self.message_outline,
                    "started_at": self.started_at,
                    "finished_at": self.finished_at,
                    "duration_ms": self.duration_ms,
                    "status": self.status,
                    "spans": trace_dict,
                    "input_text": self.input.get("message", ""),
                    "output_text": self.output.get("response", ""),
                    "total_input_tokens": total_in[0],
                    "total_output_tokens": total_out[0],
                }
            )
        except Exception as e:
            logger.debug(f"[trace] Failed to persist trace to DB: {e}")

    def _collect_tokens(self, input_ref: list[int], output_ref: list[int]) -> None:
        if self.span_type == "llm_call":
            input_ref[0] += int(self.meta.get("input_tokens", 0) or 0)
            output_ref[0] += int(self.meta.get("output_tokens", 0) or 0)
        for child in self.children:
            child._collect_tokens(input_ref, output_ref)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "span_type": self.span_type,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "input": self.input,
            "output": self.output,
            "meta": self.meta,
            "umo": self.umo,
            "sender_name": self.sender_name,
            "message_outline": self.message_outline,
            "children": [c.to_dict() for c in self.children],
        }


# ---------------------------------------------------------------------------
# Context variable helpers
# ---------------------------------------------------------------------------


def get_current_span() -> "TraceSpan | None":
    """Return the active span for the current coroutine context, if any."""
    return _current_span.get()


# ---------------------------------------------------------------------------
# No-op span — returned when tracing is disabled so callers never get None.
# ---------------------------------------------------------------------------


class _NullSpan:
    """Lightweight stub that silently ignores all operations."""

    def set_input(self, **_: Any) -> None:
        pass

    def set_output(self, **_: Any) -> None:
        pass

    def set_meta(self, **_: Any) -> None:
        pass

    def finish(self, **_: Any) -> None:
        pass

    def child(self, *_: Any, **__: Any) -> "_NullSpan":
        return self


# ---------------------------------------------------------------------------
# Legacy context manager helper (kept for backward compatibility)
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def trace_span(span: TraceSpan) -> AsyncGenerator[TraceSpan, None]:
    """Async context manager that auto-finishes a span on exit.

    Usage::

        async with trace_span(event.trace.child("my_stage", span_type="pipeline_stage")) as s:
            s.set_input(foo=bar)
            await do_work()
            s.set_output(result="ok")
    """
    try:
        yield span
    except Exception as e:
        if span.finished_at is None:
            try:
                span.set_output(error=str(e))
                span.finish(status="error")
            except Exception:
                pass
        raise
    else:
        if span.finished_at is None:
            try:
                span.finish()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# New generic span context manager
# ---------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def span_context(
    name: str,
    span_type: str = "span",
    parent: "TraceSpan | None" = None,
    **meta: Any,
) -> AsyncGenerator["TraceSpan | _NullSpan", None]:
    """Create a child span, set it as the current context, and auto-finish on exit.

    When tracing is disabled a no-op ``_NullSpan`` is yielded so the caller
    never needs to guard against ``None``.

    Usage::

        async with span_context("fetch_data", span_type="io_call") as s:
            s.set_input(url=url)
            result = await httpx.get(url)
            s.set_output(status=result.status_code)
    """
    if not astrbot_config.get("trace_enable", False):
        yield _NullSpan()
        return

    resolved_parent = parent if parent is not None else _current_span.get()
    if resolved_parent is not None and not isinstance(resolved_parent, _NullSpan):
        span = resolved_parent.child(name, span_type=span_type, **meta)
        # Propagate plugin attribution from the nearest ancestor that has it,
        # so every child span is independently queryable by plugin.
        if "plugin" not in span.meta:
            ancestor: TraceSpan | None = resolved_parent
            while ancestor is not None:
                if "plugin" in ancestor.meta:
                    span.meta["plugin"] = ancestor.meta["plugin"]
                    if "plugin_type" in ancestor.meta:
                        span.meta["plugin_type"] = ancestor.meta["plugin_type"]
                    break
                ancestor = ancestor.parent
    else:
        span = TraceSpan(name=name, span_type=span_type)
        if meta:
            span.meta.update(meta)

    token = _current_span.set(span)
    try:
        yield span
        if span.finished_at is None:
            try:
                span.finish(status="ok")
            except Exception:
                pass
    except Exception as e:
        if span.finished_at is None:
            try:
                span.finish(status="error", error=str(e))
            except Exception:
                pass
        raise
    finally:
        _current_span.reset(token)


# ---------------------------------------------------------------------------
# Generic span decorator
# ---------------------------------------------------------------------------


def span_record(
    name: str | None = None,
    span_type: str = "span",
    record_input: bool = False,
    record_output: bool = False,
):
    """Decorator that wraps a sync or async function in a trace span.

    When tracing is disabled the function is called with zero overhead.

    Usage::

        @span_record("plugin.weather", span_type="plugin_call", record_input=True)
        async def get_weather(self, event, city: str):
            ...

        @span_record()  # uses the fully-qualified function name
        def process_data(data):
            ...
    """

    def decorator(func: Any) -> Any:
        span_name = name or func.__qualname__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not astrbot_config.get("trace_enable", False):
                    return await func(*args, **kwargs)
                async with span_context(span_name, span_type=span_type) as s:
                    if record_input and not isinstance(s, _NullSpan):
                        _try_record_input(s, func, args, kwargs)
                    result = await func(*args, **kwargs)
                    if (
                        record_output
                        and result is not None
                        and not isinstance(s, _NullSpan)
                    ):
                        try:
                            s.set_output(result=str(result)[:2000])
                        except Exception:
                            pass
                    return result

            return async_wrapper

        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not astrbot_config.get("trace_enable", False):
                    return func(*args, **kwargs)
                resolved_parent = _current_span.get()
                if resolved_parent is not None and not isinstance(
                    resolved_parent, _NullSpan
                ):
                    span = resolved_parent.child(span_name, span_type=span_type)
                    if "plugin" not in span.meta:
                        ancestor: TraceSpan | None = resolved_parent
                        while ancestor is not None:
                            if "plugin" in ancestor.meta:
                                span.meta["plugin"] = ancestor.meta["plugin"]
                                if "plugin_type" in ancestor.meta:
                                    span.meta["plugin_type"] = ancestor.meta[
                                        "plugin_type"
                                    ]
                                break
                            ancestor = ancestor.parent
                else:
                    span = TraceSpan(name=span_name, span_type=span_type)
                token = _current_span.set(span)
                try:
                    if record_input:
                        _try_record_input(span, func, args, kwargs)
                    result = func(*args, **kwargs)
                    if record_output and result is not None:
                        try:
                            span.set_output(result=str(result)[:2000])
                        except Exception:
                            pass
                    if span.finished_at is None:
                        try:
                            span.finish(status="ok")
                        except Exception:
                            pass
                    return result
                except Exception as e:
                    if span.finished_at is None:
                        try:
                            span.finish(status="error", error=str(e))
                        except Exception:
                            pass
                    raise
                finally:
                    _current_span.reset(token)

            return sync_wrapper

    return decorator


def _try_record_input(
    span: "TraceSpan",
    func: Any,
    args: tuple,
    kwargs: dict,
) -> None:
    """Attempt to record function arguments as span input (best-effort)."""
    try:
        import inspect

        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        params = {
            k: str(v)[:500]
            for k, v in bound.arguments.items()
            if k not in ("self", "cls", "event")
        }
        if params:
            span.set_input(**params)
    except Exception:
        pass
