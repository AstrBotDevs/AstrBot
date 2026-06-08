from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import request
from astrbot.dashboard.services.persona_service import (
    PersonaService,
    PersonaServiceError,
)

from .route import Response, Route, RouteContext


class PersonaRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/persona/list": ("GET", self.list_personas),
            "/persona/detail": ("POST", self.get_persona_detail),
            "/persona/create": ("POST", self.create_persona),
            "/persona/update": ("POST", self.update_persona),
            "/persona/delete": ("POST", self.delete_persona),
            "/persona/move": ("POST", self.move_persona),
            "/persona/reorder": ("POST", self.reorder_items),
            "/persona/folder/list": ("GET", self.list_folders),
            "/persona/folder/tree": ("GET", self.get_folder_tree),
            "/persona/folder/detail": ("POST", self.get_folder_detail),
            "/persona/folder/create": ("POST", self.create_folder),
            "/persona/folder/update": ("POST", self.update_folder),
            "/persona/folder/delete": ("POST", self.delete_folder),
        }
        self.service = PersonaService(core_lifecycle)
        self.register_routes()

    @staticmethod
    def _ok(data):
        return Response().ok(data).__dict__

    @staticmethod
    def _error(message: str):
        return Response().error(message).__dict__

    @staticmethod
    async def _run(self, operation, *, label: str):
        try:
            result = operation() if callable(operation) else operation
            while hasattr(result, "__await__"):
                result = await result
            return self._ok(result)
        except (PersonaServiceError, ValueError) as exc:
            return self._error(str(exc))
        except Exception as exc:
            logger.error("%s: %s", label, exc, exc_info=True)
            return self._error(f"{label}: {exc!s}")

    async def list_personas(self):
        """获取所有人格列表"""
        return await self._run(
            lambda: self.service.list_personas_from_legacy_query(
                folder_id=request.args.get("folder_id"),
                has_folder_id="folder_id" in request.args,
            ),
            label="获取人格列表失败",
        )

    async def get_persona_detail(self):
        """获取指定人格的详细信息"""
        data = await request.get_json()
        return await self._run(
            self.service.get_persona_detail(data),
            label="获取人格详情失败",
        )

    async def create_persona(self):
        """创建新人格"""
        data = await request.get_json()
        return await self._run(
            self.service.create_persona(data),
            label="创建人格失败",
        )

    async def update_persona(self):
        """更新人格信息"""
        data = await request.get_json()
        return await self._run(
            self.service.update_persona(data),
            label="更新人格失败",
        )

    async def delete_persona(self):
        """删除人格"""
        data = await request.get_json()
        return await self._run(
            self.service.delete_persona(data),
            label="删除人格失败",
        )

    async def move_persona(self):
        """移动人格到指定文件夹"""
        data = await request.get_json()
        return await self._run(
            self.service.move_persona(data),
            label="移动人格失败",
        )

    async def list_folders(self):
        """获取文件夹列表"""
        return await self._run(
            lambda: self.service.list_folders_from_legacy_query(
                request.args.get("parent_id")
            ),
            label="获取文件夹列表失败",
        )

    async def get_folder_tree(self):
        """获取文件夹树形结构"""
        return await self._run(self.service.get_folder_tree, label="获取文件夹树失败")

    async def get_folder_detail(self):
        """获取指定文件夹的详细信息"""
        data = await request.get_json()
        return await self._run(
            self.service.get_folder_detail(data),
            label="获取文件夹详情失败",
        )

    async def create_folder(self):
        """创建文件夹"""
        data = await request.get_json()
        return await self._run(
            self.service.create_folder(data),
            label="创建文件夹失败",
        )

    async def update_folder(self):
        """更新文件夹信息"""
        data = await request.get_json()
        return await self._run(
            self.service.update_folder(data),
            label="更新文件夹失败",
        )

    async def delete_folder(self):
        """删除文件夹"""
        data = await request.get_json()
        return await self._run(
            self.service.delete_folder(data),
            label="删除文件夹失败",
        )

    async def reorder_items(self):
        """批量更新排序顺序"""
        data = await request.get_json()
        return await self._run(
            self.service.reorder_items(data),
            label="更新排序失败",
        )
