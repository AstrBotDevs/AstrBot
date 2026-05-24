import asyncio
import json
import os
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from quart import Response as QuartResponse
from quart import current_app, make_response, request

from astrbot.core import LogBroker, logger
from astrbot.core.db import BaseDatabase

from .route import Response, Route, RouteContext


def _format_log_sse(log: dict[str, Any], ts: float) -> str:
    """Format one cached event as an SSE payload."""
    payload = {
        "type": "log",
        **log,
    }
    return f"id: {ts}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _coerce_log_timestamp(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _split_query_values(args, name: str) -> set[str]:
    values: set[str] = set()
    for raw in args.getlist(name):
        for item in raw.split(","):
            normalized = item.strip()
            if normalized:
                values.add(normalized)
    return values


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, set)):
        return " ".join(_normalize_text(item) for item in value)
    return str(value)


def _build_search_blob(item: dict[str, Any]) -> str:
    values = [
        item.get("message"),
        item.get("rendered"),
        item.get("data"),
        item.get("tag"),
        item.get("tags"),
        item.get("platform_id"),
        item.get("plugin_name"),
        item.get("plugin_display_name"),
        item.get("umo"),
        item.get("logger_name"),
        item.get("source_file"),
        item.get("span_id"),
        item.get("action"),
        item.get("name"),
        item.get("sender_name"),
        item.get("message_outline"),
    ]
    return " ".join(_normalize_text(value) for value in values).lower()


def _build_filter_state() -> dict[str, Any]:
    args = request.args
    return {
        "levels": _split_query_values(args, "levels"),
        "event_types": _split_query_values(args, "type"),
        "tag_filters": _split_query_values(args, "tag"),
        "platform_filters": _split_query_values(args, "platform_id"),
        "plugin_filters": _split_query_values(args, "plugin_name"),
        "umo_filters": _split_query_values(args, "umo"),
        "keyword": args.get("keyword", "").strip().lower(),
    }


def _matches_filters(item: dict[str, Any], filters: dict[str, Any]) -> bool:
    levels = filters["levels"]
    if levels and str(item.get("level")) not in levels:
        return False

    event_types = filters["event_types"]
    if event_types and str(item.get("type", "log")) not in event_types:
        return False

    tag_filters = filters["tag_filters"]
    if tag_filters:
        item_tags = item.get("tags")
        if not isinstance(item_tags, list):
            item_tags = [item.get("tag")]
        normalized_tags = {str(tag) for tag in item_tags if tag}
        if not normalized_tags.intersection(tag_filters):
            return False

    platform_filters = filters["platform_filters"]
    if platform_filters and str(item.get("platform_id")) not in platform_filters:
        return False

    plugin_filters = filters["plugin_filters"]
    if plugin_filters and str(item.get("plugin_name")) not in plugin_filters:
        return False

    umo_filters = filters["umo_filters"]
    if umo_filters and str(item.get("umo")) not in umo_filters:
        return False

    keyword = filters["keyword"]
    if keyword and keyword not in _build_search_blob(item):
        return False

    return True


def _get_last_event_id() -> str | None:
    return request.headers.get("Last-Event-ID") or request.args.get("lastEventId")


def _trace_entry_to_dict(entry: Any, *, include_spans: bool = False) -> dict[str, Any]:
    data = {
        "id": getattr(entry, "id", None),
        "trace_id": getattr(entry, "trace_id", None),
        "umo": getattr(entry, "umo", None),
        "sender_name": getattr(entry, "sender_name", None),
        "message_outline": getattr(entry, "message_outline", None),
        "started_at": getattr(entry, "started_at", 0.0),
        "finished_at": getattr(entry, "finished_at", None),
        "duration_ms": getattr(entry, "duration_ms", None),
        "status": getattr(entry, "status", None),
        "input_text": getattr(entry, "input_text", None),
        "output_text": getattr(entry, "output_text", None),
        "total_input_tokens": getattr(entry, "total_input_tokens", 0),
        "total_output_tokens": getattr(entry, "total_output_tokens", 0),
        "created_at": _serialize_created_at(getattr(entry, "created_at", None)),
    }
    if include_spans:
        data["spans"] = getattr(entry, "spans", {}) or {}
    return data


def _serialize_created_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


class LogRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        log_broker: LogBroker,
        db_helper: BaseDatabase | None = None,
    ) -> None:
        super().__init__(context)
        self.log_broker = log_broker
        self.db_helper = db_helper
        self.app.add_url_rule("/api/live-log", view_func=self.log, methods=["GET"])
        self.app.add_url_rule(
            "/api/log-history",
            view_func=self.log_history,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/trace/settings",
            view_func=self.get_trace_settings,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/trace/settings",
            view_func=self.update_trace_settings,
            methods=["POST"],
        )
        self.app.add_url_rule(
            "/api/trace/history",
            view_func=self.get_trace_history,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/trace/list",
            view_func=self.list_traces,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/trace/detail",
            view_func=self.get_trace_detail,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/trace/sources",
            view_func=self.get_trace_sources,
            methods=["GET"],
        )
        self.app.add_url_rule(
            "/api/trace/clear",
            view_func=self.clear_traces,
            methods=["DELETE"],
        )

    async def _replay_cached_logs(
        self,
        last_event_id: str,
        filters: dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """Replay cached events newer than the last SSE event id."""
        try:
            last_ts = float(last_event_id)
            cached_logs = list(self.log_broker.log_cache)
            for log_item in cached_logs:
                log_ts = float(log_item.get("time", 0))
                if log_ts > last_ts and _matches_filters(log_item, filters):
                    yield _format_log_sse(log_item, log_ts)
        except ValueError:
            pass
        except Exception as e:
            logger.error(f"Log SSE replay failed: {e}")

    async def log(self) -> QuartResponse:
        last_event_id = _get_last_event_id()
        filters = _build_filter_state()

        async def stream():
            queue = None
            try:
                if last_event_id:
                    async for event in self._replay_cached_logs(last_event_id, filters):
                        yield event
                queue = self.log_broker.register()
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=15.0)
                        if not _matches_filters(message, filters):
                            continue
                        current_ts = float(message.get("time", time.time()))
                        yield _format_log_sse(message, current_ts)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Log SSE connection failed: {e}")
            finally:
                if queue:
                    self.log_broker.unregister(queue)

        if current_app.testing or os.environ.get("ASTRBOT_TEST_MODE") == "true":

            async def test_stream():
                if last_event_id:
                    async for event in self._replay_cached_logs(last_event_id, filters):
                        yield event
                yield ": keepalive\n\n"

            stream_body = test_stream()
        else:
            stream_body = stream()

        response = await make_response(
            stream_body,
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
            },
        )
        response.timeout = None
        return response

    async def log_history(self):
        """Return cached logs and traces, with optional filtering."""
        try:
            filters = _build_filter_state()
            logs = list(self.log_broker.log_cache)
            if request.args:
                logs = [item for item in logs if _matches_filters(item, filters)]

            limit = request.args.get("limit", default=None, type=int)
            if limit and limit > 0:
                logs = logs[-limit:]

            return Response().ok(data={"logs": logs}).__dict__
        except Exception as e:
            logger.error(f"Failed to load log history: {e}")
            return Response().error(f"Failed to load log history: {e}").__dict__

    async def get_trace_settings(self):
        """Get trace switch settings."""
        try:
            trace_enable = self.config.get("trace_enable", True)
            return Response().ok(data={"trace_enable": trace_enable}).to_json()
        except Exception as e:
            logger.error(f"Failed to get trace settings: {e}")
            return Response().error(f"Failed to get trace settings: {e}").__dict__

    async def update_trace_settings(self):
        """Update trace switch settings."""
        try:
            data = await request.json
            if data is None:
                return Response().error("Request body is empty").__dict__

            trace_enable = data.get("trace_enable")
            if trace_enable is not None:
                self.config["trace_enable"] = bool(trace_enable)
                self.config.save_config()

            return Response().ok(message="Trace settings updated").__dict__
        except Exception as e:
            logger.error(f"Failed to update trace settings: {e}")
            return Response().error(f"Failed to update trace settings: {e}").__dict__

    async def get_trace_history(self):
        """Return recent trace events from the in-memory log cache."""
        try:
            filters = _build_filter_state()
            traces = [
                item
                for item in self.log_broker.log_cache
                if item.get("type") == "trace" and _matches_filters(item, filters)
            ]
            limit = request.args.get("limit", default=None, type=int)
            if limit and limit > 0:
                traces = traces[-limit:]
            return Response().ok(data={"traces": traces}).__dict__
        except Exception as e:
            logger.error(f"Failed to load trace history: {e}")
            return Response().error(f"Failed to load trace history: {e}").__dict__

    async def list_traces(self):
        """Return persisted traces for the trace list page."""
        try:
            if self.db_helper is None:
                return Response().ok(data={"traces": [], "total": 0}).__dict__

            page = request.args.get("page", default=1, type=int) or 1
            page_size = request.args.get("page_size", default=20, type=int) or 20
            page = max(1, page)
            page_size = min(100, max(1, page_size))
            traces, total = await self.db_helper.get_traces(
                page=page,
                page_size=page_size,
                umo=request.args.get("umo") or None,
                search=request.args.get("search") or None,
                sender=request.args.get("sender") or None,
            )
            return (
                Response()
                .ok(
                    data={
                        "traces": [
                            _trace_entry_to_dict(trace, include_spans=False)
                            for trace in traces
                        ],
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                    },
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"Failed to list traces: {e}")
            return Response().error(f"Failed to list traces: {e}").__dict__

    async def get_trace_detail(self):
        """Return one persisted trace with its span tree."""
        try:
            trace_id = request.args.get("trace_id", "").strip()
            if not trace_id:
                return Response().error("trace_id is required").__dict__
            if self.db_helper is None:
                return Response().error("Trace database is unavailable").__dict__
            trace = await self.db_helper.get_trace_detail(trace_id)
            if trace is None:
                return Response().error("Trace not found").__dict__
            return (
                Response()
                .ok(
                    data=_trace_entry_to_dict(trace, include_spans=True),
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"Failed to get trace detail: {e}")
            return Response().error(f"Failed to get trace detail: {e}").__dict__

    async def get_trace_sources(self):
        """Return distinct trace sender names."""
        try:
            if self.db_helper is None:
                return Response().ok(data={"sources": []}).__dict__
            sources = await self.db_helper.get_trace_sources()
            return Response().ok(data={"sources": sources}).__dict__
        except Exception as e:
            logger.error(f"Failed to get trace sources: {e}")
            return Response().error(f"Failed to get trace sources: {e}").__dict__

    async def clear_traces(self):
        """Clear all persisted traces."""
        try:
            if self.db_helper is None:
                return Response().ok(data={"deleted": 0}).__dict__
            deleted = await self.db_helper.delete_traces_before(time.time() + 1.0)
            return Response().ok(data={"deleted": deleted}).__dict__
        except Exception as e:
            logger.error(f"Failed to clear traces: {e}")
            return Response().error(f"Failed to clear traces: {e}").__dict__
