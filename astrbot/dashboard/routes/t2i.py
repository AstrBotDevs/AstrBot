# astrbot/dashboard/routes/t2i.py

from dataclasses import asdict
from quart import Quart, jsonify, request

from astrbot.core import logger
from astrbot.core.utils.t2i.template_manager import TemplateManager
from .route import Response

class T2iRoute:
    def __init__(self, app: Quart, db, core_lifecycle):
        self.app = app
        self.manager = TemplateManager()
        # 使用列表保证路由注册顺序，避免 /<name> 路由优先匹配 /reset_default
        self.routes = [
            ("/api/t2i/templates", ("GET", self.list_templates)),
            ("/api/t2i/templates/create", ("POST", self.create_template)),
            ("/api/t2i/templates/reset_default", ("POST", self.reset_default_template)),
            # 动态路由应该在静态路由之后注册
            ("/api/t2i/templates/<name>", [
                ("GET", self.get_template),
                ("PUT", self.update_template),
                ("DELETE", self.delete_template),
            ]),
        ]
        
        # 应用启动时，确保备份存在
        self.manager.backup_default_template_if_not_exist()

    def register_routes(self):
        logger.info("Registering T2i routes...")
        for path, methods in self.routes:
            if isinstance(methods, tuple):
                # 单一方法
                method, handler = methods
                logger.info(f"  - Registering: {method} {path}")
                self.app.add_url_rule(path, view_func=handler, methods=[method])
            elif isinstance(methods, list):
                # 多方法
                for method, handler in methods:
                    logger.info(f"  - Registering: {method} {path}")
                    self.app.add_url_rule(path, view_func=handler, methods=[method])
        logger.info("T2i routes registered.")

    async def list_templates(self):
        """获取所有T2I模板列表"""
        try:
            templates = self.manager.list_templates()
            return jsonify(asdict(Response().ok(data=templates)))
        except Exception as e:
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response

    async def get_template(self, name: str):
        """获取指定名称的T2I模板内容"""
        try:
            content = self.manager.get_template(name)
            return jsonify(asdict(Response().ok(data={"name": name, "content": content})))
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
                response = jsonify(asdict(Response().error("Name and content are required.")))
                response.status_code = 400
                return response
            
            self.manager.create_template(name, content)
            response = jsonify(asdict(Response().ok(data={"name": name}, message="Template created successfully.")))
            response.status_code = 201
            return response
        except FileExistsError:
            response = jsonify(asdict(Response().error("Template with this name already exists.")))
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
            return jsonify(asdict(Response().ok(data={"name": name}, message="Template updated successfully.")))
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
            return jsonify(asdict(Response().ok(message="Template deleted successfully.")))
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

    async def reset_default_template(self):
        """重置默认的'base'模板"""
        logger.info("-> Entering 'reset_default_template' handler for /api/t2i/templates/reset_default")
        try:
            self.manager.reset_default_template()
            logger.info("<- 'reset_default_template' successful.")
            return jsonify(asdict(Response().ok(message="Default template has been reset.")))
        except FileNotFoundError as e:
            logger.error(f"<- 'reset_default_template' failed: Backup file not found. Details: {e}")
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 404
            return response
        except Exception as e:
            logger.error("<- 'reset_default_template' failed with unexpected error.", exc_info=True)
            response = jsonify(asdict(Response().error(str(e))))
            response.status_code = 500
            return response