import traceback

from quart import request

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase

from .route import Response, Route, RouteContext


class PersonaRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
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
            # Folder routes
            "/persona/folder/list": ("GET", self.list_folders),
            "/persona/folder/tree": ("GET", self.get_folder_tree),
            "/persona/folder/detail": ("POST", self.get_folder_detail),
            "/persona/folder/create": ("POST", self.create_folder),
            "/persona/folder/update": ("POST", self.update_folder),
            "/persona/folder/delete": ("POST", self.delete_folder),
        }
        self.db_helper = db_helper
        self.persona_mgr = core_lifecycle.persona_mgr
        self.register_routes()

    async def list_personas(self):
        """获取所有人格列表"""
        try:
            # 支持按文件夹筛选
            folder_id = request.args.get("folder_id")
            if folder_id is not None:
                personas = await self.persona_mgr.get_personas_by_folder(
                    folder_id if folder_id else None
                )
            else:
                personas = await self.persona_mgr.get_all_personas()
            return (
                Response()
                .ok(
                    [
                        {
                            "persona_id": persona.persona_id,
                            "system_prompt": persona.system_prompt,
                            "begin_dialogs": persona.begin_dialogs or [],
                            "tools": persona.tools,
                            "skills": persona.skills,
                            "folder_id": persona.folder_id,
                            "sort_order": persona.sort_order,
                            "created_at": persona.created_at.isoformat()
                            if persona.created_at
                            else None,
                            "updated_at": persona.updated_at.isoformat()
                            if persona.updated_at
                            else None,
                        }
                        for persona in personas
                    ],
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取人格列表失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取人格列表失败: {e!s}").__dict__

    async def get_persona_detail(self):
        """获取指定人格的详细信息"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")

            if not persona_id:
                return Response().error("缺少必要参数: persona_id").__dict__

            persona = await self.persona_mgr.get_persona(persona_id)
            if not persona:
                return Response().error("人格不存在").__dict__

            return (
                Response()
                .ok(
                    {
                        "persona_id": persona.persona_id,
                        "system_prompt": persona.system_prompt,
                        "begin_dialogs": persona.begin_dialogs or [],
                        "tools": persona.tools,
                        "skills": persona.skills,
                        "folder_id": persona.folder_id,
                        "sort_order": persona.sort_order,
                        "created_at": persona.created_at.isoformat()
                        if persona.created_at
                        else None,
                        "updated_at": persona.updated_at.isoformat()
                        if persona.updated_at
                        else None,
                    },
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取人格详情失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取人格详情失败: {e!s}").__dict__

    async def create_persona(self):
        """创建新人格"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id", "").strip()
            system_prompt = data.get("system_prompt", "").strip()
            begin_dialogs = data.get("begin_dialogs", [])
            tools = data.get("tools")
            skills = data.get("skills")
            folder_id = data.get("folder_id")  # None 表示根目录
            sort_order = data.get("sort_order", 0)

            if not persona_id:
                return Response().error("人格ID不能为空").__dict__

            if not system_prompt:
                return Response().error("系统提示词不能为空").__dict__

            # 验证 begin_dialogs 格式
            if begin_dialogs and len(begin_dialogs) % 2 != 0:
                return (
                    Response()
                    .error("预设对话数量必须为偶数（用户和助手轮流对话）")
                    .__dict__
                )

            persona = await self.persona_mgr.create_persona(
                persona_id=persona_id,
                system_prompt=system_prompt,
                begin_dialogs=begin_dialogs if begin_dialogs else None,
                tools=tools if tools else None,
                skills=skills if skills else None,
                folder_id=folder_id,
                sort_order=sort_order,
            )

            return (
                Response()
                .ok(
                    {
                        "message": "人格创建成功",
                        "persona": {
                            "persona_id": persona.persona_id,
                            "system_prompt": persona.system_prompt,
                            "begin_dialogs": persona.begin_dialogs or [],
                            "tools": persona.tools or [],
                            "skills": persona.skills or [],
                            "folder_id": persona.folder_id,
                            "sort_order": persona.sort_order,
                            "created_at": persona.created_at.isoformat()
                            if persona.created_at
                            else None,
                            "updated_at": persona.updated_at.isoformat()
                            if persona.updated_at
                            else None,
                        },
                    },
                )
                .__dict__
            )
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"创建人格失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"创建人格失败: {e!s}").__dict__

    async def update_persona(self):
        """更新人格信息"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")
            system_prompt = data.get("system_prompt")
            begin_dialogs = data.get("begin_dialogs")
            tools = data.get("tools")
            skills = data.get("skills")

            if not persona_id:
                return Response().error("缺少必要参数: persona_id").__dict__

            # 验证 begin_dialogs 格式
            if begin_dialogs is not None and len(begin_dialogs) % 2 != 0:
                return (
                    Response()
                    .error("预设对话数量必须为偶数（用户和助手轮流对话）")
                    .__dict__
                )

            await self.persona_mgr.update_persona(
                persona_id=persona_id,
                system_prompt=system_prompt,
                begin_dialogs=begin_dialogs,
                tools=tools,
                skills=skills,
            )

            return Response().ok({"message": "人格更新成功"}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"更新人格失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"更新人格失败: {e!s}").__dict__

    async def delete_persona(self):
        """删除人格"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")

            if not persona_id:
                return Response().error("缺少必要参数: persona_id").__dict__

            await self.persona_mgr.delete_persona(persona_id)

            return Response().ok({"message": "人格删除成功"}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"删除人格失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"删除人格失败: {e!s}").__dict__

    async def move_persona(self):
        """移动人格到指定文件夹"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")
            folder_id = data.get("folder_id")  # None 表示移动到根目录

            if not persona_id:
                return Response().error("缺少必要参数: persona_id").__dict__

            await self.persona_mgr.move_persona_to_folder(persona_id, folder_id)

            return Response().ok({"message": "人格移动成功"}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"移动人格失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"移动人格失败: {e!s}").__dict__

    # ====
    # Folder Routes
    # ====

    async def list_folders(self):
        """获取文件夹列表"""
        try:
            parent_id = request.args.get("parent_id")
            # 空字符串视为 None（根目录）
            if parent_id == "":
                parent_id = None
            folders = await self.persona_mgr.get_folders(parent_id)
            return (
                Response()
                .ok(
                    [
                        {
                            "folder_id": folder.folder_id,
                            "name": folder.name,
                            "parent_id": folder.parent_id,
                            "description": folder.description,
                            "sort_order": folder.sort_order,
                            "created_at": folder.created_at.isoformat()
                            if folder.created_at
                            else None,
                            "updated_at": folder.updated_at.isoformat()
                            if folder.updated_at
                            else None,
                        }
                        for folder in folders
                    ],
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取文件夹列表失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取文件夹列表失败: {e!s}").__dict__

    async def get_folder_tree(self):
        """获取文件夹树形结构"""
        try:
            tree = await self.persona_mgr.get_folder_tree()
            return Response().ok(tree).__dict__
        except Exception as e:
            logger.error(f"获取文件夹树失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取文件夹树失败: {e!s}").__dict__

    async def get_folder_detail(self):
        """获取指定文件夹的详细信息"""
        try:
            data = await request.get_json()
            folder_id = data.get("folder_id")

            if not folder_id:
                return Response().error("缺少必要参数: folder_id").__dict__

            folder = await self.persona_mgr.get_folder(folder_id)
            if not folder:
                return Response().error("文件夹不存在").__dict__

            return (
                Response()
                .ok(
                    {
                        "folder_id": folder.folder_id,
                        "name": folder.name,
                        "parent_id": folder.parent_id,
                        "description": folder.description,
                        "sort_order": folder.sort_order,
                        "created_at": folder.created_at.isoformat()
                        if folder.created_at
                        else None,
                        "updated_at": folder.updated_at.isoformat()
                        if folder.updated_at
                        else None,
                    },
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取文件夹详情失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取文件夹详情失败: {e!s}").__dict__

    async def create_folder(self):
        """创建文件夹"""
        try:
            data = await request.get_json()
            name = data.get("name", "").strip()
            parent_id = data.get("parent_id")
            description = data.get("description")
            sort_order = data.get("sort_order", 0)

            if not name:
                return Response().error("文件夹名称不能为空").__dict__

            folder = await self.persona_mgr.create_folder(
                name=name,
                parent_id=parent_id,
                description=description,
                sort_order=sort_order,
            )

            return (
                Response()
                .ok(
                    {
                        "message": "文件夹创建成功",
                        "folder": {
                            "folder_id": folder.folder_id,
                            "name": folder.name,
                            "parent_id": folder.parent_id,
                            "description": folder.description,
                            "sort_order": folder.sort_order,
                            "created_at": folder.created_at.isoformat()
                            if folder.created_at
                            else None,
                            "updated_at": folder.updated_at.isoformat()
                            if folder.updated_at
                            else None,
                        },
                    },
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"创建文件夹失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"创建文件夹失败: {e!s}").__dict__

    async def update_folder(self):
        """更新文件夹信息"""
        try:
            data = await request.get_json()
            folder_id = data.get("folder_id")
            name = data.get("name")
            parent_id = data.get("parent_id")
            description = data.get("description")
            sort_order = data.get("sort_order")

            if not folder_id:
                return Response().error("缺少必要参数: folder_id").__dict__

            await self.persona_mgr.update_folder(
                folder_id=folder_id,
                name=name,
                parent_id=parent_id,
                description=description,
                sort_order=sort_order,
            )

            return Response().ok({"message": "文件夹更新成功"}).__dict__
        except Exception as e:
            logger.error(f"更新文件夹失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"更新文件夹失败: {e!s}").__dict__

    async def delete_folder(self):
        """删除文件夹"""
        try:
            data = await request.get_json()
            folder_id = data.get("folder_id")

            if not folder_id:
                return Response().error("缺少必要参数: folder_id").__dict__

            await self.persona_mgr.delete_folder(folder_id)

            return Response().ok({"message": "文件夹删除成功"}).__dict__
        except Exception as e:
            logger.error(f"删除文件夹失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"删除文件夹失败: {e!s}").__dict__

    async def reorder_items(self):
        """批量更新排序顺序

        请求体格式:
        {
            "items": [
                {"id": "persona_id_1", "type": "persona", "sort_order": 0},
                {"id": "persona_id_2", "type": "persona", "sort_order": 1},
                {"id": "folder_id_1", "type": "folder", "sort_order": 0},
                ...
            ]
        }
        """
        try:
            data = await request.get_json()
            items = data.get("items", [])

            if not items:
                return Response().error("items 不能为空").__dict__

            # 验证每个 item 的格式
            for item in items:
                if not all(k in item for k in ("id", "type", "sort_order")):
                    return (
                        Response()
                        .error("每个 item 必须包含 id, type, sort_order 字段")
                        .__dict__
                    )
                if item["type"] not in ("persona", "folder"):
                    return (
                        Response()
                        .error("type 字段必须是 'persona' 或 'folder'")
                        .__dict__
                    )

            await self.persona_mgr.batch_update_sort_order(items)

            return Response().ok({"message": "排序更新成功"}).__dict__
        except Exception as e:
            logger.error(f"更新排序失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"更新排序失败: {e!s}").__dict__
