# astrbot/dashboard/routes/t2i.py

from fastapi import Body, HTTPException

from astrbot.core import logger
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.utils.t2i.template_manager import TemplateManager

from .route import Response, Route, RouteContext


class T2iRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle):
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.config = core_lifecycle.astrbot_config
        self.manager = TemplateManager()
        # 使用列表保证路由注册顺序，避免 /<name> 路由优先匹配 /reset_default
        self.routes = [
            ("/t2i/templates", ("GET", self.list_templates)),
            ("/t2i/templates/active", ("GET", self.get_active_template)),
            ("/t2i/templates/create", ("POST", self.create_template)),
            ("/t2i/templates/reset_default", ("POST", self.reset_default_template)),
            ("/t2i/templates/set_active", ("POST", self.set_active_template)),
            # 动态路由应该在静态路由之后注册
            (
                "/t2i/templates/<name>",
                [
                    ("GET", self.get_template),
                    ("PUT", self.update_template),
                    ("DELETE", self.delete_template),
                ],
            ),
        ]
        self.register_routes()

    async def list_templates(self):
        """获取所有T2I模板列表"""
        try:
            templates = self.manager.list_templates()
            return Response.ok(data=templates)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def get_active_template(self):
        """获取当前激活的T2I模板"""
        try:
            active_template = self.config.get("t2i_active_template", "base")
            return Response.ok(data={"active_template": active_template})
        except Exception as e:
            logger.error("Error in get_active_template", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def get_template(self, name: str):
        """获取指定名称的T2I模板内容"""
        try:
            content = self.manager.get_template(name)
            return Response.ok(data={"name": name, "content": content})
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Template not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def create_template(self, data: dict = Body(...)):
        """创建一个新的T2I模板"""
        try:
            name = data.get("name")
            content = data.get("content")
            if not name or not content:
                raise HTTPException(status_code=400, detail="Name and content are required.")
            name = name.strip()

            self.manager.create_template(name, content)
            return Response.ok(
                data={"name": name},
                message="Template created successfully.",
            )
        except FileExistsError:
            raise HTTPException(status_code=409, detail="Template with this name already exists.")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def update_template(self, name: str, data: dict = Body(...)):
        """更新一个已存在的T2I模板"""
        try:
            name = name.strip()
            content = data.get("content")
            if content is None:
                raise HTTPException(status_code=400, detail="Content is required.")

            self.manager.update_template(name, content)

            # 检查更新的是否为当前激活的模板，如果是，则热重载
            active_template = self.config.get("t2i_active_template", "base")
            if name == active_template:
                await self.core_lifecycle.reload_pipeline_scheduler("default")
                message = f"模板 '{name}' 已更新并重新加载。"
            else:
                message = f"模板 '{name}' 已更新。"

            return Response.ok(data={"name": name}, message=message)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_template(self, name: str):
        """删除一个T2I模板"""
        try:
            name = name.strip()
            self.manager.delete_template(name)
            return Response.ok(message="Template deleted successfully.")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Template not found.")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def set_active_template(self, data: dict = Body(...)):
        """设置当前活动的T2I模板"""
        try:
            name = data.get("name")
            if not name:
                raise HTTPException(status_code=400, detail="模板名称(name)不能为空。")

            # 验证模板文件是否存在
            self.manager.get_template(name)

            # 更新配置
            config = self.config
            config["t2i_active_template"] = name
            config.save_config(config)

            # 热重载以应用更改
            await self.core_lifecycle.reload_pipeline_scheduler("default")

            return Response.ok(message=f"模板 '{name}' 已成功应用。")

        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"模板 '{name}' 不存在，无法应用。")
        except Exception as e:
            logger.error("Error in set_active_template", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def reset_default_template(self):
        """重置默认的'base'模板"""
        try:
            self.manager.reset_default_template()

            # 更新配置，将激活模板也重置为'base'
            config = self.config
            config["t2i_active_template"] = "base"
            config.save_config(config)

            # 热重载以应用更改
            await self.core_lifecycle.reload_pipeline_scheduler("default")

            return Response.ok(message="Default template has been reset and activated.")
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("Error in reset_default_template", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
