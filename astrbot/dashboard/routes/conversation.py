from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.fastapi_compat import request, send_file
from astrbot.dashboard.services.conversation_service import (
    ConversationService,
    ConversationServiceError,
)

from .route import Response, Route, RouteContext


class ConversationRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/conversation/list": ("GET", self.list_conversations),
            "/conversation/detail": ("POST", self.get_conv_detail),
            "/conversation/update": ("POST", self.upd_conv),
            "/conversation/delete": ("POST", self.del_conv),
            "/conversation/update_history": ("POST", self.update_history),
            "/conversation/export": ("POST", self.export_conversations),
        }
        self.service = ConversationService(db_helper, core_lifecycle)
        self.register_routes()

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    @staticmethod
    def _ok(data=None):
        return Response().ok(data).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation, *, label: str):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result)
        except ConversationServiceError as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error("%s: %s", label, exc, exc_info=True)
            return self._error(f"{label}: {exc!s}")

    async def _run_json(self, operation, *, label: str):
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke, label=label)

    async def list_conversations(self):
        """获取对话列表，支持分页、排序和筛选"""
        return await self._run(
            self.service.list_conversations_from_legacy_query(
                page=request.args.get("page", 1),
                page_size=request.args.get("page_size", 20),
                platforms=request.args.get("platforms", ""),
                message_types=request.args.get("message_types", ""),
                search_query=request.args.get("search", ""),
                exclude_ids=request.args.get("exclude_ids", ""),
                exclude_platforms=request.args.get("exclude_platforms", ""),
            ),
            label="获取对话列表失败",
        )

    async def get_conv_detail(self):
        """获取指定对话详情（通过POST请求）"""
        return await self._run_json(
            self.service.get_conversation_detail,
            label="获取对话详情失败",
        )

    async def upd_conv(self):
        """更新对话信息(标题和角色ID)"""
        return await self._run_json(
            self.service.update_conversation,
            label="更新对话信息失败",
        )

    async def del_conv(self):
        """删除对话"""
        return await self._run_json(
            self.service.delete_conversation,
            label="删除对话失败",
        )

    async def update_history(self):
        """更新对话历史内容"""
        return await self._run_json(
            self.service.update_history,
            label="更新对话历史失败",
        )

    async def export_conversations(self):
        """批量导出对话为 JSONL 格式"""
        try:
            export = await self.service.export_conversations(await self._json_body())
            return await send_file(
                export.file_obj,
                mimetype=export.mimetype,
                as_attachment=True,
                attachment_filename=export.filename,
            )
        except ConversationServiceError as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error("批量导出对话失败: %s", exc, exc_info=True)
            return self._error(f"批量导出对话失败: {exc!s}")
