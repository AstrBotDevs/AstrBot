import asyncio
import json
import os
import time
from collections.abc import AsyncGenerator
from typing import cast

from quart import Response as QuartResponse
from quart import make_response, request

from astrbot.core import LogBroker, logger
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .route import Response, Route, RouteContext


def _format_log_sse(log: dict, ts: float) -> str:
    """辅助函数：格式化 SSE 消息"""
    payload = {
        "type": "log",
        **log,
    }
    return f"id: {ts}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _format_size(size_bytes: int) -> str:
    """辅助函数：格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(os.sys.modules["math"].floor(os.sys.modules["math"].log(size_bytes, 1024)))
    p = os.sys.modules["math"].pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


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
            "/api/trace/clear",
            view_func=self.clear_traces,
            methods=["DELETE"],
        )

    async def _replay_cached_logs(
        self, last_event_id: str
    ) -> AsyncGenerator[str, None]:
        """辅助生成器：重放缓存的日志"""
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
            logger.error(f"Log SSE 补发历史错误: {e}")

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
                    current_ts = message.get("time", time.time())
                    yield _format_log_sse(message, current_ts)

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Log SSE 连接错误: {e}")
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
        """获取日志历史"""
        try:
            logs = list(self.log_broker.log_cache)
            return (
                Response()
                .ok(
                    data={
                        "logs": logs,
                    },
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取日志历史失败: {e}")
            return Response().error(f"获取日志历史失败: {e}").__dict__

    async def get_trace_settings(self):
        """获取 Trace 设置"""
        try:
            trace_enable = self.config.get("trace_enable", False)
            return Response().ok(data={"trace_enable": trace_enable}).__dict__
        except Exception as e:
            logger.error(f"获取 Trace 设置失败: {e}")
            return Response().error(f"获取 Trace 设置失败: {e}").__dict__

    async def update_trace_settings(self):
        """更新 Trace 设置"""
        try:
            data = await request.json
            if data is None:
                return Response().error("请求数据为空").__dict__

            trace_enable = data.get("trace_enable")
            if trace_enable is not None:
                self.config["trace_enable"] = bool(trace_enable)
                self.config.save_config()

            return Response().ok(message="Trace 设置已更新").__dict__
        except Exception as e:
            logger.error(f"更新 Trace 设置失败: {e}")
            return Response().error(f"更新 Trace 设置失败: {e}").__dict__

    async def get_trace_history(self):
        """获取实时 Trace 缓存（专用队列，不受普通日志数量影响）"""
        try:
            traces = list(self.log_broker.trace_cache)
            return (
                Response()
                .ok(
                    data={"traces": traces},
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取 Trace 历史失败: {e}")
            return Response().error(f"获取 Trace 历史失败: {e}").__dict__

    async def list_traces(self):
        """分页查询已持久化的 Trace 列表"""
        try:
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)
            umo = request.args.get("umo") or None
            search = request.args.get("search") or None

            page = max(1, page)
            page_size = max(1, min(page_size, 100))

            if self.db_helper is None:
                return Response().error("数据库未初始化").__dict__

            entries, total = await self.db_helper.get_traces(
                page=page,
                page_size=page_size,
                umo=umo,
                search=search,
            )

            def _entry_to_dict(e):
                return {
                    "trace_id": e.trace_id,
                    "umo": e.umo,
                    "sender_name": e.sender_name,
                    "message_outline": e.message_outline,
                    "started_at": e.started_at,
                    "finished_at": e.finished_at,
                    "duration_ms": e.duration_ms,
                    "status": e.status,
                    "input_text": e.input_text,
                    "output_text": e.output_text,
                    "total_input_tokens": e.total_input_tokens,
                    "total_output_tokens": e.total_output_tokens,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }

            # 计算 Trace 相关文件占用空间
            trace_size = 0
            data_path = get_astrbot_data_path()
            # 1. Trace 日志文件
            trace_log_dir = os.path.join(data_path, "logs")
            if os.path.exists(trace_log_dir):
                for f in os.listdir(trace_log_dir):
                    if "astrbot.trace.log" in f:
                        trace_size += os.path.getsize(os.path.join(trace_log_dir, f))

            # 2. 数据库文件大小 (虽包含其他数据，但 Trace 往往是主要占用)
            db_size = 0
            if hasattr(self.db_helper, "db_path") and os.path.exists(
                self.db_helper.db_path
            ):  # type: ignore
                db_size = os.path.getsize(self.db_helper.db_path)  # type: ignore

            return (
                Response()
                .ok(
                    data={
                        "traces": [_entry_to_dict(e) for e in entries],
                        "pagination": {
                            "page": page,
                            "page_size": page_size,
                            "total": total,
                        },
                        "trace_disk_usage": _format_size(trace_size),
                        "db_disk_usage": _format_size(db_size),
                    },
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"查询 Trace 列表失败: {e}")
            return Response().error(f"查询 Trace 列表失败: {e}").__dict__

    async def get_trace_detail(self):
        """获取单个 Trace 完整 span 树"""
        try:
            trace_id = request.args.get("trace_id")
            if not trace_id:
                return Response().error("缺少 trace_id 参数").__dict__

            if self.db_helper is None:
                return Response().error("数据库未初始化").__dict__

            entry = await self.db_helper.get_trace_detail(trace_id)
            if entry is None:
                return Response().error("Trace 不存在").__dict__

            return (
                Response()
                .ok(
                    data={
                        "trace_id": entry.trace_id,
                        "umo": entry.umo,
                        "sender_name": entry.sender_name,
                        "message_outline": entry.message_outline,
                        "started_at": entry.started_at,
                        "finished_at": entry.finished_at,
                        "duration_ms": entry.duration_ms,
                        "status": entry.status,
                        "spans": entry.spans,
                        "input_text": entry.input_text,
                        "output_text": entry.output_text,
                        "total_input_tokens": entry.total_input_tokens,
                        "total_output_tokens": entry.total_output_tokens,
                    },
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取 Trace 详情失败: {e}")
            return Response().error(f"获取 Trace 详情失败: {e}").__dict__

    async def clear_traces(self):
        """清除 Trace 记录（可选：before_ts 参数，只删除该时间戳之前的记录）"""
        try:
            if self.db_helper is None:
                return Response().error("数据库未初始化").__dict__

            before_ts = request.args.get("before_ts", type=float)
            if before_ts is None:
                before_ts = time.time()  # delete all

            deleted = await self.db_helper.delete_traces_before(before_ts)
            return Response().ok(data={"deleted": deleted}).__dict__
        except Exception as e:
            logger.error(f"清除 Trace 失败: {e}")
            return Response().error(f"清除 Trace 失败: {e}").__dict__
