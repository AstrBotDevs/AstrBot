import os, json
from .route import Route, Response
from quart import Quart, request
from core.config.default import CONFIG_METADATA_2, DEFAULT_VALUE_MAP
from core.config.astrbot_config import AstrBotConfig
from core.plugin.config import update_config
from core.core_lifecycle import AstrBotCoreLifecycle
from dataclasses import asdict

def try_cast(value: str, type_: str):
    if type_ == "int" and value.isdigit():
        return int(value)
    elif type_ == "float" and isinstance(value, str) \
        and value.replace(".", "", 1).isdigit():
        return float(value)
    elif type_ == "float" and isinstance(value, int):
        return float(value)

def validate_config(data, config: AstrBotConfig):
    errors = []
    def validate(data, metadata=CONFIG_METADATA_2, path=""):
        for key, meta in metadata.items():
            if key not in data:
                continue
            value = data[key]
            # null 转换
            if value is None:
                data[key] = DEFAULT_VALUE_MAP(meta["type"])
                continue
            # 递归验证
            if meta["type"] == "list" and isinstance(value, list):
                for item in value:
                    validate(item, meta["items"], path=f"{path}{key}.")
            elif meta["type"] == "object" and isinstance(value, dict):
                validate(value, meta["items"], path=f"{path}{key}.")

            if meta["type"] == "int" and not isinstance(value, int):
                casted = try_cast(value, "int")
                if casted is None:
                    errors.append(f"错误的类型 {path}{key}: 期望是 int, 得到了 {type(value).__name__}")
                data[key] = casted
            elif meta["type"] == "float" and not isinstance(value, float):
                casted = try_cast(value, "float")
                if casted is None:
                    errors.append(f"错误的类型 {path}{key}: 期望是 float, 得到了 {type(value).__name__}")
                data[key] = casted
            elif meta["type"] == "bool" and not isinstance(value, bool):
                errors.append(f"错误的类型 {path}{key}: 期望是 bool, 得到了 {type(value).__name__}")
            elif meta["type"] in ["string", "text"] and not isinstance(value, str):
                errors.append(f"错误的类型 {path}{key}: 期望是 string, 得到了 {type(value).__name__}")
            elif meta["type"] == "list" and not isinstance(value, list):
                errors.append(f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}")
            elif meta["type"] == "object" and not isinstance(value, dict):
                errors.append(f"错误的类型 {path}{key}: 期望是 dict, 得到了 {type(value).__name__}")
                validate(value, meta["items"], path=f"{path}{key}.")
    validate(data)
    
    # hardcode warning
    data['config_version'] = config.config_version
    data['dashboard'] = asdict(config.dashboard)
    
    return errors

def save_astrbot_config(post_config: dict, config: AstrBotConfig):
    '''验证并保存配置'''
    errors = validate_config(post_config, config)
    if errors:
        raise ValueError(f"格式校验未通过: {errors}")
    config.flush_config(post_config)
    
def save_extension_config(post_config: dict):
    if 'namespace' not in post_config:
        raise ValueError("Missing key: namespace")
    if 'config' not in post_config:
        raise ValueError("Missing key: config")

    namespace = post_config['namespace']
    config: list = post_config['config'][0]['body']
    for item in config:
        key = item['path']
        value = item['value']
        typ = item['val_type']
        if typ == 'int':
            if not value.isdigit():
                raise ValueError(f"错误的类型 {namespace}.{key}: 期望是 int, 得到了 {type(value).__name__}")
            value = int(value)
        update_config(namespace, key, value)

class ConfigRoute(Route):
    def __init__(self, config: AstrBotConfig, app: Quart, core_lifecycle: AstrBotCoreLifecycle) -> None:
        super().__init__(config, app)
        self.config_key_dont_show = ['dashboard', 'config_version']
        self.core_lifecycle = core_lifecycle
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
            return Response().ok(None, "保存成功~ 机器人正在重载配置。").__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__
    
    async def post_extension_configs(self):
        post_configs = await request.json
        try:
            await self._save_extension_configs(post_configs)
            return Response().ok(None, "保存成功~ 机器人正在重载配置。").__dict__
        except Exception as e:
            return Response().error(str(e)).__dict__
            
    async def _get_astrbot_config(self):
        config = self.config.to_dict()
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
            save_astrbot_config(post_configs, self.config)
            self.core_lifecycle.restart()
        except Exception as e:
            raise e
    
    async def _save_extension_configs(self, post_configs: dict):
        try:
            save_extension_config(post_configs)
            self.core_lifecycle.restart()
        except Exception as e:
            raise e