import copy
import enum
import json
import logging
import os
from typing import Any

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
DASHBOARD_RESET_PASSWORD_ENV = "ASTRBOT_DASHBOARD_RESET_PASSWORD"
logger = logging.getLogger("astrbot")

CORE_COMPUTER_RUNTIME_IDS = {"local", "local_sandboxed", "sandbox", "none"}


def _is_config_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


_SCHEMA_TYPE_VALIDATORS = {
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": _is_config_number,
    "bool": lambda v: isinstance(v, bool),
    "string": lambda v: isinstance(v, str),
    "text": lambda v: isinstance(v, str),
    "list": lambda v: isinstance(v, list),
    "file": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "dict": lambda v: isinstance(v, dict),
    "template_list": lambda v: isinstance(v, list),
}


def _validate_schema_default(field: str, typ: str, default) -> None:
    if not _SCHEMA_TYPE_VALIDATORS[typ](default):
        raise TypeError(f"配置项 {field} 的 default 与类型 {typ} 不匹配")


def _validate_schema_slider(field: str, typ: str, slider: dict) -> None:
    if typ not in ("int", "float"):
        raise TypeError(f"配置项 {field} 只有 int/float 类型支持 slider")
    if not isinstance(slider, dict) or not all(
        _is_config_number(slider.get(key)) for key in ("min", "max", "step")
    ):
        raise TypeError(
            f"配置项 {field} 的 slider 必须包含数字 min/max/step",
        )


def _validate_config_schema_item(field: str, item: dict) -> None:
    typ = item["type"]
    if typ not in DEFAULT_VALUE_MAP:
        raise TypeError(
            f"不受支持的配置类型 {typ}。支持的类型有：{DEFAULT_VALUE_MAP.keys()}",
        )
    if "options" in item and not isinstance(item["options"], list):
        raise TypeError(f"配置项 {field} 的 options 必须是列表")
    if "obvious_hint" in item and not isinstance(item["obvious_hint"], bool):
        raise TypeError(f"配置项 {field} 的 obvious_hint 必须是布尔值")
    if "slider" in item:
        _validate_schema_slider(field, typ, item["slider"])
    if typ == "object" and not isinstance(item.get("items"), dict):
        raise TypeError(f"配置项 {field} 的 items 必须是对象")
    default = item["default"] if "default" in item else DEFAULT_VALUE_MAP[typ]
    _validate_schema_default(field, typ, default)
    if typ == "object":
        for child_key, child_item in item["items"].items():
            _validate_config_schema_item(f"{field}.{child_key}", child_item)


class RateLimitStrategy(enum.Enum):
    STALL = "stall"
    DISCARD = "discard"


class AstrBotConfig(dict):
    """从配置文件中加载的配置,支持直接通过点号操作符访问根配置项｡

    - 初始化时会将传入的 default_config 与配置文件进行比对,如果配置文件中缺少配置项则会自动插入默认值并进行一次写入操作｡会递归检查配置项｡
    - 如果配置文件路径对应的文件不存在,则会自动创建并写入默认配置｡
    - 如果传入了 schema,将会通过 schema 解析出 default_config,此时传入的 default_config 会被忽略｡
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

        # 调用父类的 __setattr__ 方法,防止保存配置时将此属性写入配置文件
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
            conf = copy.deepcopy(default_config)
        else:
            with open(config_path, encoding="utf-8-sig") as f:
                conf_str = f.read()
                # Handle UTF-8 BOM if present
                if conf_str.startswith("\ufeff"):
                    conf_str = conf_str[1:]
                if not conf_str:
                    raise OSError(f"文件 {config_path} 为空, 请手动处理...")
                try:
                    conf = json.loads(conf_str)
                except Exception as e:
                    logger.error(f"读取文件失败 {config_path}: {e}")
                    raise e

        dashboard_conf = conf.get("dashboard")
        dashboard_reset_requested = self._is_dashboard_password_reset_requested()
        legacy_dashboard_password_change_required = bool(
            isinstance(dashboard_conf, dict)
            and dashboard_conf.get("password_change_required", False),
        )
        if legacy_dashboard_password_change_required:
            object.__setattr__(
                self,
                "_dashboard_password_change_required_from_config",
                True,
            )
        config_migrated = self._migrate_legacy_config(conf)
        # 检查配置完整性，并插入
        has_new = self.check_config_integrity(default_config, conf, schema=schema)
        if (
            "dashboard" in conf
            and isinstance(conf["dashboard"], dict)
            and (
                dashboard_reset_requested
                or (
                    not conf["dashboard"].get("pbkdf2_password")
                    and not conf["dashboard"].get("password")
                )
            )
        ):
            self._reset_generated_dashboard_password(conf)
            if dashboard_reset_requested:
                os.environ[DASHBOARD_RESET_PASSWORD_ENV] = "0"
            has_new = True
        self.update(conf)
        if config_migrated:
            has_new = True
        if has_new:
            self.save_config()

    def _migrate_legacy_config(self, conf: dict) -> bool:
        changed = False
        provider_settings = conf.get("provider_settings")
        if isinstance(provider_settings, dict):
            changed |= self._migrate_legacy_computer_runtime(provider_settings)
        return changed

    @staticmethod
    def _migrate_legacy_computer_runtime(provider_settings: dict) -> bool:
        runtime = provider_settings.get("computer_use_runtime")
        if not isinstance(runtime, str) or runtime in CORE_COMPUTER_RUNTIME_IDS:
            return False

        sandbox_config = provider_settings.get("sandbox")
        if not isinstance(sandbox_config, dict):
            sandbox_config = {}
            provider_settings["sandbox"] = sandbox_config

        if not isinstance(sandbox_config.get("booter"), str) or not sandbox_config.get(
            "booter",
        ):
            sandbox_config["booter"] = runtime
        provider_settings["computer_use_runtime"] = "sandbox"
        return True

    def _reset_generated_dashboard_password(self, conf: dict) -> None:
        generated_password = self._resolve_initial_dashboard_password()
        conf["dashboard"]["pbkdf2_password"] = hash_dashboard_password(
            generated_password,
        )
        conf["dashboard"]["password"] = hash_legacy_dashboard_password(
            generated_password,
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

    @staticmethod
    def _is_dashboard_password_reset_requested() -> bool:
        return os.environ.get(DASHBOARD_RESET_PASSWORD_ENV, "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _config_schema_to_default_config(self, schema: dict) -> dict:
        """将 Schema 转换成 Config"""
        conf: dict[str, Any] = {}

        def _parse_schema(schema: dict, conf: dict) -> None:
            for k, v in schema.items():
                _validate_config_schema_item(k, v)
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
                        path=k,
                    )
                else:
                    fallback = copy.deepcopy(DEFAULT_VALUE_MAP[v["type"]])
                    conf[k], _ = self._sanitize_value_by_schema(
                        default,
                        fallback,
                        v,
                        path=k,
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
                    return default, True
            elif isinstance(value, float) and value.is_integer():
                sanitized = int(value)
                changed = True
            else:
                return default, True
        elif type_ == "float":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                sanitized = float(value)
                changed = type(value) is int
            elif isinstance(value, str):
                try:
                    sanitized = float(value.strip())
                    changed = True
                except ValueError:
                    return default, True
            else:
                return default, True
        elif type_ in ("string", "text"):
            if not isinstance(value, str):
                return default, True
            sanitized = value
        elif type_ == "bool":
            if type(value) is not bool:
                return default, True
            sanitized = value
        else:
            sanitized = value

        if not self._value_matches_options(sanitized, meta):
            return default, True

        return sanitized, changed

    def _sanitize_list_by_schema(self, value, default, meta: dict):
        if not isinstance(value, list):
            return default, True

        options = meta.get("options")
        if not isinstance(options, list):
            return value, False

        filtered = [item for item in value if item in options]
        if filtered == value:
            return value, False

        if filtered:
            return filtered, True
        return default, True

    def _sanitize_template_list_by_schema(
        self,
        value,
        default,
        meta: dict,
        path="",
    ):
        if not isinstance(value, list):
            return default, True

        templates = meta.get("templates")
        if not isinstance(templates, dict):
            templates = {}

        sanitized_entries = []
        changed = False

        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                changed = True
                logger.warning(
                    "Dropping non-dict entry from template_list at index %d.",
                    idx,
                )
                continue

            template_key = item.get("__template_key") or item.get("template")
            template_meta = templates.get(template_key)
            if not template_key:
                changed = True
                logger.warning(
                    "Dropping template_list entry at index %d: missing template key.",
                    idx,
                )
                continue
            if not isinstance(template_meta, dict):
                changed = True
                logger.warning(
                    "Dropping template_list entry at index %d: unknown template key.",
                    idx,
                )
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
                path=f"{path}[{idx}]" if path else f"[{idx}]",
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
            return default, True
        return sanitized_entries, changed

    def _sanitize_value_by_schema(self, value, default, meta: dict | None, path=""):
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
                path=path,
                schema=items,
            )
            return nested_value, changed

        if type_ == "dict":
            # dict is an opaque user mapping; object is recursively schema-defined.
            if not isinstance(value, dict):
                return default, True
            return value, False

        if type_ == "template_list":
            return self._sanitize_template_list_by_schema(value, default, meta, path)

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
            path_ = path + "." + key if path else key
            item_schema = schema.get(key) if isinstance(schema, dict) else None
            if key not in conf:
                # 配置项不存在，插入默认值
                logger.info("Config key missing; added default.")
                new_conf[key] = copy.deepcopy(value)
                has_new = True
            elif conf[key] is None:
                # 配置项为 None，使用默认值
                logger.info("Config key is None; added default.")
                new_conf[key] = copy.deepcopy(value)
                has_new = True
            elif isinstance(item_schema, dict):
                sanitized_value, value_changed = self._sanitize_value_by_schema(
                    conf[key],
                    value,
                    item_schema,
                    path=path_,
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

        # 检查不在参考配置中的项：如果在动态白名单中则保留，否则删除
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

        如果传入 replace_config,则将配置替换为 replace_config
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
        except KeyError as err:
            raise AttributeError(f"没有找到 Key: '{key}'") from err

    def __setattr__(self, key, value) -> None:
        self[key] = value

    def check_exist(self) -> bool:
        if not self.config_path:  # 加判空
            return False
        return os.path.exists(self.config_path)
