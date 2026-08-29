from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, select

from astrbot.core.db.po import Preference
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


class PreferenceStoreMixin(DatabaseStoreMixin):
    async def insert_preference_or_update(
        self,
        scope: str,
        scope_id: str,
        key: str,
        value: dict,
    ) -> Preference:
        """Insert a new preference record or update if it exists."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                query = select(Preference).where(
                    Preference.scope == scope,
                    Preference.scope_id == scope_id,
                    Preference.key == key,
                )
                result = await session.execute(query)
                existing_preference = result.scalar_one_or_none()
                if existing_preference:
                    existing_preference.value = value
                    return existing_preference
                new_preference = Preference(
                    scope=scope,
                    scope_id=scope_id,
                    key=key,
                    value=value,
                )
                session.add(new_preference)
                return new_preference

    async def get_preference(
        self,
        scope: str,
        scope_id: str,
        key: str,
    ) -> Preference | None:
        """Get a preference by key."""
        async with store_session(self) as session:
            session: AsyncSession
            query = select(Preference).where(
                Preference.scope == scope,
                Preference.scope_id == scope_id,
                Preference.key == key,
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_preferences(
        self,
        scope: str | None = None,
        scope_id: str | None = None,
        key: str | None = None,
    ) -> list[Preference]:
        """Get preferences, optionally filtered by scope, scope ID, or key."""
        async with store_session(self) as session:
            session: AsyncSession
            query = select(Preference)
            if scope is not None:
                query = query.where(Preference.scope == scope)
            if scope_id is not None:
                query = query.where(Preference.scope_id == scope_id)
            if key is not None:
                query = query.where(Preference.key == key)
            result = await session.execute(query)
            return list(result.scalars().all())

    async def remove_preference(self, scope: str, scope_id: str, key: str) -> None:
        """Remove a preference by scope ID and key."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Preference).where(
                        col(Preference.scope) == scope,
                        col(Preference.scope_id) == scope_id,
                        col(Preference.key) == key,
                    ),
                )
            await session.commit()

    async def clear_preferences(self, scope: str, scope_id: str) -> None:
        """Clear all preferences for a specific scope ID."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(Preference).where(
                        col(Preference.scope) == scope,
                        col(Preference.scope_id) == scope_id,
                    ),
                )
            await session.commit()
