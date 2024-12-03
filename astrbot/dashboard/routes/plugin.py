import threading, traceback, uuid
from .route import Route, Response, RouteContext
from astrbot.core import logger
from quart import Quart, request
from astrbot.core.plugin.plugin_manager import PluginManager
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

class PluginRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle, plugin_manager: PluginManager) -> None:
        super().__init__(context)
        self.routes = {
            '/plugin/get': ('GET', self.get_plugins),
            '/plugin/install': ('POST', self.install_plugin),
            '/plugin/install-upload': ('POST', self.install_plugin_upload),
            '/plugin/update': ('POST', self.update_plugin),
            '/plugin/uninstall': ('POST', self.uninstall_plugin),
        }
        self.core_lifecycle = core_lifecycle
        self.plugin_manager = plugin_manager
        self.register_routes()
    
    async def get_plugins(self):
        _plugin_resp = []
        for plugin in self.plugin_manager.context.registered_plugins:
            _p = plugin.metadata
            _t = {
                "name": _p.plugin_name,
                "repo": '' if _p.repo is None else _p.repo,
                "author": _p.author,
                "desc": _p.desc,
                "version": _p.version
            }
            _plugin_resp.append(_t)
        return Response().ok(_plugin_resp).__dict__
        
    async def install_plugin(self):
        post_data = await request.json
        repo_url = post_data["url"]
        try:
            logger.info(f"正在安装插件 {repo_url}")
            await self.plugin_manager.install_plugin(repo_url)
            self.core_lifecycle.restart()
            logger.info(f"安装插件 {repo_url} 成功。")
            return Response().ok(None, "安装成功。").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
        
    async def install_plugin_upload(self):
        try:
            file = await request.files
            file = file['file']
            logger.info(f"正在安装用户上传的插件 {file.filename}")
            file_path = f"data/temp/{uuid.uuid4()}.zip"
            await file.save(file_path)
            self.plugin_manager.install_plugin_from_file(file_path)
            logger.info(f"安装插件 {file.filename} 成功")
            self.core_lifecycle.restart()
            return Response().ok(None, "安装成功。").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
        
    async def uninstall_plugin(self):
        post_data = await request.json
        plugin_name = post_data["name"]
        try:
            logger.info(f"正在卸载插件 {plugin_name}")
            self.plugin_manager.uninstall_plugin(plugin_name)
            logger.info(f"卸载插件 {plugin_name} 成功")
            return Response().ok(None, "卸载成功").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).__dict__
        
    async def update_plugin(self):
        post_data = await request.json
        plugin_name = post_data["name"]
        try:
            logger.info(f"正在更新插件 {plugin_name}")
            await self.plugin_manager.update_plugin(plugin_name)
            self.core_lifecycle.restart()
            logger.info(f"更新插件 {plugin_name} 成功，2秒后重启")
            return Response().ok(None, "更新成功，程序将在 2 秒内重启。").__dict__
        except Exception as e:
            logger.error(f"/api/extensions/update: {traceback.format_exc()}")
            return Response().error(str(e)).__dict__