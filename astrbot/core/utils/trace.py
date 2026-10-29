"""SDK-managed traces bridged to local SQLite and live JSON updates."""

import json
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Span, SpanLimits, TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace import Status, StatusCode, format_span_id, format_trace_id

from astrbot import __version__, logger
from astrbot.core import astrbot_config
from astrbot.core.log import LogQueueHandler
from astrbot.core.utils.telemetry import (
    bounded_attributes,
    bounded_text,
)
from astrbot.core.utils.trace_store import get_trace_store

_cached_log_broker = None
MAX_TRACE_BYTES = 1024 * 1024
MAX_SPANS = 128
MAX_EVENTS = 256

# Keep local recording independent of global/plugin providers and exporters.
# Application byte budgets bound attributes without SDK truncation.
_provider = TracerProvider(
    resource=Resource({"service.name": "astrbot", "service.version": __version__}),
    sampler=ALWAYS_ON,
    span_limits=SpanLimits(
        max_attributes=SpanLimits.UNSET,
        max_span_attributes=SpanLimits.UNSET,
        max_event_attributes=SpanLimits.UNSET,
        max_link_attributes=SpanLimits.UNSET,
        max_attribute_length=SpanLimits.UNSET,
        max_span_attribute_length=SpanLimits.UNSET,
        max_events=MAX_EVENTS,
        max_links=0,
    ),
    shutdown_on_exit=False,
)
_tracer = _provider.get_tracer("astrbot.trace", __version__)


def _get_log_broker():
    global _cached_log_broker
    if _cached_log_broker is not None:
        return _cached_log_broker
    for handler in logger.handlers:
        if isinstance(handler, LogQueueHandler):
            _cached_log_broker = handler.log_broker
            return _cached_log_broker
    return None


class TraceSpan:
    """Own one message trace and its bounded operation spans and events."""

    def __init__(
        self,
        name: str,
        umo: str | None = None,
        sender_name: str | None = None,
        message_outline: str | None = None,
    ) -> None:
        self.name = bounded_text(name, 256)
        self.umo = bounded_text(umo or "", 1024)
        self.sender_name = bounded_text(sender_name or "", 256)
        self.message_outline = bounded_text(message_outline or "", 4096)
        self.started_at = time.time()
        self._start_ns = time.time_ns()
        self._root = _tracer.start_span(
            self.name,
            context=otel_context.Context(),
            start_time=self._start_ns,
            attributes={"astrbot.kind": "message"},
        )
        root_context = self._root.get_span_context()
        self.trace_id = format_trace_id(root_context.trace_id)
        self.span_id = format_span_id(root_context.span_id)
        self._started = False
        self._finished = False
        self._execution_active = False
        self._bytes = 0
        self._events = 0
        self._span_count = 1
        self._pending: dict[str, tuple[Span, Any, str]] = {}
        self._plugins: set[str] = set()
        self._summary = {
            "trace_id": self.trace_id,
            "root_span_id": self.span_id,
            "name": self.name,
            "start_time_unix_nano": str(self._start_ns),
            "end_time_unix_nano": None,
            "state": "running",
            "has_errors": False,
            "has_models": False,
            "has_plugins": False,
            "has_commands": False,
            "span_count": 1,
            "truncated": False,
            "attributes": bounded_attributes(
                {
                    "astrbot.umo": self.umo,
                    "astrbot.sender_name": self.sender_name,
                    "astrbot.message_outline": self.message_outline,
                }
            ),
            "resource": {"attributes": dict(_provider.resource.attributes)},
        }

    @contextmanager
    def context(self) -> Iterator[None]:
        """Bind the message root without correlating unrecorded messages.

        Yields:
            Control while this root's IDs are active.
        """
        if not self._root.is_recording() or (
            not astrbot_config.get("trace_enable", False) and not self._started
        ):
            yield
            return
        with otel_trace.use_span(
            self._root, record_exception=False, set_status_on_exception=False
        ):
            yield

    def _emit(
        self,
        *,
        span: Span | None = None,
        event: dict | None = None,
        closing: bool = False,
    ) -> None:
        """Queue a bounded snapshot and separately notify live subscribers.

        Args:
            span: Standard span update.
            event: Standard event associated with a span.
            closing: Whether completion must survive the trace payload limit.
        """
        # Preserve snapshot order on coarse clocks and across wall-clock corrections.
        updated_ns = max(
            time.time_ns(),
            int(self._summary.get("updated_time_unix_nano", self._start_ns)) + 1,
        )
        payload = {
            "type": "trace",
            "schema_version": 3,
            "trace": self._summary,
            "time_unix_nano": str(updated_ns),
        }
        self._summary["updated_time_unix_nano"] = payload["time_unix_nano"]
        if span is not None:
            status = {"code": span.status.status_code.value}
            if span.status.description:
                status["message"] = span.status.description
            payload["span"] = {
                "trace_id": format_trace_id(span.context.trace_id),
                "span_id": format_span_id(span.context.span_id),
                "parent_span_id": format_span_id(span.parent.span_id)
                if span.parent
                else None,
                "name": span.name,
                # SDK SpanKind is zero-based; the existing JSON uses OTel wire values.
                "kind": span.kind.value + 1,
                "start_time_unix_nano": str(span.start_time),
                "end_time_unix_nano": str(span.end_time)
                if span.end_time is not None
                else None,
                "status": status,
                "attributes": dict(span.attributes or {}),
            }
        if event is not None:
            payload["event"] = event
        size = len(json.dumps(payload, ensure_ascii=False).encode())
        if self._bytes + size > MAX_TRACE_BYTES:
            self._summary["truncated"] = True
            self._bytes = MAX_TRACE_BYTES
            if not closing:
                return
            if span is not None:
                payload["span"]["attributes"] = bounded_attributes(
                    {
                        key: bounded_text(value, 256)
                        if isinstance(value, str)
                        else value
                        for key, value in payload["span"]["attributes"].items()
                        if key
                        in {
                            "astrbot.kind",
                            "astrbot.plugin",
                            "astrbot.handler",
                            "astrbot.handler_full_name",
                            "astrbot.handler_category",
                            "astrbot.handler_type",
                            "astrbot.runner_type",
                        }
                    }
                )
        self._bytes += size
        try:
            accepted = get_trace_store(astrbot_config).append(payload, owner=self)
        except Exception:
            accepted = False
            logger.error("Failed to queue trace persistence.", exc_info=True)
        # Persistence acknowledgements are not implied by an SSE notification.
        live = json.loads(
            json.dumps({**payload, "storage_accepted": accepted}, ensure_ascii=False)
        )
        broker = _get_log_broker()
        if broker:
            broker.publish(live)

    def record(self, action: str, **fields: Any) -> None:
        """Record a span transition or event using bounded primitive attributes.

        Args:
            action: Existing instrumentation action.
            **fields: AstrBot-specific metadata mapped to namespaced attributes.
        """
        if self._finished or not self._root.is_recording():
            return
        enabled = bool(astrbot_config.get("trace_enable", False))
        if not enabled and not self._started:
            return
        now = time.time_ns()
        attrs = bounded_attributes(
            {
                "astrbot." + key: value
                for key, value in fields.items()
                if key not in {"action", "end_action", "duration_ms"}
            },
            max_bytes=MAX_TRACE_BYTES,
        )
        if attrs.get("astrbot.truncated"):
            self._summary["truncated"] = True
        if fields.get("status") == "error":
            self._summary["has_errors"] = True
        if action == "event_received":
            self._summary["attributes"].update(
                {key: value for key, value in attrs.items() if key != "astrbot.message"}
            )
            self._root.set_attributes(attrs)
        if not self._started:
            self._started = True
            self._emit(span=self._root)
        if action == "event_received":
            return

        current = otel_trace.get_current_span()
        if (
            not current.is_recording()
            or current.get_span_context().trace_id != self._root.context.trace_id
        ):
            current = self._root
        parent = format_span_id(current.get_span_context().span_id)
        starts = {
            "handler_start": "handler_end",
            "agent_start": "agent_end",
            "agent_tool_call": "agent_tool_result",
        }
        if action in starts:
            if (
                not enabled
                or self._span_count >= MAX_SPANS
                or self._bytes >= MAX_TRACE_BYTES
            ):
                self._summary["truncated"] = True
                return
            call_kind = {
                "handler_start": "plugin_handler",
                "agent_start": "agent",
                "agent_tool_call": "tool",
            }[action]
            span = _tracer.start_span(
                bounded_text(
                    str(
                        fields.get("handler_full_name")
                        or fields.get("tool_name")
                        or call_kind
                    ),
                    256,
                ),
                context=otel_trace.set_span_in_context(current),
                start_time=now,
                attributes={
                    **attrs,
                    "astrbot.kind": call_kind,
                },
            )
            span_id = format_span_id(span.context.span_id)
            token = otel_context.attach(otel_trace.set_span_in_context(span))
            self._pending[span_id] = (span, token, starts[action])
            self._span_count += 1
            self._summary["span_count"] = self._span_count
            if action == "handler_start":
                self._summary["has_plugins"] = True
                if fields.get("handler_category") == "command":
                    self._summary["has_commands"] = True
                if len(self._plugins) < MAX_SPANS:
                    self._plugins.add(
                        bounded_text(str(fields.get("plugin") or ""), 256)
                    )
                if len(self._plugins) < MAX_SPANS:
                    self._plugins.add(
                        bounded_text(
                            str(
                                fields.get("plugin_display_name")
                                or fields.get("plugin")
                                or ""
                            ),
                            256,
                        )
                    )
                self._summary["attributes"]["astrbot.plugins"] = bounded_text(
                    ", ".join(sorted(self._plugins)), 4096
                )
            if action == "agent_start":
                self._summary["has_models"] = True
            self._emit(span=span)
            return

        if action in starts.values() or action == "pipeline_end":
            target = parent
            while target in self._pending:
                span, _, end_action = self._pending[target]
                if action == "pipeline_end" or (
                    end_action == action
                    and (
                        action != "handler_end"
                        or span.attributes.get("astrbot.handler_full_name")
                        == fields.get("handler_full_name")
                    )
                ):
                    break
                target = format_span_id(span.parent.span_id)
            if action != "pipeline_end" and target not in self._pending:
                return
            # Close abandoned descendants before their ancestor. Their copied
            # contexts are invalidated even when an operation is cancelled.
            while parent in self._pending:
                span, token, _ = self._pending.pop(parent)
                is_target = parent == target and action != "pipeline_end"
                if is_target:
                    span.set_attributes(
                        bounded_attributes(
                            {**span.attributes, **attrs},
                            max_bytes=MAX_TRACE_BYTES,
                        )
                    )
                    failed = fields.get("status") == "error"
                    span.set_status(
                        Status(
                            StatusCode.ERROR if failed else StatusCode.OK,
                            bounded_text(str(fields["error"]), 1024)
                            if failed and fields.get("error")
                            else None,
                        )
                    )
                else:
                    span.set_status(
                        Status(
                            StatusCode.ERROR, "Parent operation ended before this span."
                        )
                    )
                    self._summary["has_errors"] = True
                span.end(end_time=now)
                otel_context.detach(token)
                parent = format_span_id(span.parent.span_id)
                self._emit(span=span, closing=True)
                if is_target:
                    break
            if action != "pipeline_end":
                return
            for span, _, _ in self._pending.values():
                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        "Message ended before this concurrent operation.",
                    )
                )
                span.end(end_time=now)
                self._summary["has_errors"] = True
                self._emit(span=span, closing=True)
            self._pending.clear()
            self._summary["state"] = "completed"
            self._summary["end_time_unix_nano"] = str(now)
            self._root.set_attributes(attrs)
            failed = fields.get("status") == "error"
            self._root.set_status(
                Status(
                    StatusCode.ERROR if failed else StatusCode.OK,
                    bounded_text(str(fields["error"]), 1024)
                    if failed and fields.get("error")
                    else None,
                )
            )
            self._root.end(end_time=now)
            self._finished = True
            self._emit(span=self._root, closing=True)
            return

        if not enabled or self._events >= MAX_EVENTS or self._bytes >= MAX_TRACE_BYTES:
            self._summary["truncated"] = True
            return
        self._events += 1
        current.add_event(action, attributes=attrs, timestamp=now)
        self._emit(
            event={
                "event_id": secrets.token_hex(8),
                "trace_id": self.trace_id,
                "span_id": parent,
                "name": action,
                "time_unix_nano": str(now),
                "attributes": attrs,
            }
        )


@contextmanager
def trace_execution(trace: TraceSpan) -> Iterator[None]:
    """Bind and finish a trace independently of message-event resources.

    Args:
        trace: Trace whose outermost execution scope owns completion.

    Yields:
        Control while the trace's root span is bound.

    Raises:
        BaseException: Any execution failure or cancellation, unchanged.
    """
    if trace._execution_active or trace._finished:
        yield
        return
    with trace.context():
        trace._execution_active = True
        status = "success"
        error = None
        try:
            yield
        except BaseException as exc:
            status = "error"
            error = str(exc) or type(exc).__name__
            raise
        finally:
            try:
                trace.record("pipeline_end", status=status, error=error)
            finally:
                trace._finished = True
                trace._execution_active = False
