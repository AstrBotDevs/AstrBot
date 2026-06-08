from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.dashboard.fastapi_compat import request
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
    SessionManagementServiceError,
)

from .route import Response, Route, RouteContext


class SessionManagementRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/session/list-rule": ("GET", self.list_session_rule),
            "/session/update-rule": ("POST", self.update_session_rule),
            "/session/delete-rule": ("POST", self.delete_session_rule),
            "/session/batch-delete-rule": ("POST", self.batch_delete_session_rule),
            "/session/active-umos": ("GET", self.list_umos),
            "/session/list-all-with-status": ("GET", self.list_all_umos_with_status),
            "/session/batch-update-service": ("POST", self.batch_update_service),
            "/session/batch-update-provider": ("POST", self.batch_update_provider),
            "/session/groups": ("GET", self.list_groups),
            "/session/group/create": ("POST", self.create_group),
            "/session/group/update": ("POST", self.update_group),
            "/session/group/delete": ("POST", self.delete_group),
        }
        self.service = SessionManagementService(core_lifecycle, db_helper)
        self.register_routes()

    @staticmethod
    def _ok(data: dict | list | None = None) -> dict:
        return Response().ok(data).__dict__

    @staticmethod
    def _error(message: str) -> dict:
        return Response().error(message).__dict__

    @staticmethod
    async def _json_body() -> dict:
        data = await request.get_json()
        return data if isinstance(data, dict) else {}

    async def _run(self, operation, *, label: str) -> dict:
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result)
        except SessionManagementServiceError as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error("%s: %s", label, exc, exc_info=True)
            return self._error(f"{label}: {exc!s}")

    async def _run_json(self, operation, *, label: str) -> dict:
        async def invoke():
            data = await self._json_body()
            return operation(data)

        return await self._run(invoke, label=label)

    async def list_session_rule(self):
        return await self._run(
            self.service.list_session_rules_from_legacy_query(
                page=request.args.get("page", 1),
                page_size=request.args.get("page_size", 10),
                search=request.args.get("search", ""),
            ),
            label="获取规则列表失败",
        )

    async def update_session_rule(self):
        return await self._run_json(
            self.service.update_session_rule,
            label="更新会话规则失败",
        )

    async def delete_session_rule(self):
        return await self._run_json(
            self.service.delete_session_rule,
            label="删除会话规则失败",
        )

    async def batch_delete_session_rule(self):
        return await self._run_json(
            self.service.batch_delete_session_rule,
            label="批量删除会话规则失败",
        )

    async def list_umos(self):
        return await self._run(
            self.service.list_active_umos(),
            label="获取 UMO 列表失败",
        )

    async def list_all_umos_with_status(self):
        return await self._run(
            self.service.list_all_umos_with_status_from_legacy_query(
                page=request.args.get("page", 1),
                page_size=request.args.get("page_size", 20),
                search=request.args.get("search", ""),
                message_type=request.args.get("message_type", "all"),
                platform=request.args.get("platform", ""),
            ),
            label="获取会话状态列表失败",
        )

    async def batch_update_service(self):
        return await self._run_json(
            self.service.batch_update_service,
            label="批量更新服务状态失败",
        )

    async def batch_update_provider(self):
        return await self._run_json(
            self.service.batch_update_provider,
            label="批量更新 Provider 失败",
        )

    async def list_groups(self):
        return await self._run(self.service.list_groups, label="获取分组列表失败")

    async def create_group(self):
        return await self._run_json(
            self.service.create_group,
            label="创建分组失败",
        )

    async def update_group(self):
        return await self._run_json(
            self.service.update_group,
            label="更新分组失败",
        )

    async def delete_group(self):
        return await self._run_json(
            self.service.delete_group,
            label="删除分组失败",
        )


__all__ = ["SessionManagementRoute"]
