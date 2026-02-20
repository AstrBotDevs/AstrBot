from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from astrbot.core import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.pipeline.engine.chain_config import (
    DEFAULT_CHAIN_CONFIG,
    ChainConfig,
    ChainConfigModel,
)
from astrbot.core.star.modality import Modality


class ChainRouter:
    def __init__(self) -> None:
        self._configs: list[ChainConfig] = []
        self._configs_map: dict[str, ChainConfig] = {}

    async def load_configs(self, db_helper: BaseDatabase) -> None:
        db_chains = await self._load_chain_configs_from_db(db_helper)
        default_chain = None
        normal_chains: list[ChainConfig] = []
        for chain in db_chains:
            if chain.chain_id == "default":
                default_chain = chain
            else:
                normal_chains.append(chain)
        normal_chains.sort(key=lambda c: c.sort_order, reverse=True)
        self._configs = normal_chains + [default_chain or DEFAULT_CHAIN_CONFIG]
        self._configs_map = {config.chain_id: config for config in self._configs}
        logger.info(f"Loaded {len(self._configs)} chain configs")

    def route(
        self, umo: str, modality: set[Modality] | None = None, message_text: str = ""
    ) -> ChainConfig | None:
        for config in self._configs:
            if config.matches(umo, modality, message_text):
                logger.debug(f"Routed {umo} to chain: {config.chain_id}")
                return config
        return None

    def get_by_chain_id(self, chain_id: str) -> ChainConfig | None:
        return self._configs_map.get(chain_id)

    async def reload(self, db_helper: BaseDatabase) -> None:
        await self.load_configs(db_helper)

    @staticmethod
    async def _load_chain_configs_from_db(db_helper: BaseDatabase) -> list[ChainConfig]:
        async with db_helper.get_db() as session:
            session: AsyncSession
            result = await session.execute(select(ChainConfigModel))
            records = result.scalars().all()

        return [ChainConfig.from_model(record) for record in records]
