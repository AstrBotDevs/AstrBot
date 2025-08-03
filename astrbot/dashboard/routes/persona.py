import traceback
from .route import Route, Response, RouteContext
from astrbot.core import logger
from quart import request
from astrbot.core.db import BaseDatabase
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle


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
        }
        self.db_helper = db_helper
        self.persona_mgr = core_lifecycle.persona_mgr
        self.register_routes()

    async def list_personas(self):
        """获取所有人格列表"""
        try:
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
                            "created_at": persona.created_at.isoformat()
                            if persona.created_at
                            else None,
                            "updated_at": persona.updated_at.isoformat()
                            if persona.updated_at
                            else None,
                        }
                        for persona in personas
                    ]
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取人格列表失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"获取人格列表失败: {str(e)}").__dict__

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
                        "created_at": persona.created_at.isoformat()
                        if persona.created_at
                        else None,
                        "updated_at": persona.updated_at.isoformat()
                        if persona.updated_at
                        else None,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取人格详情失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"获取人格详情失败: {str(e)}").__dict__

    async def create_persona(self):
        """创建新人格"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id", "").strip()
            system_prompt = data.get("system_prompt", "").strip()
            begin_dialogs = data.get("begin_dialogs", [])
            tools = data.get("tools")

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
                            "created_at": persona.created_at.isoformat()
                            if persona.created_at
                            else None,
                            "updated_at": persona.updated_at.isoformat()
                            if persona.updated_at
                            else None,
                        },
                    }
                )
                .__dict__
            )
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"创建人格失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"创建人格失败: {str(e)}").__dict__

    async def update_persona(self):
        """更新人格信息"""
        try:
            data = await request.get_json()
            persona_id = data.get("persona_id")
            system_prompt = data.get("system_prompt")
            begin_dialogs = data.get("begin_dialogs")
            tools = data.get("tools")

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
            )

            return Response().ok({"message": "人格更新成功"}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__
        except Exception as e:
            logger.error(f"更新人格失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"更新人格失败: {str(e)}").__dict__

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
            logger.error(f"删除人格失败: {str(e)}\n{traceback.format_exc()}")
            return Response().error(f"删除人格失败: {str(e)}").__dict__
