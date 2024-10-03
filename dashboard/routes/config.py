import os, json, threading
from .. import Route, Response
from ..utils.config import *
from quart import Quart, request
from type.types import Context
from type.config import CONFIG_METADATA_2
from util.updator.astrbot_updator import AstrBotUpdator


class ConfigRoute(Route):
    def __init__(self, context: Context, app: Quart, astrbot_updator: AstrBotUpdator) -> None:
        super().__init__(context, app)
        self.config_key_dont_show = ['dashboard', 'config_version']
        self.astrbot_updator = astrbot_updator
        self.routes = {
            '/config/get': ('GET', self.get_configs),
            '/config/astrbot/update': ('POST', self.post_astrbot_configs),
            '/config/plugin/update': ('POST', self.post_extension_configs),
        }
        self.register_routes()

    async def get_configs(self):
        # namespace 为空时返回 AstrBot 配置
        # 否则返回指定 namespace 的插件配置
        namespace = "" if "namespace" not in request.args else request.args["namespace"]
        if not namespace:
            return Response().ok(await self._get_astrbot_config()).__dict__
        return Response().ok(await self._get_extension_config(namespace)).__dict__

    async def post_astrbot_configs(self):
        post_configs = await request.json
        try:
            await self._save_astrbot_configs(post_configs)
            return Response().ok(None, "保存成功~ 机器人将在 3 秒内重启以应用新的配置。").__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__
    
    async def post_extension_configs(self):
        post_configs = await request.json
        try:
            await self._save_extension_configs(post_configs)
            return Response().ok(None, "保存成功~ 机器人将在 3 秒内重启以应用新的配置。").__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__
            
    async def _get_astrbot_config(self):
        config = self.context.config_helper.to_dict()
        for key in self.config_key_dont_show:
            if key in config:
                del config[key]
        return {
            "metadata": CONFIG_METADATA_2,
            "config": config,
        }
            
    async def _get_extension_config(self, namespace: str):
        path = f"data/config/{namespace}.json"
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8-sig") as f:
            return [{
                "config_type": "group",
                "name": namespace + " 插件配置",
                "description": "",
                "body": list(json.load(f).values())
            },]

    async def _save_astrbot_configs(self, post_configs: dict):
        try:
            save_astrbot_config(post_configs, self.context)
            threading.Thread(target=self.astrbot_updator._reboot, args=(3, self.context), daemon=True).start()
        except Exception as e:
            raise e
    
    async def _save_extension_configs(self, post_configs: dict):
        try:
            save_extension_config(post_configs)
            threading.Thread(target=self.astrbot_updator._reboot, args=(3, self.context), daemon=True).start()
        except Exception as e:
            raise e