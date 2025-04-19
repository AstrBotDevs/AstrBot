import os
import json
import logging
import enum
from .default import DEFAULT_CONFIG, DEFAULT_VALUE_MAP
from typing import Dict

ASTRBOT_CONFIG_PATH = "data/cmd_config.json"
logger = logging.getLogger("astrbot")


class RateLimitStrategy(enum.Enum):
    STALL = "stall"
    DISCARD = "discard"


class AstrBotConfig(dict):
    """从配置文件中加载的配置，支持直接通过点号操作符访问根配置项。

    - 初始化时会将传入的 default_config 与配置文件进行比对，如果配置文件中缺少配置项则会自动插入默认值并进行一次写入操作。会递归检查配置项。
    - 如果配置文件路径对应的文件不存在，则会自动创建并写入默认配置。
    - 如果传入了 schema，将会通过 schema 解析出 default_config，此时传入的 default_config 会被忽略。
    """

    def __init__(
        self,
        config_path: str = ASTRBOT_CONFIG_PATH,
        default_config: dict = DEFAULT_CONFIG,
        schema: dict = None,
    ):
        super().__init__()

        # 调用父类的 __setattr__ 方法，防止保存配置时将此属性写入配置文件
        object.__setattr__(self, "config_path", config_path)
        object.__setattr__(self, "default_config", default_config)
        object.__setattr__(self, "schema", schema)

        if schema:
            default_config = self._config_schema_to_default_config(schema)

        if not self.check_exist():
            """不存在时载入默认配置"""
            with open(config_path, "w", encoding="utf-8-sig") as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)

        with open(config_path, "r", encoding="utf-8-sig") as f:
            conf_str = f.read()
            if conf_str.startswith("/ufeff"):  # remove BOM
                conf_str = conf_str.encode("utf8")[3:].decode("utf8")
            conf = json.loads(conf_str)

        # 检查配置完整性，并插入
        has_new = self.check_config_integrity(default_config, conf)
        self.update(conf)
        if has_new:
            self.save_config()

        self.update(conf)

    def _config_schema_to_default_config(self, schema: dict) -> dict:
        """将 Schema 转换成 Config"""
        conf = {}

        def _parse_schema(schema: dict, conf: dict):
            for k, v in schema.items():
                if v["type"] not in DEFAULT_VALUE_MAP:
                    raise TypeError(
                        f"不受支持的配置类型 {v['type']}。支持的类型有：{DEFAULT_VALUE_MAP.keys()}"
                    )
                if "default" in v:
                    default = v["default"]
                else:
                    default = DEFAULT_VALUE_MAP[v["type"]]

                if v["type"] == "object":
                    conf[k] = {}
                    _parse_schema(v["items"], conf[k])
                else:
                    conf[k] = default

        _parse_schema(schema, conf)

        return conf

    def check_config_integrity(self, refer_conf: Dict, conf: Dict, path=""):
        """检查配置完整性，如果有新的配置项则返回 True"""
        has_new = False
        for key, value in refer_conf.items():
            if key not in conf:
                # logger.info(f"检查到配置项 {path + "." + key if path else key} 不存在，已插入默认值 {value}")
                path_ = path + "." + key if path else key
                logger.info(f"检查到配置项 {path_} 不存在，已插入默认值 {value}")
                conf[key] = value
                has_new = True
            else:
                if conf[key] is None:
                    conf[key] = value
                    has_new = True
                elif isinstance(value, dict):
                    has_new |= self.check_config_integrity(
                        value, conf[key], path + "." + key if path else key
                    )
        return has_new

    def save_config(self, replace_config: Dict = None):
        """将配置写入文件

        如果传入 replace_config，则将配置替换为 replace_config
        """
        if replace_config:
            self.update(replace_config)
        with open(self.config_path, "w", encoding="utf-8-sig") as f:
            json.dump(self, f, indent=2, ensure_ascii=False)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            return None

    def __delattr__(self, key):
        try:
            del self[key]
            self.save_config()
        except KeyError:
            raise AttributeError(f"没有找到 Key: '{key}'")

    def __setattr__(self, key, value):
        self[key] = value

    def check_exist(self) -> bool:
        return os.path.exists(self.config_path)
