import asyncio
import copy
import enum
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from astrbot.core.config.agent_runner import normalize_agent_runner_for_load
from astrbot.core.config.agent_runner_migration import migrate_config_on_load
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.auth_password import (
    generate_dashboard_password,
    hash_dashboard_password,
    validate_dashboard_password,
)

from .default import DEFAULT_CONFIG, DEFAULT_VALUE_MAP

ASTRBOT_CONFIG_PATH = os.path.join(get_astrbot_data_path(), "cmd_config.json")
DASHBOARD_INITIAL_PASSWORD_ENV = "ASTRBOT_DASHBOARD_INITIAL_PASSWORD"
DASHBOARD_RESET_PASSWORD_ENV = "ASTRBOT_RESET_DASHBOARD_PASSWORD"
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
    _save_state_lock: threading.Lock
    _save_commit_lock: threading.Lock
    _save_revision: int
    _save_committed_revision: int

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
        object.__setattr__(self, "_save_state_lock", threading.Lock())
        object.__setattr__(self, "_save_commit_lock", threading.Lock())
        object.__setattr__(self, "_save_revision", 0)
        object.__setattr__(self, "_save_committed_revision", 0)

        default_config = self._resolve_default_config(default_config, schema)
        self._ensure_config_file(default_config)
        conf = self._load_config_dict(config_path)
        dashboard_conf = conf.get("dashboard")
        stored_dashboard_password_change_required = bool(
            isinstance(dashboard_conf, dict)
            and dashboard_conf.get("password_change_required", False)
        )
        if stored_dashboard_password_change_required:
            object.__setattr__(
                self,
                "_dashboard_password_change_required_from_config",
                True,
            )
        # 检查配置完整性，并插入
        has_new = self._migrate_openai_chat_completions_type(conf)
        if default_config is DEFAULT_CONFIG:
            has_new |= migrate_config_on_load(conf, Path(config_path))
            normalized_runner = normalize_agent_runner_for_load(
                conf.get("agent_runner")
            )
            if conf.get("agent_runner") != normalized_runner:
                conf["agent_runner"] = normalized_runner
                has_new = True
        has_new |= self.check_config_integrity(default_config, conf)
        if self._should_reset_dashboard_password(conf):
            self._reset_generated_dashboard_password(conf)
            has_new = True
        self.update(conf)
        if has_new:
            self.save_config()

        self.update(conf)

    @staticmethod
    def _migrate_openai_chat_completions_type(conf: dict) -> bool:
        """Migrate the persisted OpenAI Chat Completions adapter identifier once."""
        migrated = False
        for key in ("provider_sources", "provider"):
            configs = conf.get(key)
            if not isinstance(configs, list):
                continue
            for config in configs:
                if (
                    isinstance(config, dict)
                    and config.get("type") == "openai_chat_completion"
                ):
                    config["type"] = "openai_chat_completions"
                    migrated = True
        if migrated:
            logger.info(
                "Migrated OpenAI Chat Completions provider type to the current identifier."
            )
        return migrated

    def _resolve_default_config(
        self, default_config: dict, schema: dict | None
    ) -> dict:
        if schema is not None:
            return self._config_schema_to_default_config(schema)
        return default_config

    def _ensure_config_file(self, default_config: dict) -> None:
        if self.check_exist():
            return
        self.update(copy.deepcopy(default_config))
        self.save_config(indent=4)
        object.__setattr__(self, "first_deploy", True)

    @staticmethod
    def _load_config_dict(config_path: str) -> dict:
        with open(config_path, encoding="utf-8-sig") as f:
            conf_str = f.read()
        if conf_str.startswith("\ufeff"):
            conf_str = conf_str[1:]
        return json.loads(conf_str)

    def _should_reset_dashboard_password(self, conf: dict) -> bool:
        dashboard_conf = conf.get("dashboard")
        if not isinstance(dashboard_conf, dict):
            return False
        if self._consume_reset_dashboard_password_flag():
            return True
        if not dashboard_conf.get("pbkdf2_password") and not dashboard_conf.get(
            "password"
        ):
            return True
        return False

    def _reset_generated_dashboard_password(self, conf: dict) -> None:
        generated_password = self._resolve_initial_dashboard_password()
        conf["dashboard"]["pbkdf2_password"] = hash_dashboard_password(
            generated_password
        )
        conf["dashboard"]["password"] = ""
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
    def _consume_reset_dashboard_password_flag() -> bool:
        raw_value = os.environ.pop(DASHBOARD_RESET_PASSWORD_ENV, "")
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}

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
                    default = v["default"]
                else:
                    default = DEFAULT_VALUE_MAP[v["type"]]

                if v["type"] == "object":
                    conf[k] = {}
                    _parse_schema(v["items"], conf[k])
                elif v["type"] == "template_list":
                    conf[k] = copy.deepcopy(default)
                else:
                    conf[k] = copy.deepcopy(default)

        _parse_schema(schema, conf)

        return conf

    def check_config_integrity(self, refer_conf: dict, conf: dict, path=""):
        """检查配置完整性，如果有新的配置项或顺序不一致则返回 True"""
        has_new = False

        # 创建一个新的有序字典以保持参考配置的顺序
        new_conf = {}

        has_new |= self._sync_config_against_reference(
            refer_conf=refer_conf,
            conf=conf,
            new_conf=new_conf,
            path=path,
        )
        has_new |= self._remove_unknown_config_keys(
            refer_conf=refer_conf,
            conf=conf,
            path=path,
        )
        has_new |= self._fix_config_key_order(conf=conf, new_conf=new_conf, path=path)

        # 更新原始配置
        conf.clear()
        conf.update(new_conf)

        return has_new

    def _sync_config_against_reference(
        self,
        *,
        refer_conf: dict,
        conf: dict,
        new_conf: dict,
        path: str,
    ) -> bool:
        has_new = False
        for key, value in refer_conf.items():
            current_path = path + "." + key if path else key
            if key not in conf:
                logger.info("Config key missing; added default.")
                new_conf[key] = copy.deepcopy(value)
                has_new = True
                continue
            if conf[key] is None:
                new_conf[key] = copy.deepcopy(value)
                has_new = True
                continue
            if not isinstance(value, dict):
                new_conf[key] = conf[key]
                continue
            if not isinstance(conf[key], dict):
                new_conf[key] = copy.deepcopy(value)
                has_new = True
                continue
            if current_path == "agent_runner.config":
                # Runner config is normalized according to runner_type when saved.
                new_conf[key] = conf[key]
                continue
            child_has_new = self.check_config_integrity(value, conf[key], current_path)
            new_conf[key] = conf[key]
            has_new |= child_has_new
        return has_new

    def _remove_unknown_config_keys(
        self,
        *,
        refer_conf: dict,
        conf: dict,
        path: str,
    ) -> bool:
        has_new = False
        for key in list(conf.keys()):
            if key in refer_conf:
                continue
            current_path = path + "." + key if path else key
            logger.info("Config key removed: %s", current_path)
            has_new = True
        return has_new

    def _fix_config_key_order(self, *, conf: dict, new_conf: dict, path: str) -> bool:
        if list(conf.keys()) == list(new_conf.keys()):
            return False
        if path:
            logger.info("Config key order fixed: %s", path)
        else:
            logger.info("Config key order fixed")
        return True

    def save_config(
        self, replace_config: dict | None = None, *, indent: int = 2
    ) -> None:
        """Persist the current configuration synchronously.

        Args:
            replace_config: Values to merge into the configuration before saving.
            indent: Number of spaces used to indent the JSON output.
        """
        snapshot, revision = self._prepare_config_snapshot(replace_config)
        self._write_config_snapshot(snapshot, revision, indent)

    async def save_config_async(
        self, replace_config: dict | None = None, *, indent: int = 2
    ) -> bool:
        """Persist a stable configuration snapshot without blocking the event loop.

        Args:
            replace_config: Values to merge into the configuration before saving.
            indent: Number of spaces used to indent the JSON output.

        Returns:
            Whether this snapshot replaced the persisted configuration.
        """
        snapshot, revision = self._prepare_config_snapshot(replace_config)
        return await asyncio.to_thread(
            self._write_config_snapshot,
            snapshot,
            revision,
            indent,
        )

    def _prepare_config_snapshot(
        self,
        replace_config: dict | None,
    ) -> tuple[dict, int]:
        """Create an isolated snapshot and allocate its save revision."""
        with self._save_state_lock:
            if replace_config:
                self.update(replace_config)
            snapshot = copy.deepcopy(dict(self))
            revision = self._save_revision + 1
            object.__setattr__(self, "_save_revision", revision)
        return snapshot, revision

    def _write_config_snapshot(
        self,
        snapshot: dict,
        revision: int,
        indent: int,
    ) -> bool:
        """Write a prepared snapshot unless a newer one was already committed."""
        directory = os.path.dirname(os.path.abspath(self.config_path)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            dir=directory,
            prefix=f".{os.path.basename(self.config_path)}.",
            suffix=".tmp",
        )
        committed = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                json.dump(snapshot, f, indent=indent, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            with self._save_commit_lock:
                if revision > self._save_committed_revision:
                    os.replace(temp_path, self.config_path)
                    object.__setattr__(self, "_save_committed_revision", revision)
                    committed = True
        finally:
            if not committed:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
        return committed

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
