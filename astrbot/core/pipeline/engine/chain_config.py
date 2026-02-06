from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import JSON, Field, SQLModel

from astrbot.core.db.po import TimestampMixin
from astrbot.core.star.modality import Modality


class ChainConfigModel(TimestampMixin, SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    chain_id: str = Field(
        max_length=36,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    match_rule: dict | None = Field(default=None, sa_type=JSON)
    sort_order: int = Field(default=0)
    enabled: bool = Field(default=True)

    nodes: list[dict | str] | None = Field(default=None, sa_type=JSON)

    llm_enabled: bool = Field(default=True)

    plugin_filter: dict | None = Field(default=None, sa_type=JSON)

    config_id: str | None = Field(default=None, max_length=36)


@dataclass
class PluginFilterConfig:
    mode: str = "blacklist"
    plugins: list[str] = field(default_factory=list)


_NODE_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "astrbot.chain.node")


@dataclass
class ChainNodeConfig:
    name: str
    uuid: str


def _stable_node_uuid(chain_id: str, name: str, occurrence: int) -> str:
    seed = f"{chain_id}:{name}:{occurrence}"
    return str(uuid.uuid5(_NODE_UUID_NAMESPACE, seed))


def normalize_chain_nodes(
    raw_nodes: list[Any] | None, chain_id: str
) -> list[ChainNodeConfig]:
    if not raw_nodes:
        return []

    normalized: list[ChainNodeConfig] = []
    seen_uuids: set[str] = set()
    name_occurrence: dict[str, int] = {}

    for entry in raw_nodes:
        name: str | None = None
        node_uuid: str | None = None

        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("node_name") or entry.get("node")
            node_uuid = entry.get("uuid") or entry.get("id")
        elif isinstance(entry, str):
            name = entry

        if not name:
            continue

        occurrence = name_occurrence.get(name, 0) + 1
        name_occurrence[name] = occurrence

        if node_uuid is not None:
            node_uuid = str(node_uuid).strip()
            if not node_uuid or node_uuid in seen_uuids:
                node_uuid = None

        if not node_uuid:
            node_uuid = _stable_node_uuid(chain_id, name, occurrence)
            if node_uuid in seen_uuids:
                node_uuid = str(uuid.uuid4())

        seen_uuids.add(node_uuid)
        normalized.append(ChainNodeConfig(name=name, uuid=node_uuid))

    return normalized


def serialize_chain_nodes(nodes: list[ChainNodeConfig]) -> list[dict]:
    return [{"name": node.name, "uuid": node.uuid} for node in nodes]


def clone_chain_nodes(nodes: list[ChainNodeConfig]) -> list[ChainNodeConfig]:
    return [ChainNodeConfig(name=node.name, uuid=node.uuid) for node in nodes]


@dataclass
class ChainConfig:
    chain_id: str
    match_rule: dict | None = None
    sort_order: int = 0
    enabled: bool = True
    nodes: list[ChainNodeConfig] = field(default_factory=list)
    llm_enabled: bool = True
    plugin_filter: PluginFilterConfig | None = None
    config_id: str | None = None

    def matches(
        self,
        umo: str,
        modality: set[Modality] | None = None,
        message_text: str = "",
    ) -> bool:
        if not self.enabled:
            return False

        from astrbot.core.pipeline.engine.rule_matcher import rule_matcher

        return rule_matcher.matches(self.match_rule, umo, modality, message_text)

    @staticmethod
    def from_model(model: ChainConfigModel) -> ChainConfig:
        if model.nodes is None:
            nodes = clone_chain_nodes(DEFAULT_CHAIN_CONFIG.nodes)
        else:
            nodes = normalize_chain_nodes(model.nodes, model.chain_id)

        plugin_filter = None
        if model.plugin_filter:
            mode = model.plugin_filter.get("mode", "blacklist")
            plugins = model.plugin_filter.get("plugins", []) or []
            plugin_filter = PluginFilterConfig(mode=mode, plugins=list(plugins))

        return ChainConfig(
            chain_id=model.chain_id,
            match_rule=model.match_rule,
            sort_order=model.sort_order,
            enabled=model.enabled,
            nodes=nodes,
            llm_enabled=model.llm_enabled,
            plugin_filter=plugin_filter,
            config_id=model.config_id,
        )


_DEFAULT_NODES = normalize_chain_nodes(["agent"], "default")

DEFAULT_CHAIN_CONFIG = ChainConfig(
    chain_id="default",
    match_rule=None,  # None = match all
    sort_order=-1,  # Always last
    nodes=_DEFAULT_NODES,
    config_id="default",
)
