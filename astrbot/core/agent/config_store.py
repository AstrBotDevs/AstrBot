"""Database persistence for reusable agent configurations, separate from agent history."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlmodel import col, select

from astrbot.core.agent.config import StoredAgentConfig
from astrbot.core.db.po import AgentConfigRecord

if TYPE_CHECKING:
    from astrbot.core.db import BaseDatabase


class AgentConfigStore:
    """Read and persist configurations without interpreting runtime-owned options."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self.lock = asyncio.Lock()

    async def list(self) -> list[StoredAgentConfig]:
        """Return reusable configurations in creation order.

        Returns:
            Detached portable records.
        """
        async with self.db.get_db() as session:
            rows = (
                await session.execute(
                    select(AgentConfigRecord).order_by(
                        col(AgentConfigRecord.created_at),
                        col(AgentConfigRecord.config_id),
                    )
                )
            ).scalars()
            return [
                StoredAgentConfig.model_validate(
                    row.model_dump(include=set(StoredAgentConfig.model_fields))
                )
                for row in rows
            ]

    async def get(self, config_id: str) -> StoredAgentConfig:
        """Find a configuration by stable identity.

        Args:
            config_id: Persistent agent_config identity.

        Returns:
            The detached configuration.

        Raises:
            ValueError: If the agent_config is missing.
        """
        async with self.db.get_db() as session:
            row = await session.get(AgentConfigRecord, config_id)
            if row is None:
                raise ValueError(f"Agent configuration not found: {config_id}")
            return StoredAgentConfig.model_validate(
                row.model_dump(include=set(StoredAgentConfig.model_fields))
            )

    async def save(self, agent_config: StoredAgentConfig) -> StoredAgentConfig:
        """Atomically create or replace a configuration.

        Args:
            agent_config: Validated metadata and runtime configuration.

        Returns:
            The persisted record.
        """
        async with self.db.get_db() as session, session.begin():
            row = await session.get(AgentConfigRecord, agent_config.config_id)
            if row is None:
                session.add(AgentConfigRecord(**agent_config.model_dump()))
            else:
                for key, value in agent_config.model_dump().items():
                    setattr(row, key, value)
        return agent_config

    async def delete(self, config_id: str) -> None:
        """Delete a record after the caller has checked references.

        Args:
            config_id: Persistent agent_config identity.

        Raises:
            ValueError: If the record does not exist.
        """
        async with self.db.get_db() as session, session.begin():
            row = await session.get(AgentConfigRecord, config_id)
            if row is None:
                raise ValueError(f"Agent configuration not found: {config_id}")
            await session.delete(row)
