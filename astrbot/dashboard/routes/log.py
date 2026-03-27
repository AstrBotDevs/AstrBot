import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any, cast

from quart import Response as QuartResponse
from quart import make_response, request

from astrbot.core import LogBroker, logger

from .route import Response, Route, RouteContext


def _format_log_sse(log: dict[str, Any], ts: float) -> str:
    """Format one cached event as an SSE payload."""
    payload = {
        "type": "log",
        **log,
    }
    return f"id: {ts}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _split_query_values(name: str) -> set[str]:
    values: set[str] = set()
    for raw in request.args.getlist(name):
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


def _matches_filters(item: dict[str, Any]) -> bool:
    levels = _split_query_values("levels")
    if levels and str(item.get("level")) not in levels:
        return False

    event_types = _split_query_values("type")
    if event_types and str(item.get("type", "log")) not in event_types:
        return False

    tag_filters = _split_query_values("tag")
    if tag_filters:
        item_tags = item.get("tags")
        if not isinstance(item_tags, list):
            item_tags = [item.get("tag")]
        normalized_tags = {str(tag) for tag in item_tags if tag}
        if not normalized_tags.intersection(tag_filters):
            return False

    platform_filters = _split_query_values("platform_id")
    if platform_filters and str(item.get("platform_id")) not in platform_filters:
        return False

    plugin_filters = _split_query_values("plugin_name")
    if plugin_filters and str(item.get("plugin_name")) not in plugin_filters:
        return False

    umo_filters = _split_query_values("umo")
    if umo_filters and str(item.get("umo")) not in umo_filters:
        return False

    keyword = request.args.get("keyword", "").strip().lower()
    if keyword and keyword not in _build_search_blob(item):
        return False

    return True


class LogRoute(Route):
    def __init__(self, context: RouteContext, log_broker: LogBroker) -> None:
        super().__init__(context)
        self.log_broker = log_broker
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

    async def _replay_cached_logs(
        self,
        last_event_id: str,
    ) -> AsyncGenerator[str, None]:
        """Replay cached events newer than the last SSE event id."""
        try:
            last_ts = float(last_event_id)
            cached_logs = list(self.log_broker.log_cache)

            for log_item in cached_logs:
                log_ts = float(log_item.get("time", 0))
                if log_ts > last_ts:
                    yield _format_log_sse(log_item, log_ts)

        except ValueError:
            pass
        except Exception as e:
            logger.error(f"Log SSE replay failed: {e}")

    async def log(self) -> QuartResponse:
        last_event_id = request.headers.get("Last-Event-ID")

        async def stream():
            queue = None
            try:
                if last_event_id:
                    async for event in self._replay_cached_logs(last_event_id):
                        yield event

                queue = self.log_broker.register()
                while True:
                    message = await queue.get()
                    current_ts = float(message.get("time", time.time()))
                    yield _format_log_sse(message, current_ts)

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Log SSE connection failed: {e}")
            finally:
                if queue:
                    self.log_broker.unregister(queue)

        response = cast(
            QuartResponse,
            await make_response(
                stream(),
                {
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Transfer-Encoding": "chunked",
                },
            ),
        )
        response.timeout = None  # type: ignore
        return response

    async def log_history(self):
        """Return cached logs and traces, with optional filtering."""
        try:
            logs = list(self.log_broker.log_cache)
            if request.args:
                logs = [item for item in logs if _matches_filters(item)]

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
            return Response().ok(data={"trace_enable": trace_enable}).__dict__
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
