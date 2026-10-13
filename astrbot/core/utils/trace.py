"""OTel-compatible local trace/span/event model, independent of OTLP."""

import json
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from astrbot import __version__, logger
from astrbot.core import astrbot_config
from astrbot.core.log import LogQueueHandler
from astrbot.core.utils.telemetry import (
    TraceContext,
    bind_trace_context,
    bounded_attributes,
    bounded_text,
    current_trace_context,
)
from astrbot.core.utils.trace_store import get_trace_store

_cached_log_broker = None
MAX_TRACE_BYTES = 1024 * 1024
MAX_SPANS = 128
MAX_EVENTS = 256


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
        self.trace_id = secrets.token_hex(16)
        self.span_id = secrets.token_hex(8)
        self.name = bounded_text(name, 256)
        self.umo = bounded_text(umo or "", 1024)
        self.sender_name = bounded_text(sender_name or "", 256)
        self.message_outline = bounded_text(message_outline or "", 4096)
        self.started_at = time.time()
        self._start_ns = time.time_ns()
        self._started = False
        self._finished = False
        self._bytes = 0
        self._events = 0
        self._span_count = 1
        self._pending: dict[str, tuple[dict, Any, TraceContext]] = {}
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
            "span_count": 1,
            "truncated": False,
            "attributes": bounded_attributes(
                {
                    "astrbot.umo": self.umo,
                    "astrbot.sender_name": self.sender_name,
                    "astrbot.message_outline": self.message_outline,
                }
            ),
            "resource": {
                "attributes": {
                    "service.name": "astrbot",
                    "service.version": __version__,
                }
            },
        }
        self._root = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": None,
            "name": self.name,
            "kind": 1,
            "start_time_unix_nano": str(self._start_ns),
            "end_time_unix_nano": None,
            "status": {"code": 0},
            "attributes": {"astrbot.action": "event_received"},
        }

    @contextmanager
    def context(self) -> Iterator[None]:
        """Bind the message root without correlating unrecorded messages.

        Yields:
            Control while this root's IDs are active.
        """
        if not astrbot_config.get("trace_enable", False) and not self._started:
            yield
            return
        with bind_trace_context(self.trace_id, self.span_id):
            yield

    def _emit(
        self,
        *,
        span: dict | None = None,
        event: dict | None = None,
        closing: bool = False,
    ) -> None:
        """Queue a bounded snapshot and separately notify live subscribers.

        Args:
            span: Standard span update.
            event: Standard event associated with a span.
            closing: Whether completion must survive the trace payload limit.
        """
        payload = {
            "type": "trace",
            "schema_version": 3,
            "trace": self._summary,
            "time_unix_nano": str(time.time_ns()),
        }
        self._summary["updated_time_unix_nano"] = payload["time_unix_nano"]
        if span is not None:
            payload["span"] = span
        if event is not None:
            payload["event"] = event
        size = len(json.dumps(payload, ensure_ascii=False).encode())
        if self._bytes + size > MAX_TRACE_BYTES:
            self._summary["truncated"] = True
            self._bytes = MAX_TRACE_BYTES
            if not closing:
                return
            if span is not None:
                span["attributes"] = bounded_attributes(
                    {
                        key: bounded_text(value, 256)
                        if isinstance(value, str)
                        else value
                        for key, value in span["attributes"].items()
                        if key
                        in {
                            "astrbot.action",
                            "astrbot.end_action",
                            "astrbot.kind",
                            "astrbot.plugin",
                            "astrbot.handler",
                            "astrbot.handler_full_name",
                            "astrbot.handler_category",
                            "astrbot.handler_type",
                            "astrbot.duration_ms",
                            "astrbot.runner_type",
                        }
                    }
                )
        self._bytes += size
        try:
            accepted = get_trace_store(astrbot_config).append(payload)
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
        if self._finished:
            return
        enabled = bool(astrbot_config.get("trace_enable", False))
        if not enabled and not self._started:
            return
        now = time.time_ns()
        attrs = bounded_attributes(
            {"astrbot." + key: value for key, value in fields.items()},
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
            self._root["attributes"].update(attrs)
        if not self._started:
            self._started = True
            self._emit(span=self._root)
        if action == "event_received":
            return

        current = current_trace_context.get()
        parent = (
            current.span_id
            if current and current.active and current.trace_id == self.trace_id
            else self.span_id
        )
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
            span_id = secrets.token_hex(8)
            span = {
                "trace_id": self.trace_id,
                "span_id": span_id,
                "parent_span_id": parent,
                "name": bounded_text(
                    str(
                        fields.get("handler_full_name")
                        or fields.get("tool_name")
                        or action
                    ),
                    256,
                ),
                "kind": 1,
                "start_time_unix_nano": str(now),
                "end_time_unix_nano": None,
                "status": {"code": 0},
                "attributes": {
                    **attrs,
                    "astrbot.action": action,
                    "astrbot.end_action": starts[action],
                },
            }
            context = TraceContext(self.trace_id, span_id)
            token = current_trace_context.set(context)
            self._pending[span_id] = (span, token, context)
            self._span_count += 1
            self._summary["span_count"] = self._span_count
            if action == "handler_start":
                self._summary["has_plugins"] = True
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
                span, _, _ = self._pending[target]
                if action == "pipeline_end" or (
                    span["attributes"]["astrbot.end_action"] == action
                    and (
                        action != "handler_end"
                        or span["attributes"].get("astrbot.handler_full_name")
                        == fields.get("handler_full_name")
                    )
                ):
                    break
                target = span["parent_span_id"]
            if action != "pipeline_end" and target not in self._pending:
                return
            # Close abandoned descendants before their ancestor. Their copied
            # contexts are invalidated even when an operation is cancelled.
            while parent in self._pending:
                span, token, context = self._pending.pop(parent)
                is_target = parent == target and action != "pipeline_end"
                span["end_time_unix_nano"] = str(now)
                if is_target:
                    span["attributes"] = bounded_attributes(
                        {**span["attributes"], **attrs},
                        max_bytes=MAX_TRACE_BYTES,
                    )
                    span["status"] = {
                        "code": 2 if fields.get("status") == "error" else 1
                    }
                    if fields.get("error"):
                        span["status"]["message"] = bounded_text(
                            str(fields["error"]), 1024
                        )
                else:
                    span["status"] = {
                        "code": 2,
                        "message": "Parent operation ended before this span.",
                    }
                    self._summary["has_errors"] = True
                context.active = False
                current_trace_context.reset(token)
                parent = span["parent_span_id"]
                self._emit(span=span, closing=True)
                if is_target:
                    break
            if action != "pipeline_end":
                return
            self._finished = True
            for span, _, context in self._pending.values():
                context.active = False
                span["end_time_unix_nano"] = str(now)
                span["status"] = {
                    "code": 2,
                    "message": "Message ended before this concurrent operation.",
                }
                self._summary["has_errors"] = True
                self._emit(span=span, closing=True)
            self._pending.clear()
            self._summary["state"] = "completed"
            self._summary["end_time_unix_nano"] = str(now)
            self._root["end_time_unix_nano"] = str(now)
            self._root["attributes"].update(attrs)
            self._root["attributes"]["astrbot.end_action"] = "pipeline_end"
            self._root["status"] = {"code": 2 if fields.get("status") == "error" else 1}
            if fields.get("error"):
                self._root["status"]["message"] = bounded_text(
                    str(fields["error"]), 1024
                )
            self._emit(span=self._root, closing=True)
            return

        if not enabled or self._events >= MAX_EVENTS or self._bytes >= MAX_TRACE_BYTES:
            self._summary["truncated"] = True
            return
        self._events += 1
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
