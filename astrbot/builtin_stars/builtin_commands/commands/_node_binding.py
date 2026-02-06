from __future__ import annotations

from dataclasses import dataclass

from astrbot.api.event import AstrMessageEvent
from astrbot.core.config.node_config import AstrBotNodeConfig
from astrbot.core.pipeline.engine.chain_config import ChainNodeConfig
from astrbot.core.star.context import Context


@dataclass
class NodeTarget:
    node: ChainNodeConfig
    config: AstrBotNodeConfig


def _get_node_schema(context: Context, node_name: str) -> dict | None:
    meta = context.get_registered_star(node_name)
    if meta:
        return meta.node_schema
    return None


def get_chain_nodes(event: AstrMessageEvent, node_name: str) -> list[ChainNodeConfig]:
    chain_config = event.chain_config
    if not chain_config:
        return []
    return [node for node in chain_config.nodes if node.name == node_name]


def resolve_node_selector(
    nodes: list[ChainNodeConfig], selector: str
) -> ChainNodeConfig | None:
    selector = (selector or "").strip()
    if not selector:
        return None
    if selector.isdigit():
        idx = int(selector)
        if idx < 1 or idx > len(nodes):
            return None
        return nodes[idx - 1]
    for node in nodes:
        if node.uuid == selector:
            return node
    return None


def get_node_target(
    context: Context,
    event: AstrMessageEvent,
    node_name: str,
    selector: str | None = None,
) -> NodeTarget | None:
    chain_config = event.chain_config
    if not chain_config:
        return None

    nodes = get_chain_nodes(event, node_name)
    if not nodes:
        return None

    target: ChainNodeConfig | None = None
    if selector:
        target = resolve_node_selector(nodes, selector)
    elif len(nodes) == 1:
        target = nodes[0]

    if target is None:
        return None

    schema = _get_node_schema(context, node_name)
    cfg = AstrBotNodeConfig.get_cached(
        node_name=node_name,
        chain_id=chain_config.chain_id,
        node_uuid=target.uuid,
        schema=schema,
    )
    return NodeTarget(node=target, config=cfg)


def list_nodes_with_config(
    context: Context,
    event: AstrMessageEvent,
    node_name: str,
) -> list[NodeTarget]:
    chain_config = event.chain_config
    if not chain_config:
        return []

    schema = _get_node_schema(context, node_name)
    ret: list[NodeTarget] = []
    for node in get_chain_nodes(event, node_name):
        cfg = AstrBotNodeConfig.get_cached(
            node_name=node_name,
            chain_id=chain_config.chain_id,
            node_uuid=node.uuid,
            schema=schema,
        )
        ret.append(NodeTarget(node=node, config=cfg))
    return ret
