import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_add_session_to_project_replaces_existing_relation_and_queries_follow_latest(
    temp_db: SQLiteDatabase,
):
    session = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-a",
    )
    first_project = await temp_db.create_chatui_project(creator="alice", title="First")
    second_project = await temp_db.create_chatui_project(
        creator="alice",
        title="Second",
    )

    await temp_db.add_session_to_project(session.session_id, first_project.project_id)
    await temp_db.add_session_to_project(session.session_id, second_project.project_id)

    first_project_sessions = await temp_db.get_project_sessions(
        first_project.project_id
    )
    second_project_sessions = await temp_db.get_project_sessions(
        second_project.project_id
    )
    linked_project = await temp_db.get_project_by_session(session.session_id, "alice")

    assert first_project_sessions == []
    assert [item.session_id for item in second_project_sessions] == [session.session_id]
    assert linked_project is not None
    assert linked_project.project_id == second_project.project_id


@pytest.mark.asyncio
async def test_remove_session_from_project_detaches_relation_without_deleting_session(
    temp_db: SQLiteDatabase,
):
    session = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-project",
    )
    project = await temp_db.create_chatui_project(creator="alice", title="Alpha")
    await temp_db.add_session_to_project(session.session_id, project.project_id)

    await temp_db.remove_session_from_project(session.session_id)

    assert await temp_db.get_project_by_session(session.session_id, "alice") is None
    assert await temp_db.get_project_sessions(project.project_id) == []
    remaining = await temp_db.get_platform_session_by_id(session.session_id)
    assert remaining is not None
    assert remaining.session_id == session.session_id


@pytest.mark.asyncio
async def test_delete_chatui_project_removes_relations_but_preserves_sessions(
    temp_db: SQLiteDatabase,
):
    session = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-project-delete",
    )
    project = await temp_db.create_chatui_project(creator="alice", title="Alpha")
    await temp_db.add_session_to_project(session.session_id, project.project_id)

    await temp_db.delete_chatui_project(project.project_id)

    assert await temp_db.get_chatui_project_by_id(project.project_id) is None
    assert await temp_db.get_project_by_session(session.session_id, "alice") is None
    remaining = await temp_db.get_platform_session_by_id(session.session_id)
    assert remaining is not None
    assert remaining.session_id == session.session_id


@pytest.mark.asyncio
async def test_get_project_by_session_is_scoped_to_creator(temp_db: SQLiteDatabase):
    session = await temp_db.create_platform_session(
        creator="alice",
        platform_id="webchat",
        session_id="session-a",
    )
    project = await temp_db.create_chatui_project(creator="alice", title="Alpha")
    await temp_db.add_session_to_project(session.session_id, project.project_id)

    linked = await temp_db.get_project_by_session(session.session_id, "alice")
    hidden = await temp_db.get_project_by_session(session.session_id, "bob")

    assert linked is not None
    assert linked.project_id == project.project_id
    assert hidden is None
