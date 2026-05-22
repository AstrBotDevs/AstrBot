import copy
import enum
import json
import logging
import os

from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.auth_password import (
    generate_dashboard_password,
    hash_dashboard_password,
    hash_legacy_dashboard_password,
    validate_dashboard_password,
)

from .default import DEFAULT_CONFIG, DEFAULT_VALUE_MAP

ASTRBOT_CONFIG_PATH = os.path.join(get_astrbot_data_path(), "cmd_config.json")
DASHBOARD_INITIAL_PASSWORD_ENV = "ASTRBOT_DASHBOARD_INITIAL_PASSWORD"
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

    config_path: str
    default_config: dict
    schema: dict | None

    def __init__(
        self,
        config_path: str = ASTRBOT_CONFIG_PATH,
        default_config: dict = DEFAULT_CONFIG,
        schema: dict | None = None,
    ) -> None:
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
                object.__setattr__(self, "first_deploy", True)  # 标记第一次部署

        with open(config_path, encoding="utf-8-sig") as f:
            conf_str = f.read()
            # Handle UTF-8 BOM if present
            if conf_str.startswith("\ufeff"):
                conf_str = conf_str[1:]
            conf = json.loads(conf_str)
        dashboard_conf = conf.get("dashboard")
        legacy_dashboard_password_change_required = bool(
            isinstance(dashboard_conf, dict)
            and dashboard_conf.get("password_change_required", False)
        )
        if legacy_dashboard_password_change_required:
            object.__setattr__(
                self,
                "_dashboard_password_change_required_from_config",
                True,
            )
        # 检查配置完整性，并插入
        has_new = self.check_config_integrity(default_config, conf, schema=schema)
        if (
            "dashboard" in conf
            and isinstance(conf["dashboard"], dict)
            and not conf["dashboard"].get("pbkdf2_password")
            and not conf["dashboard"].get("password")
        ):
            self._reset_generated_dashboard_password(conf)
            has_new = True
        elif (
            "dashboard" in conf
            and isinstance(conf["dashboard"], dict)
            and legacy_dashboard_password_change_required
            and conf["dashboard"].get("pbkdf2_password")
        ):
            self._reset_generated_dashboard_password(conf)
            has_new = True
        self.update(conf)
        if has_new:
            self.save_config()

        self.update(conf)

    def _reset_generated_dashboard_password(self, conf: dict) -> None:
        generated_password = self._resolve_initial_dashboard_password()
        conf["dashboard"]["pbkdf2_password"] = hash_dashboard_password(
            generated_password
        )
        conf["dashboard"]["password"] = hash_legacy_dashboard_password(
            generated_password
        )
        conf["dashboard"]["password_storage_upgraded"] = True
        conf["dashboard"]["password_change_required"] = True
        object.__setattr__(
            self,
            "_generated_dashboard_password",
            generated_password,
        )
        object.__setattr__(
            self,
            "_generated_dashboard_password_change_required",
            True,
        )

    @staticmethod
    def _resolve_initial_dashboard_password() -> str:
        env_password = os.environ.get(DASHBOARD_INITIAL_PASSWORD_ENV)
        if env_password is None:
            return generate_dashboard_password()
        validate_dashboard_password(env_password)
        return env_password

    def _config_schema_to_default_config(self, schema: dict) -> dict:
        """将 Schema 转换成 Config"""
        conf = {}

        def _parse_schema(schema: dict, conf: dict) -> None:
            for k, v in schema.items():
                if v["type"] not in DEFAULT_VALUE_MAP:
                    raise TypeError(
                        f"不受支持的配置类型 {v['type']}。支持的类型有：{DEFAULT_VALUE_MAP.keys()}",
                    )
                if "default" in v:
                    default = copy.deepcopy(v["default"])
                else:
                    default = copy.deepcopy(DEFAULT_VALUE_MAP[v["type"]])

                if v["type"] == "object":
                    conf[k] = {}
                    _parse_schema(v["items"], conf[k])
                elif v["type"] == "template_list":
                    fallback = copy.deepcopy(DEFAULT_VALUE_MAP[v["type"]])
                    conf[k], _ = self._sanitize_value_by_schema(
                        default,
                        fallback,
                        v,
                    )
                else:
                    fallback = copy.deepcopy(DEFAULT_VALUE_MAP[v["type"]])
                    conf[k], _ = self._sanitize_value_by_schema(
                        default,
                        fallback,
                        v,
                    )

        _parse_schema(schema, conf)

        return conf

    def _value_matches_options(self, value, meta: dict) -> bool:
        options = meta.get("options")
        if not isinstance(options, list):
            return True
        if value in options:
            return True
        type_ = meta.get("type")
        if "default" not in meta and type_ in DEFAULT_VALUE_MAP:
            return value == DEFAULT_VALUE_MAP[type_]
        return False

    def _sanitize_scalar_by_schema(self, value, default, meta: dict):
        type_ = meta.get("type")
        changed = False

        if type_ == "int":
            if type(value) is int:
                sanitized = value
            elif isinstance(value, str):
                try:
                    sanitized = int(value.strip())
                    changed = True
                except ValueError:
                    return copy.deepcopy(default), True
            elif isinstance(value, float) and value.is_integer():
                sanitized = int(value)
                changed = True
            else:
                return copy.deepcopy(default), True
        elif type_ == "float":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                sanitized = float(value)
                changed = type(value) is int
            elif isinstance(value, str):
                try:
                    sanitized = float(value.strip())
                    changed = True
                except ValueError:
                    return copy.deepcopy(default), True
            else:
                return copy.deepcopy(default), True
        elif type_ in ("string", "text"):
            if not isinstance(value, str):
                return copy.deepcopy(default), True
            sanitized = value
        elif type_ == "bool":
            if type(value) is not bool:
                return copy.deepcopy(default), True
            sanitized = value
        else:
            sanitized = value

        if not self._value_matches_options(sanitized, meta):
            return copy.deepcopy(default), True

        return sanitized, changed

    def _sanitize_list_by_schema(self, value, default, meta: dict):
        if not isinstance(value, list):
            return copy.deepcopy(default), True

        options = meta.get("options")
        if not isinstance(options, list):
            return value, False

        filtered = [item for item in value if item in options]
        if filtered == value:
            return value, False

        if filtered:
            return filtered, True
        return copy.deepcopy(default), True

    def _sanitize_template_list_by_schema(self, value, default, meta: dict):
        if not isinstance(value, list):
            return copy.deepcopy(default), True

        templates = meta.get("templates")
        if not isinstance(templates, dict):
            templates = {}

        sanitized_entries = []
        changed = False

        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                changed = True
                continue

            template_key = item.get("__template_key") or item.get("template")
            template_meta = templates.get(template_key)
            if not template_key or not isinstance(template_meta, dict):
                changed = True
                continue

            template_items = template_meta.get("items", {})
            if not isinstance(template_items, dict):
                template_items = {}

            entry_default = self._config_schema_to_default_config(template_items)
            entry_data = {
                key: item_value
                for key, item_value in item.items()
                if key not in {"__template_key", "template"}
            }
            entry_changed = self.check_config_integrity(
                entry_default,
                entry_data,
                path=f"[{idx}]",
                schema=template_items,
            )

            sanitized_entry = {"__template_key": template_key}
            sanitized_entry.update(entry_data)
            sanitized_entries.append(sanitized_entry)

            if item.get("__template_key") != template_key:
                entry_changed = True
            if set(item.keys()) - set(sanitized_entry.keys()) - {"template"}:
                entry_changed = True
            changed |= entry_changed

        if sanitized_entries != value:
            changed = True
        if not sanitized_entries and value:
            return copy.deepcopy(default), True
        return sanitized_entries, changed

    def _sanitize_value_by_schema(self, value, default, meta: dict | None):
        if not isinstance(meta, dict) or "type" not in meta:
            return value, False

        type_ = meta["type"]
        default = copy.deepcopy(default)

        if value is None:
            return default, True

        if type_ == "object":
            if not isinstance(value, dict):
                return default, True
            items = meta.get("items", {})
            if not isinstance(items, dict):
                items = {}
            nested_value = copy.deepcopy(value)
            changed = self.check_config_integrity(
                default,
                nested_value,
                schema=items,
            )
            return nested_value, changed

        if type_ == "dict":
            if not isinstance(value, dict):
                return default, True
            return value, False

        if type_ == "template_list":
            return self._sanitize_template_list_by_schema(value, default, meta)

        if type_ == "list":
            return self._sanitize_list_by_schema(value, default, meta)

        if type_ == "file":
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                return default, True
            return value, False

        return self._sanitize_scalar_by_schema(value, default, meta)

    def check_config_integrity(
        self,
        refer_conf: dict,
        conf: dict,
        path="",
        schema: dict | None = None,
    ):
        """检查配置完整性，如果有新的配置项或顺序不一致则返回 True"""
        has_new = False

        # 创建一个新的有序字典以保持参考配置的顺序
        new_conf = {}

        # 先按照参考配置的顺序添加配置项
        for key, value in refer_conf.items():
            item_schema = schema.get(key) if isinstance(schema, dict) else None
            if key not in conf:
                # 配置项不存在，插入默认值
                path_ = path + "." + key if path else key
                logger.info("Config key missing; added default.")
                new_conf[key] = copy.deepcopy(value)
                has_new = True
            elif conf[key] is None:
                # 配置项为 None，使用默认值
                new_conf[key] = copy.deepcopy(value)
                has_new = True
            elif isinstance(item_schema, dict):
                sanitized_value, value_changed = self._sanitize_value_by_schema(
                    conf[key],
                    value,
                    item_schema,
                )
                if value_changed:
                    logger.info("Config key incompatible with schema; sanitized.")
                new_conf[key] = sanitized_value
                has_new |= value_changed
            elif isinstance(value, dict):
                # 递归检查子配置项
                if not isinstance(conf[key], dict):
                    # 类型不匹配，使用默认值
                    new_conf[key] = copy.deepcopy(value)
                    has_new = True
                else:
                    # 递归检查并同步顺序
                    child_has_new = self.check_config_integrity(
                        value,
                        conf[key],
                        path + "." + key if path else key,
                    )
                    new_conf[key] = conf[key]
                    has_new |= child_has_new
            else:
                # 直接使用现有配置
                new_conf[key] = conf[key]

        # 检查是否存在参考配置中没有的配置项
        for key in list(conf.keys()):
            if key not in refer_conf:
                path_ = path + "." + key if path else key
                logger.info("Config key removed: %s", path_)
                has_new = True

        # 顺序不一致也算作变更
        if list(conf.keys()) != list(new_conf.keys()):
            if path:
                logger.info("Config key order fixed: %s", path)
            else:
                logger.info("Config key order fixed")
            has_new = True

        # 更新原始配置
        conf.clear()
        conf.update(new_conf)

        return has_new

    def save_config(self, replace_config: dict | None = None) -> None:
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

    def __delattr__(self, key) -> None:
        try:
            del self[key]
            self.save_config()
        except KeyError:
            raise AttributeError(f"没有找到 Key: '{key}'")

    def __setattr__(self, key, value) -> None:
        self[key] = value

    def check_exist(self) -> bool:
        if not self.config_path:  # 加判空
            return False
        return os.path.exists(self.config_path)
