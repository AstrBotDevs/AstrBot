# astrbot/dashboard/routes/t2i.py

from dataclasses import asdict
from quart import jsonify, request

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

        # 应用启动时，确保备份存在
        self.manager.backup_default_template_if_not_exist()

        self.register_routes()

    async def list_templates(self):
        """获取所有T2I模板列表"""
        try:
            templates = self.manager.list_templates()
            return jsonify(asdict(Response().ok(data=templates)))
        except Exception as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response

    async def get_active_template(self):
        """获取当前激活的T2I模板"""
        try:
            active_template = self.config.get("t2i_active_template", "base")
            return jsonify(
                asdict(Response().ok(data={"active_template": active_template}))
            )
        except Exception as e:
            logger.error("Error in get_active_template", exc_info=True)
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response

    async def get_template(self, name: str):
        """获取指定名称的T2I模板内容"""
        try:
            content = self.manager.get_template(name)
            return jsonify(
                asdict(Response().ok(data={"name": name, "content": content}))
            )
        except FileNotFoundError:
            response = jsonify(asdict(Response().error("Template not found")))
            response.status_code = 404
            return response
        except Exception as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response

    async def create_template(self):
        """创建一个新的T2I模板"""
        try:
            data = await request.json
            name = data.get("name")
            content = data.get("content")
            if not name or not content:
                response = jsonify(
                    asdict(Response().error("Name and content are required."))
                )
                response.status_code = 400
                return response

            self.manager.create_template(name, content)
            response = jsonify(
                asdict(
                    Response().ok(
                        data={"name": name}, message="Template created successfully."
                    )
                )
            )
            response.status_code = 201
            return response
        except FileExistsError:
            response = jsonify(
                asdict(Response().error("Template with this name already exists."))
            )
            response.status_code = 409
            return response
        except ValueError as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 400
            return response
        except Exception as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response

    async def update_template(self, name: str):
        """更新一个已存在的T2I模板"""
        try:
            data = await request.json
            content = data.get("content")
            if content is None:
                response = jsonify(asdict(Response().error("Content is required.")))
                response.status_code = 400
                return response

            self.manager.update_template(name, content)
            return jsonify(
                asdict(
                    Response().ok(
                        data={"name": name}, message="Template updated successfully."
                    )
                )
            )
        except FileNotFoundError:
            response = jsonify(asdict(Response().error("Template not found.")))
            response.status_code = 404
            return response
        except ValueError as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 400
            return response
        except Exception as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response

    async def delete_template(self, name: str):
        """删除一个T2I模板"""
        try:
            self.manager.delete_template(name)
            return jsonify(
                asdict(Response().ok(message="Template deleted successfully."))
            )
        except FileNotFoundError:
            response = jsonify(asdict(Response().error("Template not found.")))
            response.status_code = 404
            return response
        except ValueError as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 400
            return response
        except Exception as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response

    async def set_active_template(self):
        """设置当前活动的T2I模板"""
        try:
            data = await request.json
            name = data.get("name")
            if not name:
                response = jsonify(asdict(Response().error("模板名称(name)不能为空。")))
                response.status_code = 400
                return response

            # 验证模板文件是否存在
            self.manager.get_template(name)

            # 更新配置
            config = self.config
            config["t2i_active_template"] = name
            config.save_config(config)

            # 热重载以应用更改
            await self.core_lifecycle.reload_pipeline_scheduler("default")

            return jsonify(asdict(Response().ok(message=f"模板 '{name}' 已成功应用。")))

        except FileNotFoundError:
            response = jsonify(
                asdict(Response().error(f"模板 '{name}' 不存在，无法应用。"))
            )
            response.status_code = 404
            return response
        except Exception as e:
            logger.error("Error in set_active_template", exc_info=True)
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response

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

            return jsonify(
                asdict(
                    Response().ok(
                        message="Default template has been reset and activated."
                    )
                )
            )
        except FileNotFoundError as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 404
            return response
        except Exception as e:
            logger.error("Error in reset_default_template", exc_info=True)
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response
