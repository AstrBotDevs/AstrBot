from __future__ import annotations

import os
import re

from astrbot.core.utils.astrbot_path import get_astrbot_config_path

from .astrbot_config import AstrBotConfig

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_name(value: str) -> str:
    value = (value or "").strip().lower()
    value = value.replace("/", "_").replace("\\", "_")
    value = _SAFE_NAME_RE.sub("_", value)
    return value or "unknown"


def _build_node_config_path(
    node_name: str,
    chain_id: str,
    node_uuid: str,
) -> str:
    plugin_key = _sanitize_name(node_name)
    chain_key = _sanitize_name(chain_id)
    uuid_key = _sanitize_name(node_uuid)
    filename = f"node_{plugin_key}_{chain_key}_{uuid_key}.json"
    os.makedirs(get_astrbot_config_path(), exist_ok=True)
    return os.path.join(get_astrbot_config_path(), filename)


class AstrBotNodeConfig(AstrBotConfig):
    """Node config - extends AstrBotConfig with chain-specific path.

    Node config is chain-scoped and shared across config_id.
    This class reuses AstrBotConfig's schema parsing, integrity checking,
    and persistence logic, only overriding the config path.
    """

    node_name: str
    chain_id: str
    node_uuid: str

    _cache: dict[tuple[str, str, str], AstrBotNodeConfig] = {}

    def __init__(
        self,
        node_name: str,
        chain_id: str,
        node_uuid: str,
        schema: dict | None = None,
    ):
        # Store node identifiers before parent init
        object.__setattr__(self, "node_name", node_name)
        object.__setattr__(self, "chain_id", chain_id)
        object.__setattr__(self, "node_uuid", node_uuid)

        # Keep behavior aligned with Star plugin config:
        # if schema is not declared, do not create a persisted config file.
        if schema is not None:
            config_path = _build_node_config_path(node_name, chain_id, node_uuid)
        else:
            config_path = ""

        # Initialize with empty default_config, schema will generate defaults
        super().__init__(
            config_path=config_path,
            default_config={},
            schema=schema,
        )

    def check_exist(self) -> bool:
        """Override to handle empty config_path case."""
        if not self.config_path:
            return True  # Skip file operations if no path
        return super().check_exist()

    def save_config(self, replace_config: dict | None = None):
        """Override to handle empty config_path case."""
        if not self.config_path:
            return
        if replace_config:
            self.update(replace_config)
        super().save_config()

    @classmethod
    def get_cached(
        cls,
        node_name: str,
        chain_id: str,
        node_uuid: str,
        schema: dict | None = None,
    ) -> AstrBotNodeConfig:
        cache_key = (node_name, chain_id, node_uuid)
        cached = cls._cache.get(cache_key)
        if cached is None:
            cached = cls(
                node_name=node_name,
                chain_id=chain_id,
                node_uuid=node_uuid,
                schema=schema,
            )
            cls._cache[cache_key] = cached
            return cached

        if schema is not None:
            if not cached.config_path:
                cached = cls(
                    node_name=node_name,
                    chain_id=chain_id,
                    node_uuid=node_uuid,
                    schema=schema,
                )
                cls._cache[cache_key] = cached
                return cached
            cached._update_schema(schema)
        return cached

    def _update_schema(self, schema: dict) -> None:
        if self.schema == schema:
            return
        object.__setattr__(self, "schema", schema)
        refer_conf = self._config_schema_to_default_config(schema)
        object.__setattr__(self, "default_config", refer_conf)
        conf = dict(self)
        has_new = self.check_config_integrity(refer_conf, conf)
        self.clear()
        self.update(conf)
        if has_new:
            self.save_config()
