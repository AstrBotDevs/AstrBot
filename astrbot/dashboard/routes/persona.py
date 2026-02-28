from astrbot.core.lang import t
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
                            "custom_error_message": persona.custom_error_message,
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
            logger.error(t("msg-4a12aead", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-c168407f", e=e)).__dict__

    async def get_persona_detail(self):
        """获取指定人格的详细信息"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")

            if not persona_id:
                return Response().error(t("msg-63c6f414")).__dict__

            persona = await self.persona_mgr.get_persona(persona_id)
            if not persona:
                return Response().error(t("msg-ce7da6f3")).__dict__

            return (
                Response()
                .ok(
                    {
                        "persona_id": persona.persona_id,
                        "system_prompt": persona.system_prompt,
                        "begin_dialogs": persona.begin_dialogs or [],
                        "tools": persona.tools,
                        "skills": persona.skills,
                        "custom_error_message": persona.custom_error_message,
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
            logger.error(t("msg-9c07774d", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-ee3b44ad", e=e)).__dict__

    async def create_persona(self):
        """创建新人格"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id", "").strip()
            system_prompt = data.get("system_prompt", "").strip()
            begin_dialogs = data.get("begin_dialogs", [])
            tools = data.get("tools")
            skills = data.get("skills")
            custom_error_message = data.get("custom_error_message")
            folder_id = data.get("folder_id")  # None 表示根目录
            sort_order = data.get("sort_order", 0)

            if not persona_id:
                return Response().error(t("msg-ad455c14")).__dict__

            if not system_prompt:
                return Response().error(t("msg-43037094")).__dict__

            if custom_error_message is not None:
                if not isinstance(custom_error_message, str):
                    return Response().error("自定义报错回复信息必须是字符串").__dict__
                custom_error_message = custom_error_message.strip() or None

            # 验证 begin_dialogs 格式
            if begin_dialogs and len(begin_dialogs) % 2 != 0:
                return (
                    Response()
                    .error(t("msg-ec9dda44"))
                    .__dict__
                )

            persona = await self.persona_mgr.create_persona(
                persona_id=persona_id,
                system_prompt=system_prompt,
                begin_dialogs=begin_dialogs if begin_dialogs else None,
                tools=tools if tools else None,
                skills=skills if skills else None,
                custom_error_message=custom_error_message,
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
                            "custom_error_message": persona.custom_error_message,
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
            logger.error(t("msg-26b214d5", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-8913dfe6", e=e)).__dict__

    async def update_persona(self):
        """更新人格信息"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")
            system_prompt = data.get("system_prompt")
            begin_dialogs = data.get("begin_dialogs")
            has_tools = "tools" in data
            tools = data.get("tools")
            has_skills = "skills" in data
            skills = data.get("skills")
            has_custom_error_message = "custom_error_message" in data
            custom_error_message = data.get("custom_error_message")

            if not persona_id:
                return Response().error(t("msg-63c6f414")).__dict__

            if has_custom_error_message:
                if custom_error_message is not None and not isinstance(
                    custom_error_message, str
                ):
                    return Response().error("自定义报错回复信息必须是字符串").__dict__
                if isinstance(custom_error_message, str):
                    custom_error_message = custom_error_message.strip() or None

            # 验证 begin_dialogs 格式
            if begin_dialogs is not None and len(begin_dialogs) % 2 != 0:
                return (
                    Response()
                    .error(t("msg-ec9dda44"))
                    .__dict__
                )

            update_kwargs = {
                "persona_id": persona_id,
                "system_prompt": system_prompt,
                "begin_dialogs": begin_dialogs,
            }
            if has_tools:
                update_kwargs["tools"] = tools
            if has_skills:
                update_kwargs["skills"] = skills
            if has_custom_error_message:
                update_kwargs["custom_error_message"] = custom_error_message

            await self.persona_mgr.update_persona(**update_kwargs)

            return Response().ok({"message": "人格更新成功"}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(t("msg-3d94d18d", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-f2cdfbb8", e=e)).__dict__

    async def delete_persona(self):
        """删除人格"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")

            if not persona_id:
                return Response().error(t("msg-63c6f414")).__dict__

            await self.persona_mgr.delete_persona(persona_id)

            return Response().ok({"message": "人格删除成功"}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(t("msg-51d84afc", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-8314a263", e=e)).__dict__

    async def move_persona(self):
        """移动人格到指定文件夹"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")
            folder_id = data.get("folder_id")  # None 表示移动到根目录

            if not persona_id:
                return Response().error(t("msg-63c6f414")).__dict__

            await self.persona_mgr.move_persona_to_folder(persona_id, folder_id)

            return Response().ok({"message": "人格移动成功"}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(t("msg-b8ecb8f9", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-ab0420e3", e=e)).__dict__

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
            logger.error(t("msg-e5604a24", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-4d7c7f4a", e=e)).__dict__

    async def get_folder_tree(self):
        """获取文件夹树形结构"""
        try:
            tree = await self.persona_mgr.get_folder_tree()
            return Response().ok(tree).__dict__
        except Exception as e:
            logger.error(t("msg-cf0ee4aa", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-bb515af0", e=e)).__dict__

    async def get_folder_detail(self):
        """获取指定文件夹的详细信息"""
        try:
            data = await request.get_json()
            folder_id = data.get("folder_id")

            if not folder_id:
                return Response().error(t("msg-c92b4863")).__dict__

            folder = await self.persona_mgr.get_folder(folder_id)
            if not folder:
                return Response().error(t("msg-77cdd6fa")).__dict__

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
            logger.error(t("msg-2d34652f", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-650ef096", e=e)).__dict__

    async def create_folder(self):
        """创建文件夹"""
        try:
            data = await request.get_json()
            name = data.get("name", "").strip()
            parent_id = data.get("parent_id")
            description = data.get("description")
            sort_order = data.get("sort_order", 0)

            if not name:
                return Response().error(t("msg-27c413df")).__dict__

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
            logger.error(t("msg-b5866931", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-5e57f3b5", e=e)).__dict__

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
                return Response().error(t("msg-c92b4863")).__dict__

            await self.persona_mgr.update_folder(
                folder_id=folder_id,
                name=name,
                parent_id=parent_id,
                description=description,
                sort_order=sort_order,
            )

            return Response().ok({"message": "文件夹更新成功"}).__dict__
        except Exception as e:
            logger.error(t("msg-9bd8f820", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-1eada044", e=e)).__dict__

    async def delete_folder(self):
        """删除文件夹"""
        try:
            data = await request.get_json()
            folder_id = data.get("folder_id")

            if not folder_id:
                return Response().error(t("msg-c92b4863")).__dict__

            await self.persona_mgr.delete_folder(folder_id)

            return Response().ok({"message": "文件夹删除成功"}).__dict__
        except Exception as e:
            logger.error(t("msg-9cef0256", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-22020727", e=e)).__dict__

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
                return Response().error(t("msg-7a69fe08")).__dict__

            # 验证每个 item 的格式
            for item in items:
                if not all(k in item for k in ("id", "type", "sort_order")):
                    return (
                        Response()
                        .error(t("msg-e71ba5c2"))
                        .__dict__
                    )
                if item["type"] not in ("persona", "folder"):
                    return (
                        Response()
                        .error(t("msg-dfeb8320"))
                        .__dict__
                    )

            await self.persona_mgr.batch_update_sort_order(items)

            return Response().ok({"message": "排序更新成功"}).__dict__
        except Exception as e:
            logger.error(t("msg-aec43ed3", e=e, res=traceback.format_exc()))
            return Response().error(t("msg-75ec4427", e=e)).__dict__
