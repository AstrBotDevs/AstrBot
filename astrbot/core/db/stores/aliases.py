from datetime import UTC, datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot.core.db.po import UmoAlias
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


class UmoAliasStoreMixin(DatabaseStoreMixin):
    async def upsert_umo_alias(
        self,
        umo: str,
        creator_sender_id: str,
        auto_name: str | None,
        user_alias: str | None,
    ) -> UmoAlias:
        """Create or update alias metadata for a UMO."""
        now = datetime.now(UTC)
        statement = sqlite_insert(UmoAlias).values(
            umo=umo,
            creator_sender_id=creator_sender_id,
            auto_name=auto_name,
            user_alias=user_alias,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UmoAlias.umo],
            set_={
                "creator_sender_id": statement.excluded.creator_sender_id,
                "auto_name": statement.excluded.auto_name,
                "user_alias": statement.excluded.user_alias,
                "updated_at": now,
            },
        )
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(statement)
                result = await session.execute(
                    select(UmoAlias).where(col(UmoAlias.umo) == umo)
                )
                return result.scalar_one()

    async def upsert_umo_auto_name(
        self,
        umo: str,
        creator_sender_id: str,
        auto_name: str,
    ) -> None:
        """Persist an automatic UMO name without changing its manual alias."""
        now = datetime.now(UTC)
        statement = sqlite_insert(UmoAlias).values(
            umo=umo,
            creator_sender_id=creator_sender_id,
            auto_name=auto_name,
            user_alias=None,
            created_at=now,
            updated_at=now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[UmoAlias.umo],
            set_={
                "auto_name": statement.excluded.auto_name,
                "updated_at": now,
            },
            where=col(UmoAlias.auto_name).is_distinct_from(
                statement.excluded.auto_name
            ),
        )
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(statement)

    async def get_umo_alias(self, umo: str) -> UmoAlias | None:
        """Get alias metadata for one UMO."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(UmoAlias).where(col(UmoAlias.umo) == umo)
            )
            return result.scalar_one_or_none()

    async def get_umo_aliases(self, umos: list[str] | None = None) -> list[UmoAlias]:
        """Get alias metadata, optionally restricted to a UMO list."""
        if umos is not None and not umos:
            return []

        async with store_session(self) as session:
            session: AsyncSession
            query = select(UmoAlias)
            if umos is not None:
                query = query.where(col(UmoAlias.umo).in_(umos))
            result = await session.execute(query)
            return list(result.scalars().all())
