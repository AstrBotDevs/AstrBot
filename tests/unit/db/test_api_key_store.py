from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import update

from astrbot.core.auth.models import (
    ANY_CONFIG_SCOPE_ID,
    persist_capability_config_id,
    restore_capability_config_id,
)
from astrbot.core.db.sqlite import SQLiteDatabase


def test_capability_config_id_normalizer_round_trips_unspecified_and_concrete():
    assert persist_capability_config_id(None) == ANY_CONFIG_SCOPE_ID
    assert persist_capability_config_id("default") == "default"
    assert restore_capability_config_id(ANY_CONFIG_SCOPE_ID) is None
    assert restore_capability_config_id(None) is None
    assert restore_capability_config_id("default") == "default"


@pytest.mark.asyncio
async def test_api_key_lifecycle_filters_active_and_tracks_state(
    temp_db: SQLiteDatabase,
):
    active = await temp_db.create_api_key(
        name="active",
        key_hash="hash-active",
        key_prefix="ak-act",
        scopes=["im"],
        created_by="alice",
    )
    expired = await temp_db.create_api_key(
        name="expired",
        key_hash="hash-expired",
        key_prefix="ak-exp",
        scopes=["config"],
        created_by="alice",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    revoked = await temp_db.create_api_key(
        name="revoked",
        key_hash="hash-revoked",
        key_prefix="ak-rev",
        scopes=["plugin"],
        created_by="alice",
    )
    await temp_db.revoke_api_key(revoked.key_id)

    assert (await temp_db.get_active_api_key_by_hash("hash-active")) is not None
    assert await temp_db.get_active_api_key_by_hash("hash-expired") is None
    assert await temp_db.get_active_api_key_by_hash("hash-revoked") is None

    await temp_db.touch_api_key(active.key_id)
    touched = await temp_db.get_api_key_by_id(active.key_id)
    assert touched is not None
    assert touched.last_used_at is not None

    assert await temp_db.revoke_api_key("missing-key") is False
    assert await temp_db.delete_api_key("missing-key") is False
    assert await temp_db.delete_api_key(expired.key_id) is True
    assert await temp_db.get_api_key_by_id(expired.key_id) is None


@pytest.mark.asyncio
async def test_list_api_keys_orders_by_latest_created_at(temp_db: SQLiteDatabase):
    now = datetime.now(UTC)
    older = await temp_db.create_api_key(
        name="older",
        key_hash="hash-older",
        key_prefix="ak-old",
        scopes=["read"],
        created_by="alice",
    )
    newer = await temp_db.create_api_key(
        name="newer",
        key_hash="hash-newer",
        key_prefix="ak-new",
        scopes=["write"],
        created_by="alice",
    )

    async with temp_db.get_db() as session:
        async with session.begin():
            await session.execute(
                update(type(older))
                .where(type(older).key_id == older.key_id)
                .values(created_at=now - timedelta(minutes=2))
            )
            await session.execute(
                update(type(newer))
                .where(type(newer).key_id == newer.key_id)
                .values(created_at=now - timedelta(minutes=1))
            )

    rows = await temp_db.list_api_keys()

    assert [row.key_id for row in rows] == [newer.key_id, older.key_id]


@pytest.mark.asyncio
async def test_create_api_key_rolls_back_when_capability_write_fails(
    temp_db: SQLiteDatabase, monkeypatch: pytest.MonkeyPatch
):
    async def fail(*_args, **_kwargs):
        raise RuntimeError("capability write failed")

    monkeypatch.setattr(
        "astrbot.core.db.stores.api_keys._upsert_capability_in_session",
        fail,
    )
    with pytest.raises(RuntimeError, match="capability write failed"):
        await temp_db.create_api_key(
            name="broken",
            key_hash="hash-broken",
            key_prefix="ak-brk",
            scopes=["chat"],
            created_by="alice",
        )

    assert await temp_db.list_api_keys() == []


@pytest.mark.asyncio
async def test_upsert_capability_revives_and_keeps_scope_uniqueness(
    temp_db: SQLiteDatabase,
):
    from sqlmodel import col, select

    from astrbot.core.db.po import AuthCapability

    first = await temp_db.upsert_capability(
        subject_id="api-key:cap-1",
        action="session.read",
        resource_type="session",
        resource_id="session:v1:any",
        config_id=None,
        created_by="alice",
    )
    await temp_db.upsert_capability(
        subject_id="api-key:cap-1",
        action="session.read",
        resource_type="session",
        resource_id="session:v1:any",
        config_id=None,
        created_by="alice",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    revived = await temp_db.upsert_capability(
        subject_id="api-key:cap-1",
        action="session.read",
        resource_type="session",
        resource_id="session:v1:any",
        config_id=None,
        created_by="bob",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    concrete = await temp_db.upsert_capability(
        subject_id="api-key:cap-1",
        action="session.read",
        resource_type="session",
        resource_id="session:v1:any",
        config_id="default",
        created_by="alice",
    )

    async with temp_db.get_db() as session:
        rows = list(
            (
                await session.execute(
                    select(AuthCapability).where(
                        col(AuthCapability.subject_id) == "api-key:cap-1"
                    )
                )
            ).scalars()
        )

    config_ids = {row.config_id for row in rows}
    assert revived.capability_id == first.capability_id
    assert revived.revoked_at is None
    assert revived.created_by == "bob"
    assert concrete.capability_id != first.capability_id
    assert config_ids == {ANY_CONFIG_SCOPE_ID, "default"}
    assert len(rows) == 2
