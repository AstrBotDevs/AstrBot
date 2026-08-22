from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot.core.db.po import UmoAlias


class UmoAliasStoreMixin:
    async def upsert_umo_alias(
        self,
        umo: str,
        creator_sender_id: str,
        auto_name: str | None,
        user_alias: str | None,
    ) -> UmoAlias:
        """Create or update alias metadata for a UMO."""
        async with self.get_db() as session:
            session: AsyncSession
            async with session.begin():
                result = await session.execute(
                    select(UmoAlias).where(col(UmoAlias.umo) == umo)
                )
                alias = result.scalar_one_or_none()
                if alias:
                    alias.creator_sender_id = creator_sender_id
                    alias.auto_name = auto_name
                    alias.user_alias = user_alias
                    alias.updated_at = datetime.now(UTC)
                else:
                    alias = UmoAlias(
                        umo=umo,
                        creator_sender_id=creator_sender_id,
                        auto_name=auto_name,
                        user_alias=user_alias,
                    )
                    session.add(alias)
                await session.flush()
                await session.refresh(alias)
                return alias

    async def get_umo_alias(self, umo: str) -> UmoAlias | None:
        """Get alias metadata for one UMO."""
        async with self.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(UmoAlias).where(col(UmoAlias.umo) == umo)
            )
            return result.scalar_one_or_none()

    async def get_umo_aliases(self, umos: list[str] | None = None) -> list[UmoAlias]:
        """Get alias metadata, optionally restricted to a UMO list."""
        if umos is not None and not umos:
            return []

        async with self.get_db() as session:
            session: AsyncSession
            query = select(UmoAlias)
            if umos is not None:
                query = query.where(col(UmoAlias.umo).in_(umos))
            result = await session.execute(query)
            return list(result.scalars().all())
