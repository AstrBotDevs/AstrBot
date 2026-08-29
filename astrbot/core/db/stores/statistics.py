from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select, text

from astrbot.core.db.po import PlatformStat, ProviderStat
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


class StatisticsStoreMixin(DatabaseStoreMixin):
    async def insert_platform_stats(
        self,
        platform_id,
        platform_type,
        count=1,
        timestamp=None,
    ) -> None:
        """Insert a new platform statistic record."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                if timestamp is None:
                    timestamp = datetime.now().replace(
                        minute=0,
                        second=0,
                        microsecond=0,
                    )
                current_hour = timestamp
                await session.execute(
                    text("""
                    INSERT INTO platform_stats (timestamp, platform_id, platform_type, count)
                    VALUES (:timestamp, :platform_id, :platform_type, :count)
                    ON CONFLICT(timestamp, platform_id, platform_type) DO UPDATE SET
                        count = platform_stats.count + EXCLUDED.count
                    """),
                    {
                        "timestamp": current_hour,
                        "platform_id": platform_id,
                        "platform_type": platform_type,
                        "count": count,
                    },
                )

    async def count_platform_stats(self) -> int:
        """Count the number of platform statistics records."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(func.count(col(PlatformStat.platform_id))).select_from(
                    PlatformStat,
                ),
            )
            count = result.scalar_one_or_none()
            return count if count is not None else 0

    async def get_platform_stats(self, offset_sec: int = 86400) -> list[PlatformStat]:
        """Get platform statistic rows within the specified offset in seconds."""
        async with store_session(self) as session:
            session: AsyncSession
            now = datetime.now()
            start_time = now - timedelta(seconds=offset_sec)
            result = await session.execute(
                select(PlatformStat)
                .where(col(PlatformStat.timestamp) >= start_time)
                .order_by(col(PlatformStat.timestamp).asc()),
            )
            return list(result.scalars().all())

    async def insert_provider_stat(
        self,
        *,
        umo: str,
        provider_id: str,
        provider_model: str | None = None,
        conversation_id: str | None = None,
        status: str = "completed",
        stats: dict | None = None,
        agent_type: str = "internal",
    ) -> ProviderStat:
        """Insert a provider stat record for a single agent response."""
        stats = stats or {}
        token_usage = stats.get("token_usage", {})

        token_input_other = int(token_usage.get("input_other", 0) or 0)
        token_input_cached = int(token_usage.get("input_cached", 0) or 0)
        token_output = int(token_usage.get("output", 0) or 0)

        start_time = float(stats.get("start_time", 0.0) or 0.0)
        end_time = float(stats.get("end_time", 0.0) or 0.0)
        time_to_first_token = float(stats.get("time_to_first_token", 0.0) or 0.0)

        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                record = ProviderStat(
                    agent_type=agent_type,
                    status=status,
                    umo=umo,
                    conversation_id=conversation_id,
                    provider_id=provider_id,
                    provider_model=provider_model,
                    token_input_other=token_input_other,
                    token_input_cached=token_input_cached,
                    token_output=token_output,
                    start_time=start_time,
                    end_time=end_time,
                    time_to_first_token=time_to_first_token,
                )
                session.add(record)
                await session.flush()
                await session.refresh(record)
                return record
