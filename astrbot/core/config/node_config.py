from __future__ import annotations

import json
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
    node_name: str, chain_id: str, node_uuid: str | None = None
) -> str:
    plugin_key = _sanitize_name(node_name or "unknown")
    chain_key = _sanitize_name(chain_id or "default")
    if node_uuid:
        uuid_key = _sanitize_name(node_uuid)
        filename = f"node_{plugin_key}_{chain_key}_{uuid_key}.json"
    else:
        filename = f"node_{plugin_key}_{chain_key}.json"
    os.makedirs(get_astrbot_config_path(), exist_ok=True)
    return os.path.join(get_astrbot_config_path(), filename)


class AstrBotNodeConfig(AstrBotConfig):
    """Node config - extends AstrBotConfig with chain-specific path.

    Node config is chain-scoped and shared across config_id.
    This class reuses AstrBotConfig's schema parsing, integrity checking,
    and persistence logic, only overriding the config path.
    """

    node_name: str | None
    chain_id: str | None
    node_uuid: str | None

    _cache: dict[tuple[str, str, str], AstrBotNodeConfig] = {}

    def __init__(
        self,
        node_name: str | None = None,
        chain_id: str | None = None,
        node_uuid: str | None = None,
        schema: dict | None = None,
    ):
        # Store node identifiers before parent init
        object.__setattr__(self, "node_name", node_name)
        object.__setattr__(self, "chain_id", chain_id)
        object.__setattr__(self, "node_uuid", node_uuid)

        # Build config path based on node_name and chain_id
        if node_name and chain_id:
            legacy_path = _build_node_config_path(node_name, chain_id)
            config_path = _build_node_config_path(node_name, chain_id, node_uuid)
            if (
                node_uuid
                and not os.path.exists(config_path)
                and os.path.exists(legacy_path)
            ):
                with open(legacy_path, encoding="utf-8-sig") as f:
                    legacy_conf = json.loads(f.read())
                with open(config_path, "w", encoding="utf-8-sig") as f:
                    json.dump(legacy_conf, f, indent=2, ensure_ascii=False)
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
        node_name: str | None,
        chain_id: str | None,
        node_uuid: str | None = None,
        schema: dict | None = None,
    ) -> AstrBotNodeConfig:
        cache_key = (node_name or "", chain_id or "", node_uuid or "")
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
