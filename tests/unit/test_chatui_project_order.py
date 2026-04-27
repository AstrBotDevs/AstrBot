import pytest


@pytest.mark.asyncio
async def test_project_sessions_preserve_custom_order(temp_db):
    await temp_db.initialize()

    project = await temp_db.create_chatui_project("user", "Project")
    first = await temp_db.create_platform_session(
        creator="user",
        session_id="session-1",
        display_name="First",
    )
    second = await temp_db.create_platform_session(
        creator="user",
        session_id="session-2",
        display_name="Second",
    )
    third = await temp_db.create_platform_session(
        creator="user",
        session_id="session-3",
        display_name="Third",
    )

    await temp_db.add_session_to_project(first.session_id, project.project_id)
    await temp_db.add_session_to_project(second.session_id, project.project_id)
    await temp_db.add_session_to_project(third.session_id, project.project_id)

    await temp_db.reorder_project_sessions(
        project.project_id,
        [third.session_id, first.session_id, second.session_id],
    )

    sessions = await temp_db.get_project_sessions(project.project_id)
    assert [session.session_id for session in sessions] == [
        third.session_id,
        first.session_id,
        second.session_id,
    ]


@pytest.mark.asyncio
async def test_unassigned_sessions_preserve_custom_order(temp_db):
    await temp_db.initialize()

    first = await temp_db.create_platform_session(
        creator="user",
        session_id="session-1",
        display_name="First",
    )
    second = await temp_db.create_platform_session(
        creator="user",
        session_id="session-2",
        display_name="Second",
    )
    third = await temp_db.create_platform_session(
        creator="user",
        session_id="session-3",
        display_name="Third",
    )

    await temp_db.reorder_platform_sessions(
        "user",
        [third.session_id, first.session_id, second.session_id],
    )

    sessions, _ = await temp_db.get_platform_sessions_by_creator_paginated(
        creator="user",
        exclude_project_sessions=True,
    )
    assert [item["session"].session_id for item in sessions] == [
        third.session_id,
        first.session_id,
        second.session_id,
    ]
