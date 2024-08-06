from . import DashBoardData
from util.cmd_config import AstrBotConfig
from dataclasses import dataclass, asdict
from util.plugin_dev.api.v1.config import update_config
from SparkleLogging.utils.core import LogManager
from logging import Logger
from type.types import Context
from type.config import CONFIG_METADATA_2

logger: Logger = LogManager.GetLogger(log_name='astrbot')


class DashBoardHelper():
    def __init__(self, context: Context):
        self.context = context
        self.config_key_dont_show = ['dashboard', 'config_version']

    def validate_config(self, data):
        errors = []
        # 递归验证数据
        def validate(data, path=""):
            for key, meta in CONFIG_METADATA_2.items():
                if key not in data:
                    if key not in self.config_key_dont_show:
                        # 这些key不会传给前端，所以不需要验证
                        errors.append(f"Missing key: {path}{key}")
                    continue
                value = data[key]
                if meta["type"] == "int" and not isinstance(value, int):
                    errors.append(f"Invalid type for {path}{key}: expected int, got {type(value).__name__}")
                elif meta["type"] == "bool" and not isinstance(value, bool):
                    errors.append(f"Invalid type for {path}{key}: expected bool, got {type(value).__name__}")
                elif meta["type"] == "string" and not isinstance(value, str):
                    errors.append(f"Invalid type for {path}{key}: expected string, got {type(value).__name__}")
                elif meta["type"] == "list" and not isinstance(value, list):
                    errors.append(f"Invalid type for {path}{key}: expected list, got {type(value).__name__}")
                    for item in value:
                        validate(item, meta["items"], path=f"{path}{key}.")
                elif meta["type"] == "dict" and not isinstance(value, dict):
                    errors.append(f"Invalid type for {path}{key}: expected dict, got {type(value).__name__}")
                    validate(value, meta["items"], path=f"{path}{key}.")
        validate(data)
        
        # hardcode warning
        data['config_version'] = self.context.config_helper.config_version
        data['dashboard'] = asdict(self.context.config_helper.dashboard)
        
        return errors

    def save_astrbot_config(self, post_config: dict):
        '''验证并保存配置'''
        errors = self.validate_config(post_config)
        if errors:
            raise ValueError(f"格式校验未通过: {errors}")
        self.context.config_helper.flush_config(post_config)
        
    def save_extension_config(self, post_config: list, namespace: str):
        pass
        # update_config(namespace, key, value)