import traceback
import uuid

from quart import request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from astrbot.core import logger
from astrbot.core.config.node_config import AstrBotNodeConfig
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.pipeline.engine.chain_config import (
    DEFAULT_CHAIN_CONFIG,
    ChainConfigModel,
    normalize_chain_nodes,
    serialize_chain_nodes,
)
from astrbot.core.star.modality import Modality
from astrbot.core.star.node_star import NodeStar
from astrbot.core.star.star import StarMetadata

from .config import validate_config
from .route import Response, Route, RouteContext


class ChainManagementRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.db_helper = db_helper
        self.core_lifecycle = core_lifecycle
        self.routes = {
            "/chain/list": ("GET", self.list_chains),
            "/chain/get": ("GET", self.get_chain),
            "/chain/create": ("POST", self.create_chain),
            "/chain/update": ("POST", self.update_chain),
            "/chain/delete": ("POST", self.delete_chain),
            "/chain/reorder": ("POST", self.reorder_chains),
            "/chain/available-options": ("GET", self.get_available_options),
            "/chain/node-config": ("GET", self.get_node_config),
            "/chain/node-config/update": ("POST", self.update_node_config),
        }
        self.register_routes()

    def _default_nodes(self) -> list[dict]:
        return serialize_chain_nodes(DEFAULT_CHAIN_CONFIG.nodes)

    async def _reload_chain_configs(self) -> None:
        await self.core_lifecycle.chain_config_router.reload(
            self.db_helper,
        )

    def _serialize_chain(self, chain: ChainConfigModel) -> dict:
        is_default = chain.chain_id == "default"
        nodes_payload = None
        if chain.nodes is not None:
            normalized = normalize_chain_nodes(chain.nodes, chain.chain_id)
            nodes_payload = serialize_chain_nodes(normalized)
        return {
            "chain_id": chain.chain_id,
            "match_rule": chain.match_rule,
            "sort_order": chain.sort_order,
            "enabled": chain.enabled,
            "nodes": nodes_payload,
            "llm_enabled": chain.llm_enabled,
            "plugin_filter": chain.plugin_filter,
            "config_id": chain.config_id,
            "created_at": chain.created_at.isoformat() if chain.created_at else None,
            "updated_at": chain.updated_at.isoformat() if chain.updated_at else None,
            "is_default": is_default,
        }

    def _serialize_default_chain_virtual(self) -> dict:
        return {
            "chain_id": "default",
            "match_rule": None,
            "sort_order": -1,
            "enabled": True,
            "nodes": None,
            "llm_enabled": DEFAULT_CHAIN_CONFIG.llm_enabled,
            "plugin_filter": None,
            "config_id": "default",
            "created_at": None,
            "updated_at": None,
            "is_default": True,
        }

    @staticmethod
    def _is_node_plugin(plugin: StarMetadata) -> bool:
        if plugin.star_cls_type:
            try:
                return issubclass(plugin.star_cls_type, NodeStar)
            except TypeError:
                return False
        return isinstance(plugin.star_cls, NodeStar)

    def _get_node_plugin_map(self) -> dict[str, StarMetadata]:
        return {
            p.name: p
            for p in self.core_lifecycle.plugin_manager.context.get_all_stars()
            if p.name and self._is_node_plugin(p)
        }

    def _get_node_schema(self, node_name: str) -> dict | None:
        node = self._get_node_plugin_map().get(node_name)
        return node.node_schema if node else None

    async def list_chains(self):
        try:
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 10, type=int)
            search = request.args.get("search", "", type=str).strip()

            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 10
            if page_size > 100:
                page_size = 100

            async with self.db_helper.get_db() as session:
                session: AsyncSession
                result = await session.execute(select(ChainConfigModel))
                chains = list(result.scalars().all())

            default_chain = None
            normal_chains: list[ChainConfigModel] = []
            for chain in chains:
                if chain.chain_id == "default":
                    default_chain = chain
                else:
                    normal_chains.append(chain)

            if search:
                search_lower = search.lower()
                normal_chains = [
                    chain
                    for chain in normal_chains
                    if chain.match_rule
                    and search_lower in str(chain.match_rule).lower()
                ]

            chains = sorted(normal_chains, key=lambda c: c.sort_order, reverse=True)

            if default_chain:
                include_default = True
                if search:
                    search_lower = search.lower()
                    include_default = search_lower in "default" or (
                        default_chain.match_rule
                        and search_lower in str(default_chain.match_rule).lower()
                    )
                if include_default:
                    chains.append(default_chain)
            elif not search or "default" in search.lower():
                chains.append(self._serialize_default_chain_virtual())

            total = len(chains)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated = chains[start_idx:end_idx]

            return (
                Response()
                .ok(
                    {
                        "chains": [
                            self._serialize_chain(chain)
                            if isinstance(chain, ChainConfigModel)
                            else chain
                            for chain in paginated
                        ],
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取 Chain 列表失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取 Chain 列表失败: {e!s}").__dict__

    async def get_chain(self):
        try:
            chain_id = request.args.get("chain_id", "")
            if not chain_id:
                return Response().error("缺少必要参数: chain_id").__dict__

            async with self.db_helper.get_db() as session:
                session: AsyncSession
                result = await session.execute(
                    select(ChainConfigModel).where(
                        ChainConfigModel.chain_id == chain_id
                    )
                )
                chain = result.scalar_one_or_none()

            if not chain:
                if chain_id == "default":
                    return (
                        Response().ok(self._serialize_default_chain_virtual()).__dict__
                    )
                return Response().error("Chain 不存在").__dict__

            return Response().ok(self._serialize_chain(chain)).__dict__
        except Exception as e:
            logger.error(f"获取 Chain 失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取 Chain 失败: {e!s}").__dict__

    async def create_chain(self):
        try:
            data = await request.get_json()

            chain_id = data.get("chain_id") or str(uuid.uuid4())
            if chain_id == "default":
                return (
                    Response().error("默认 Chain 不允许创建，请使用编辑功能。").__dict__
                )
            nodes = data.get("nodes")
            nodes_payload = (
                serialize_chain_nodes(normalize_chain_nodes(nodes, chain_id))
                if nodes is not None
                else None
            )

            # 获取当前最大 sort_order，新建的放到最后
            async with self.db_helper.get_db() as session:
                session: AsyncSession
                result = await session.execute(select(ChainConfigModel))
                existing_chains = list(result.scalars().all())
                max_sort_order = max(
                    (c.sort_order for c in existing_chains), default=-1
                )

            chain = ChainConfigModel(
                chain_id=chain_id,
                match_rule=data.get("match_rule"),
                sort_order=max_sort_order + 1,
                enabled=data.get("enabled", True),
                nodes=nodes_payload,
                llm_enabled=data.get("llm_enabled", True),
                plugin_filter=data.get("plugin_filter"),
                config_id=data.get("config_id"),
            )

            async with self.db_helper.get_db() as session:
                session: AsyncSession
                session.add(chain)
                await session.commit()
                await session.refresh(chain)

            await self._reload_chain_configs()

            return Response().ok(self._serialize_chain(chain)).__dict__
        except Exception as e:
            logger.error(f"创建 Chain 失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"创建 Chain 失败: {e!s}").__dict__

    async def update_chain(self):
        try:
            data = await request.get_json()
            chain_id = data.get("chain_id", "")
            if not chain_id:
                return Response().error("缺少必要参数: chain_id").__dict__

            async with self.db_helper.get_db() as session:
                session: AsyncSession
                result = await session.execute(
                    select(ChainConfigModel).where(
                        ChainConfigModel.chain_id == chain_id
                    )
                )
                chain = result.scalar_one_or_none()
                if not chain and chain_id != "default":
                    return Response().error("Chain 不存在").__dict__

                if chain_id == "default" and not chain:
                    nodes = data.get("nodes")
                    nodes_payload = (
                        serialize_chain_nodes(normalize_chain_nodes(nodes, chain_id))
                        if nodes is not None
                        else None
                    )
                    chain = ChainConfigModel(
                        chain_id="default",
                        match_rule=None,
                        sort_order=-1,
                        enabled=data.get("enabled", True),
                        nodes=nodes_payload,
                        llm_enabled=data.get("llm_enabled", True),
                        plugin_filter=data.get("plugin_filter"),
                        config_id="default",
                    )
                    session.add(chain)
                    await session.commit()
                    await session.refresh(chain)
                    await self._reload_chain_configs()
                    return Response().ok(self._serialize_chain(chain)).__dict__

                for field in [
                    "match_rule",
                    "enabled",
                    "nodes",
                    "llm_enabled",
                    "plugin_filter",
                    "config_id",
                ]:
                    if field in data:
                        value = data.get(field)
                        if field == "nodes":
                            value = (
                                serialize_chain_nodes(
                                    normalize_chain_nodes(value, chain_id)
                                )
                                if value is not None
                                else None
                            )
                        setattr(chain, field, value)

                if chain.chain_id == "default":
                    chain.match_rule = None
                    chain.sort_order = -1
                    chain.config_id = "default"

                session.add(chain)
                await session.commit()
                await session.refresh(chain)

            await self._reload_chain_configs()

            return Response().ok(self._serialize_chain(chain)).__dict__
        except Exception as e:
            logger.error(f"更新 Chain 失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"更新 Chain 失败: {e!s}").__dict__

    async def delete_chain(self):
        try:
            data = await request.get_json()
            chain_id = data.get("chain_id", "")
            if not chain_id:
                return Response().error("缺少必要参数: chain_id").__dict__
            if chain_id == "default":
                return Response().error("默认 Chain 不允许删除。").__dict__

            async with self.db_helper.get_db() as session:
                session: AsyncSession
                result = await session.execute(
                    select(ChainConfigModel).where(
                        ChainConfigModel.chain_id == chain_id
                    )
                )
                chain = result.scalar_one_or_none()
                if not chain:
                    return Response().error("Chain 不存在").__dict__

                await session.delete(chain)
                await session.commit()

            await self._reload_chain_configs()

            return Response().ok({"message": "Chain 已删除"}).__dict__
        except Exception as e:
            logger.error(f"删除 Chain 失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"删除 Chain 失败: {e!s}").__dict__

    async def reorder_chains(self):
        """接收有序的 chain_id 列表，按顺序分配 sort_order（列表顺序即匹配顺序）"""
        try:
            data = await request.get_json()
            chain_ids = data.get("chain_ids", [])
            if not chain_ids:
                return Response().error("chain_ids 不能为空").__dict__
            chain_ids = [cid for cid in chain_ids if cid != "default"]

            async with self.db_helper.get_db() as session:
                session: AsyncSession
                total = len(chain_ids)
                for index, chain_id in enumerate(chain_ids):
                    result = await session.execute(
                        select(ChainConfigModel).where(
                            ChainConfigModel.chain_id == chain_id
                        )
                    )
                    chain = result.scalar_one_or_none()
                    if chain:
                        # 列表第一个元素 sort_order 最大，最先匹配
                        chain.sort_order = total - 1 - index
                        session.add(chain)
                await session.commit()

            await self._reload_chain_configs()

            return Response().ok({"message": "排序已更新"}).__dict__
        except Exception as e:
            logger.error(f"更新排序失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"更新排序失败: {e!s}").__dict__

    async def get_available_options(self):
        try:
            provider_manager = self.core_lifecycle.provider_manager
            plugin_manager = self.core_lifecycle.plugin_manager

            available_stt_providers = [
                {
                    "id": p.meta().id,
                    "name": p.meta().id,
                    "model": p.meta().model,
                }
                for p in provider_manager.stt_provider_insts
            ]

            available_tts_providers = [
                {
                    "id": p.meta().id,
                    "name": p.meta().id,
                    "model": p.meta().model,
                }
                for p in provider_manager.tts_provider_insts
            ]

            available_plugins = [
                {
                    "name": p.name,
                    "display_name": p.display_name or p.name,
                    "desc": p.desc,
                }
                for p in plugin_manager.context.get_all_stars()
                if not p.reserved and p.name and not self._is_node_plugin(p)
            ]

            node_plugins = [
                p
                for p in plugin_manager.context.get_all_stars()
                if p.name and self._is_node_plugin(p)
            ]
            available_nodes = [
                {
                    "name": p.name,
                    "display_name": p.display_name or p.name,
                    "schema": p.node_schema or {},
                }
                for p in node_plugins
            ]
            default_nodes = self._default_nodes()
            available_nodes = {node["name"]: node for node in available_nodes}
            available_nodes = list(available_nodes.values())

            available_configs = self.core_lifecycle.astrbot_config_mgr.get_conf_list()

            available_modalities = [
                {"label": m.value, "value": m.value} for m in Modality
            ]

            return (
                Response()
                .ok(
                    {
                        "available_stt_providers": available_stt_providers,
                        "available_tts_providers": available_tts_providers,
                        "available_plugins": available_plugins,
                        "available_nodes": available_nodes,
                        "default_nodes": default_nodes,
                        "available_configs": available_configs,
                        "available_modalities": available_modalities,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取可用选项失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取可用选项失败: {e!s}").__dict__

    async def get_node_config(self):
        try:
            chain_id = request.args.get("chain_id", "").strip()
            node_name = request.args.get("node_name", "").strip()
            node_uuid = request.args.get("node_uuid", "").strip() or None

            if not chain_id or not node_name:
                return Response().error("缺少必要参数: chain_id 或 node_name").__dict__

            schema = self._get_node_schema(node_name) or {}
            node_config = AstrBotNodeConfig.get_cached(
                node_name=node_name,
                chain_id=chain_id,
                node_uuid=node_uuid,
                schema=schema or None,
            )

            return (
                Response()
                .ok(
                    {
                        "config": dict(node_config),
                        "schema": schema,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取节点配置失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"获取节点配置失败: {e!s}").__dict__

    async def update_node_config(self):
        try:
            data = await request.get_json()
            chain_id = (data.get("chain_id") or "").strip()
            node_name = (data.get("node_name") or "").strip()
            node_uuid = (data.get("node_uuid") or "").strip() or None
            config = data.get("config")

            if not chain_id or not node_name:
                return Response().error("缺少必要参数: chain_id 或 node_name").__dict__
            if not isinstance(config, dict):
                return Response().error("配置内容必须是对象").__dict__

            schema = self._get_node_schema(node_name) or {}
            if schema:
                errors, config = validate_config(config, schema, is_core=False)
                if errors:
                    return Response().error(f"配置校验失败: {errors}").__dict__

            node_config = AstrBotNodeConfig.get_cached(
                node_name=node_name,
                chain_id=chain_id,
                node_uuid=node_uuid,
                schema=schema or None,
            )
            node_config.save_config(config)

            return Response().ok({"message": "节点配置已保存"}).__dict__
        except Exception as e:
            logger.error(f"保存节点配置失败: {e!s}\n{traceback.format_exc()}")
            return Response().error(f"保存节点配置失败: {e!s}").__dict__
