from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import col, update

from astrbot.core.db.po import PlatformSession
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_get_platform_sessions_by_creator_paginated_excludes_project_sessions(
    temp_db: SQLiteDatabase,
):
    session_a = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-a",
    )
    session_b = await temp_db.create_platform_session(
        creator="alice",
        platform_id="telegram",
        session_id="session-b",
    )
    project = await temp_db.create_chatui_project(creator="alice", title="Project")
    await temp_db.add_session_to_project(session_b.session_id, project.project_id)
    await temp_db.update_platform_session(session_a.session_id, display_name="A")
    await temp_db.update_platform_session(session_b.session_id, display_name="B")

    rows, total = await temp_db.get_platform_sessions_by_creator_paginated(
        creator="alice",
        page=1,
        page_size=10,
        exclude_project_sessions=True,
    )

    assert total == 1
    assert [row["session"].session_id for row in rows] == ["session-a"]


@pytest.mark.asyncio
async def test_get_platform_sessions_by_creator_paginated_includes_project_metadata(
    temp_db: SQLiteDatabase,
):
    session_a = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-a",
    )
    session_b = await temp_db.create_platform_session(
        creator="alice",
        platform_id="telegram",
        session_id="session-b",
    )
    project = await temp_db.create_chatui_project(
        creator="alice",
        title="Alpha",
        emoji="A",
    )
    await temp_db.add_session_to_project(session_a.session_id, project.project_id)

    rows, total = await temp_db.get_platform_sessions_by_creator_paginated(
        creator="alice",
        platform_id="webchat",
        page=1,
        page_size=10,
    )

    assert total == 1
    assert rows[0]["session"].session_id == "session-a"
    assert rows[0]["project_id"] == project.project_id
    assert rows[0]["project_title"] == "Alpha"
    assert rows[0]["project_emoji"] == "A"
    assert all(row["session"].session_id != session_b.session_id for row in rows)


@pytest.mark.asyncio
async def test_get_platform_sessions_by_ids_empty_and_delete_platform_session(
    temp_db: SQLiteDatabase,
):
    created = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-delete",
    )

    assert await temp_db.get_platform_sessions_by_ids([]) == []
    assert (
        await temp_db.get_platform_session_by_id(created.session_id)
    ).session_id == "session-delete"

    await temp_db.delete_platform_session(created.session_id)

    assert await temp_db.get_platform_session_by_id(created.session_id) is None


@pytest.mark.asyncio
async def test_get_platform_sessions_by_creator_paginated_orders_by_latest_update(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    older = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-older",
    )
    newer = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-newer",
    )

    async with temp_db.get_db() as session:
        async with session.begin():
            await session.execute(
                update(PlatformSession)
                .where(col(PlatformSession.session_id) == older.session_id)
                .values(updated_at=now - timedelta(minutes=5))
            )
            await session.execute(
                update(PlatformSession)
                .where(col(PlatformSession.session_id) == newer.session_id)
                .values(updated_at=now)
            )

    rows, total = await temp_db.get_platform_sessions_by_creator_paginated(
        creator="alice",
        platform_id="webchat",
        page=1,
        page_size=10,
    )

    assert total == 2
    assert [row["session"].session_id for row in rows] == [
        "session-newer",
        "session-older",
    ]


@pytest.mark.asyncio
async def test_get_platform_sessions_by_creator_applies_platform_filter_and_returns_project_metadata(
    temp_db: SQLiteDatabase,
):
    webchat_session = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-webchat",
    )
    telegram_session = await temp_db.create_platform_session(
        creator="alice",
        platform_id="telegram",
        session_id="session-telegram",
    )
    project = await temp_db.create_chatui_project(
        creator="alice",
        title="Alpha",
        emoji="A",
    )
    await temp_db.add_session_to_project(webchat_session.session_id, project.project_id)

    rows = await temp_db.get_platform_sessions_by_creator(
        creator="alice",
        platform_id="webchat",
        page=1,
        page_size=10,
    )

    assert [row["session"].session_id for row in rows] == ["session-webchat"]
    assert rows[0]["project_id"] == project.project_id
    assert rows[0]["project_title"] == "Alpha"
    assert rows[0]["project_emoji"] == "A"
    assert all(row["session"].session_id != telegram_session.session_id for row in rows)


@pytest.mark.asyncio
async def test_update_platform_session_without_display_name_only_touches_timestamp(
    temp_db: SQLiteDatabase,
):
    created = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-touch",
        display_name="Original Name",
    )
    before = await temp_db.get_platform_session_by_id(created.session_id)
    assert before is not None
    before_updated_at = before.updated_at

    await temp_db.update_platform_session(created.session_id)

    updated = await temp_db.get_platform_session_by_id(created.session_id)
    assert updated is not None
    assert updated.display_name == "Original Name"
    assert updated.updated_at >= before_updated_at
