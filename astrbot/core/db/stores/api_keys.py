import typing as T
from datetime import UTC, datetime

from sqlalchemy import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, delete, desc, or_, select, update

from astrbot.core.auth.models import persist_capability_config_id
from astrbot.core.auth.registry import dashboard_api_capability_specs
from astrbot.core.db.po import ApiKey, AuthCapability
from astrbot.core.db.stores.mixin import DatabaseStoreMixin, store_session


async def _upsert_capability_in_session(
    session: AsyncSession,
    *,
    subject_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    config_id: str | None,
    created_by: str | None,
    expires_at: datetime | None,
) -> AuthCapability:
    persisted_config_id = persist_capability_config_id(config_id)
    existing = (
        await session.execute(
            select(AuthCapability).where(
                col(AuthCapability.subject_id) == subject_id,
                col(AuthCapability.action) == action,
                col(AuthCapability.resource_type) == resource_type,
                col(AuthCapability.resource_id) == resource_id,
                col(AuthCapability.config_id) == persisted_config_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = AuthCapability(
            subject_id=subject_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            config_id=persisted_config_id,
            created_by=created_by,
            expires_at=expires_at,
        )
        session.add(existing)
    else:
        existing.created_by = created_by
        existing.expires_at = expires_at
        existing.revoked_at = None
    await session.flush()
    await session.refresh(existing)
    return existing


class ApiKeyStoreMixin(DatabaseStoreMixin):
    async def create_api_key(
        self,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: list[str] | None,
        created_by: str,
        expires_at: datetime | None = None,
    ) -> ApiKey:
        """Create a new API key record."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                api_key = ApiKey(
                    name=name,
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    scopes=scopes,
                    created_by=created_by,
                    expires_at=expires_at,
                )
                session.add(api_key)
                await session.flush()
                if scopes:
                    for (
                        action,
                        resource_type,
                        resource_id,
                    ) in dashboard_api_capability_specs(scopes):
                        await _upsert_capability_in_session(
                            session,
                            subject_id=f"api-key:{api_key.key_id}",
                            action=action,
                            resource_type=resource_type,
                            resource_id=resource_id,
                            config_id=None,
                            created_by=created_by,
                            expires_at=expires_at,
                        )
                await session.refresh(api_key)
                return api_key

    async def list_api_keys(self) -> list[ApiKey]:
        """List all API keys."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(ApiKey).order_by(desc(ApiKey.created_at))
            )
            return list(result.scalars().all())

    async def get_api_key_by_id(self, key_id: str) -> ApiKey | None:
        """Get an API key by key_id."""
        async with store_session(self) as session:
            session: AsyncSession
            result = await session.execute(
                select(ApiKey).where(ApiKey.key_id == key_id)
            )
            return result.scalar_one_or_none()

    async def get_active_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        """Get an active API key by hash (not revoked, not expired)."""
        async with store_session(self) as session:
            session: AsyncSession
            now = datetime.now(UTC)
            query = select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                col(ApiKey.revoked_at).is_(None),
                or_(col(ApiKey.expires_at).is_(None), col(ApiKey.expires_at) > now),
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def touch_api_key(self, key_id: str) -> None:
        """Update last_used_at of an API key."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    update(ApiKey)
                    .where(col(ApiKey.key_id) == key_id)
                    .values(last_used_at=datetime.now(UTC)),
                )

    async def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                now = datetime.now(UTC)
                query = (
                    update(ApiKey)
                    .where(col(ApiKey.key_id) == key_id)
                    .values(revoked_at=now)
                )
                result = T.cast(CursorResult, await session.execute(query))
                if result.rowcount:
                    await session.execute(
                        update(AuthCapability)
                        .where(
                            col(AuthCapability.subject_id) == f"api-key:{key_id}",
                            col(AuthCapability.revoked_at).is_(None),
                        )
                        .values(revoked_at=now)
                    )
                return result.rowcount > 0

    async def delete_api_key(self, key_id: str) -> bool:
        """Delete an API key."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                await session.execute(
                    delete(AuthCapability).where(
                        col(AuthCapability.subject_id) == f"api-key:{key_id}"
                    )
                )
                result = T.cast(
                    CursorResult,
                    await session.execute(
                        delete(ApiKey).where(col(ApiKey.key_id) == key_id)
                    ),
                )
                return result.rowcount > 0

    async def upsert_capability(
        self,
        *,
        subject_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        config_id: str | None = None,
        created_by: str | None = None,
        expires_at: datetime | None = None,
    ) -> AuthCapability:
        """Insert or revive one current-state capability row."""
        async with store_session(self) as session:
            session: AsyncSession
            async with session.begin():
                return await _upsert_capability_in_session(
                    session,
                    subject_id=subject_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    config_id=config_id,
                    created_by=created_by,
                    expires_at=expires_at,
                )
