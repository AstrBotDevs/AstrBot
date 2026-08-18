import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import col, text, update

from astrbot.core.db import is_aiosqlite_worker_thread
from astrbot.core.db.po import (
    MemoryFact,
    PlatformMessageHistory,
    PlatformSession,
    ProviderStat,
    WebChatThread,
)
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_platform_stats_upsert_count_and_time_window_ordering(
    temp_db: SQLiteDatabase,
):
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    older_hour = now - timedelta(hours=2)
    newer_hour = now - timedelta(hours=1)

    await temp_db.insert_platform_stats(
        "telegram",
        "bot",
        count=2,
        timestamp=older_hour,
    )
    await temp_db.insert_platform_stats(
        "telegram",
        "bot",
        count=3,
        timestamp=older_hour,
    )
    await temp_db.insert_platform_stats(
        "discord",
        "bot",
        count=1,
        timestamp=newer_hour,
    )

    rows = await temp_db.get_platform_stats(offset_sec=3 * 3600)
    recent_rows = await temp_db.get_platform_stats(offset_sec=30 * 60)

    assert await temp_db.count_platform_stats() == 2
    assert [(row.platform_id, row.count) for row in rows] == [
        ("telegram", 5),
        ("discord", 1),
    ]
    assert recent_rows == []


@pytest.mark.asyncio
async def test_insert_provider_stat_normalizes_defaults_and_persists_numbers(
    temp_db: SQLiteDatabase,
):
    record = await temp_db.insert_provider_stat(
        umo="webchat:FriendMessage:session-1",
        provider_id="provider-a",
        provider_model=None,
        conversation_id=None,
        stats={
            "token_usage": {
                "input_other": "4",
                "input_cached": None,
                "output": 2.7,
            },
            "start_time": "1.5",
            "end_time": None,
            "time_to_first_token": "0.25",
        },
    )

    async with temp_db.get_db() as session:
        stored = await session.get(ProviderStat, record.id)

    assert stored is not None
    assert stored.umo == "webchat:FriendMessage:session-1"
    assert stored.provider_id == "provider-a"
    assert stored.provider_model is None
    assert stored.status == "completed"
    assert stored.agent_type == "internal"
    assert stored.token_input_other == 4
    assert stored.token_input_cached == 0
    assert stored.token_output == 2
    assert stored.start_time == 1.5
    assert stored.end_time == 0.0
    assert stored.time_to_first_token == 0.25


@pytest.mark.asyncio
async def test_persona_runtime_and_memory_sqlite_interfaces(temp_db: SQLiteDatabase):
    state = await temp_db.upsert_persona_session_state(
        persona_id="persona-a",
        umo="webchat:FriendMessage:session-a",
        agent_state="running",
        talk_frequency_adjust=1.25,
        consecutive_idle_count=0,
        extra_state={"proactive_enabled": False},
    )
    updated_state = await temp_db.upsert_persona_session_state(
        persona_id="persona-a",
        umo="webchat:FriendMessage:session-a",
        agent_state="wait",
        talk_frequency_adjust=0.9,
        consecutive_idle_count=1,
        extra_state={"proactive_enabled": True},
    )
    fact, created = await temp_db.upsert_memory_fact(
        person_id="user-a",
        chat_id="webchat:FriendMessage:session-a",
        scope_id="isolated:webchat:FriendMessage:session-a",
        fact_text="User likes green tea.",
        fact_type="preference",
        source_message_id="conv-a:1",
        evidence_message_ids=["conv-a:1"],
    )
    merged_fact, merged_created = await temp_db.upsert_memory_fact(
        person_id="user-a",
        chat_id="webchat:FriendMessage:session-a",
        scope_id="isolated:webchat:FriendMessage:session-a",
        fact_text="User likes green tea.",
        fact_type="preference",
        source_message_id="conv-a:2",
        evidence_message_ids=["conv-a:2"],
    )
    profile = await temp_db.upsert_memory_profile(
        person_id="user-a",
        chat_scope="isolated:webchat:FriendMessage:session-a",
        profile_text="User likes green tea.",
    )
    log = await temp_db.insert_memory_operation_log(
        operator="test",
        target_type="memory_fact",
        target_id=str(fact.id),
        action="merge",
        payload={"source": "unit"},
    )

    assert state.id == updated_state.id
    assert updated_state.agent_state == "wait"
    assert updated_state.extra_state == {"proactive_enabled": True}
    assert created is True
    assert merged_created is False
    assert merged_fact.id == fact.id
    assert merged_fact.evidence_message_ids == ["conv-a:1", "conv-a:2"]
    assert (
        await temp_db.get_memory_profile("user-a", profile.chat_scope)
    ).id == profile.id
    assert [row.operation_id for row in await temp_db.list_memory_operation_logs()] == [
        log.operation_id
    ]
    episode = await temp_db.upsert_memory_episode(
        episode_id="episode-a",
        chat_id="webchat:FriendMessage:session-a",
        scope_id="isolated:webchat:FriendMessage:session-a",
        title="Green tea preference",
        summary="User said they like green tea.",
        participant_ids=["user-a"],
        source_message_ids=["conv-a:1"],
    )
    updated_episode = await temp_db.upsert_memory_episode(
        episode_id="episode-a",
        chat_id="webchat:FriendMessage:session-a",
        scope_id="isolated:webchat:FriendMessage:session-a",
        title="Green tea preference updated",
        summary="User repeated that they like green tea.",
        participant_ids=["user-a"],
        source_message_ids=["conv-a:1", "conv-a:2"],
    )
    scope_policy = await temp_db.upsert_memory_scope_policy(
        owner_scope_id="isolated:webchat:FriendMessage:session-a",
        target_scope_id="isolated:webchat:FriendMessage:session-b",
    )

    assert episode.id == updated_episode.id
    assert [
        item.title
        for item in await temp_db.list_memory_episodes(
            chat_ids=["webchat:FriendMessage:session-a"],
            query="green tea",
        )
    ] == ["Green tea preference updated"]
    assert [
        item.target_scope_id
        for item in await temp_db.list_memory_scope_policies(
            owner_scope_id="isolated:webchat:FriendMessage:session-a"
        )
    ] == [scope_policy.target_scope_id]
    scope_logs = await temp_db.list_memory_operation_logs(
        target_type="memory_scope_policy"
    )
    assert scope_logs[0].action == "enable"
    tuning_task = await temp_db.upsert_memory_tuning_task(
        task_id="tune-a",
        task_type="retrieval_probe",
        target_scope="isolated:webchat:FriendMessage:session-a",
        candidate_config={"limit": 3},
        evaluation_result={"coverage": 1.0},
        status="completed",
    )
    assert [
        task.task_id
        for task in await temp_db.list_memory_tuning_tasks(
            target_scope="isolated:webchat:FriendMessage:session-a",
            status="completed",
        )
    ] == [tuning_task.task_id]

    async with temp_db.get_db() as session:
        stored_fact = await session.get(MemoryFact, fact.id)
    assert stored_fact is not None
    assert stored_fact.fact_text == "User likes green tea."

    assert await temp_db.update_memory_fact_status(
        fact.id,
        status="deleted",
        operator="unit",
        reason="incorrect",
    )
    deleted = await temp_db.get_memory_fact(fact.id)
    assert deleted is not None
    assert deleted.status == "deleted"
    assert await temp_db.list_memory_facts(person_id="user-a") == []
    assert (await temp_db.count_memory_facts(person_id="user-a", status="deleted")) == 1
    merged_deleted, merged_deleted_created = await temp_db.upsert_memory_fact(
        person_id="user-a",
        chat_id="webchat:FriendMessage:session-a",
        scope_id="isolated:webchat:FriendMessage:session-a",
        fact_text="User likes green tea.",
        fact_type="preference",
        source_message_id="conv-a:deleted-merge",
        evidence_message_ids=["conv-a:deleted-merge"],
    )
    assert merged_deleted_created is False
    assert merged_deleted.id == fact.id
    assert merged_deleted.status == "deleted"
    assert await temp_db.list_memory_facts(person_id="user-a") == []

    assert await temp_db.update_memory_fact_status(
        fact.id,
        status="active",
        operator="unit",
        reason="restored",
    )
    restored = await temp_db.get_memory_fact(fact.id)
    assert restored is not None
    assert restored.status == "active"
    updated_fact = await temp_db.update_memory_fact(
        fact.id,
        fact_text="User likes jasmine tea.",
        confidence=0.8,
        operator="unit",
        reason="dashboard edit",
    )
    assert updated_fact is not None
    assert updated_fact.fact_text == "User likes jasmine tea."
    assert (
        await temp_db.count_memory_facts(
            person_id="user-a",
            query="jasmine",
            status="active",
        )
    ) == 1
    assert [
        item.id
        for item in await temp_db.list_memory_profiles(
            person_id="user-a",
            limit=5,
        )
    ] == [profile.id]
    assert await temp_db.count_memory_profiles(person_id="user-a") == 1
    assert await temp_db.count_memory_episodes(status="active") == 1
    logs = await temp_db.list_memory_operation_logs(target_id=str(fact.id))
    assert [row.action for row in logs[:3]] == ["update", "restore", "delete"]
    assert (
        await temp_db.count_memory_operation_logs(
            target_type="memory_fact",
            target_id=str(fact.id),
        )
    ) == 4

    expression = await temp_db.upsert_persona_expression_asset(
        persona_id="persona-a",
        scope="isolated:webchat:FriendMessage:session-a",
        trigger_scene="general",
        style_text="Prefer concise replies.",
        source_message_id="conv-a:3",
        score=0.5,
    )
    updated_expression = await temp_db.upsert_persona_expression_asset(
        persona_id="persona-a",
        scope="isolated:webchat:FriendMessage:session-a",
        trigger_scene="general",
        style_text="Prefer concise replies.",
        source_message_id="conv-a:4",
        score=0.7,
    )
    jargon = await temp_db.upsert_persona_jargon_asset(
        persona_id="persona-a",
        scope="isolated:webchat:FriendMessage:session-a",
        term="ship-it",
        meaning=None,
        source_message_id="conv-a:5",
        score=0.6,
    )
    policy = await temp_db.upsert_persona_behavior_policy(
        persona_id="persona-a",
        scope="isolated:webchat:FriendMessage:session-a",
        situation="simple request",
        preferred_action="Answer briefly.",
        confidence=0.6,
    )

    assert expression.id == updated_expression.id
    assert updated_expression.score == 0.7
    assert [
        item.style_text
        for item in await temp_db.list_persona_expression_assets(
            persona_id="persona-a",
            scope="isolated:webchat:FriendMessage:session-a",
        )
    ] == ["Prefer concise replies."]
    assert [
        item.term
        for item in await temp_db.list_persona_jargon_assets(
            persona_id="persona-a",
            scope="isolated:webchat:FriendMessage:session-a",
            approved=False,
        )
    ] == [jargon.term]
    assert [
        item.preferred_action
        for item in await temp_db.list_persona_behavior_policies(
            persona_id="persona-a",
            scope="isolated:webchat:FriendMessage:session-a",
        )
    ] == [policy.preferred_action]


@pytest.mark.asyncio
async def test_update_conversation_returns_none_for_empty_update_and_applies_partial_fields(
    temp_db: SQLiteDatabase,
):
    conversation = await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        title="Original",
        content=[{"text": "before"}],
        persona_id="persona-before",
        cid="conv-update",
    )

    assert await temp_db.update_conversation(conversation.conversation_id) is None

    updated = await temp_db.update_conversation(
        conversation.conversation_id,
        title="Updated",
        content=[{"text": "after"}],
        token_usage=12,
    )

    assert updated is not None
    assert updated.conversation_id == conversation.conversation_id
    assert updated.title == "Updated"
    assert updated.persona_id == "persona-before"
    assert updated.content == [{"text": "after"}]
    assert updated.token_usage == 12


@pytest.mark.asyncio
async def test_get_conversations_filters_and_get_all_conversations_paginates_by_latest(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        title="Old telegram",
        cid="conv-old",
        created_at=now - timedelta(minutes=3),
        updated_at=now - timedelta(minutes=3),
    )
    await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        title="New telegram",
        cid="conv-new",
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )
    await temp_db.create_conversation(
        user_id="discord:FriendMessage:user-2",
        platform_id="discord",
        title="Discord",
        cid="conv-discord",
        created_at=now - timedelta(minutes=2),
        updated_at=now - timedelta(minutes=2),
    )

    filtered = await temp_db.get_conversations(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
    )
    paged = await temp_db.get_all_conversations(page=1, page_size=2)

    assert [conversation.conversation_id for conversation in filtered] == [
        "conv-new",
        "conv-old",
    ]
    assert [conversation.conversation_id for conversation in paged] == [
        "conv-new",
        "conv-discord",
    ]


@pytest.mark.asyncio
async def test_delete_conversation_and_delete_conversations_by_user_id_scope_correctly(
    temp_db: SQLiteDatabase,
):
    target = await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        cid="conv-target",
    )
    await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        cid="conv-user-delete",
    )
    survivor = await temp_db.create_conversation(
        user_id="discord:FriendMessage:user-2",
        platform_id="discord",
        cid="conv-survivor",
    )

    await temp_db.delete_conversation(target.conversation_id)
    await temp_db.delete_conversations_by_user_id("telegram:FriendMessage:user-1")

    assert await temp_db.get_conversation_by_id(target.conversation_id) is None
    assert await temp_db.get_conversation_by_id("conv-user-delete") is None
    remaining = await temp_db.get_conversation_by_id(survivor.conversation_id)
    assert remaining is not None
    assert remaining.conversation_id == survivor.conversation_id


@pytest.mark.asyncio
async def test_get_filtered_conversations_combines_filters_and_paginates(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        title="Alpha match",
        content=[{"text": "one"}],
        cid="conv-1",
        created_at=now - timedelta(minutes=3),
        updated_at=now - timedelta(minutes=3),
    )
    await temp_db.create_conversation(
        user_id="telegram:GroupMessage:user-2",
        platform_id="telegram",
        title="Alpha group",
        content=[{"text": "two"}],
        cid="conv-2",
        created_at=now - timedelta(minutes=2),
        updated_at=now - timedelta(minutes=2),
    )
    await temp_db.create_conversation(
        user_id="discord:FriendMessage:user-3",
        platform_id="discord",
        title="Alpha discord",
        content=[{"text": "three"}],
        cid="conv-3",
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )

    conversations, total = await temp_db.get_filtered_conversations(
        page=1,
        page_size=1,
        platform_ids=["telegram", "discord"],
        search_query="Alpha",
        message_types=["FriendMessage"],
        platforms=["telegram"],
    )

    assert total == 1
    assert [conversation.conversation_id for conversation in conversations] == [
        "conv-1"
    ]


@pytest.mark.asyncio
async def test_get_filtered_conversations_supports_unicode_and_literal_wildcards(
    temp_db: SQLiteDatabase,
):
    await temp_db.create_conversation(
        user_id="wechat:FriendMessage:user-1",
        platform_id="wechat",
        title="中文 100% 命中",
        content=[{"text": "内容"}],
        cid="conv-unicode",
    )
    await temp_db.create_conversation(
        user_id="wechat:FriendMessage:user-2",
        platform_id="wechat",
        title="中文 100X 命中",
        content=[{"text": "内容"}],
        cid="conv-other",
    )

    conversations, total = await temp_db.get_filtered_conversations(
        page=1,
        page_size=10,
        search_query="中文 100%",
    )

    assert total == 1
    assert [conversation.conversation_id for conversation in conversations] == [
        "conv-unicode"
    ]


@pytest.mark.asyncio
async def test_get_session_conversations_joins_preferences_conversations_and_personas(
    temp_db: SQLiteDatabase,
):
    persona = await temp_db.insert_persona(
        persona_id="persona-a",
        system_prompt="prompt",
    )
    await temp_db.create_conversation(
        user_id="umo-1",
        platform_id="webchat",
        title="Session Alpha",
        persona_id=persona.persona_id,
        cid="conv-a",
    )
    await temp_db.create_conversation(
        user_id="umo-2",
        platform_id="telegram",
        title="Other Title",
        cid="conv-b",
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "webchat:FriendMessage:webchat!alice!session-a",
        "sel_conv_id",
        {"val": "conv-a"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "telegram:FriendMessage:telegram!alice!session-b",
        "sel_conv_id",
        {"val": "conv-b"},
    )

    rows, total = await temp_db.get_session_conversations(
        page=1,
        page_size=10,
        search_query="Alpha",
        platform="webchat",
    )

    assert total == 1
    assert rows == [
        {
            "session_id": "webchat:FriendMessage:webchat!alice!session-a",
            "conversation_id": "conv-a",
            "persona_id": "persona-a",
            "title": "Session Alpha",
            "persona_name": "persona-a",
        }
    ]


@pytest.mark.asyncio
async def test_get_session_conversations_handles_missing_related_rows_and_pagination(
    temp_db: SQLiteDatabase,
):
    await temp_db.create_conversation(
        user_id="umo-1",
        platform_id="webchat",
        title="Alpha",
        cid="conv-a",
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "a:webchat:session",
        "sel_conv_id",
        {"val": "missing-conv"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "b:webchat:session",
        "sel_conv_id",
        {"val": "conv-a"},
    )

    page_one, total = await temp_db.get_session_conversations(
        page=1,
        page_size=1,
    )
    page_two, _ = await temp_db.get_session_conversations(
        page=2,
        page_size=1,
    )
    missing = await temp_db.get_session_conversations(
        page=1,
        page_size=10,
        search_query="does-not-exist",
        platform="discord",
    )

    assert total == 2
    assert page_one == [
        {
            "session_id": "a:webchat:session",
            "conversation_id": "missing-conv",
            "persona_id": None,
            "title": None,
            "persona_name": None,
        }
    ]
    assert page_two == [
        {
            "session_id": "b:webchat:session",
            "conversation_id": "conv-a",
            "persona_id": None,
            "title": "Alpha",
            "persona_name": None,
        }
    ]
    assert missing == ([], 0)


@pytest.mark.asyncio
async def test_batch_update_sort_order_reorders_personas_and_folders(
    temp_db: SQLiteDatabase,
):
    root_b = await temp_db.insert_persona_folder(name="B", sort_order=20)
    root_a = await temp_db.insert_persona_folder(name="A", sort_order=10)
    await temp_db.insert_persona(
        persona_id="persona-b",
        system_prompt="prompt",
        folder_id=None,
        sort_order=20,
    )
    await temp_db.insert_persona(
        persona_id="persona-a",
        system_prompt="prompt",
        folder_id=None,
        sort_order=10,
    )

    await temp_db.batch_update_sort_order(
        [
            {"id": root_b.folder_id, "type": "folder", "sort_order": 0},
            {"id": "persona-b", "type": "persona", "sort_order": 0},
            {"id": None, "type": "persona", "sort_order": 99},
            {"id": root_a.folder_id, "type": "unknown", "sort_order": 0},
        ]
    )

    folders = await temp_db.get_persona_folders()
    personas = await temp_db.get_personas_by_folder(None)

    assert [folder.name for folder in folders] == ["B", "A"]
    assert [persona.persona_id for persona in personas] == ["persona-b", "persona-a"]


@pytest.mark.asyncio
async def test_preference_upsert_filter_remove_and_clear_paths(temp_db: SQLiteDatabase):
    created = await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "sel_conv_id",
        {"val": "conv-a"},
    )
    updated = await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "sel_conv_id",
        {"val": "conv-b"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "theme",
        {"val": "dark"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "session-b",
        "sel_conv_id",
        {"val": "conv-c"},
    )

    assert created.scope_id == "session-a"
    assert updated.value == {"val": "conv-b"}
    assert (await temp_db.get_preference("umo", "session-a", "sel_conv_id")).value == {
        "val": "conv-b"
    }
    assert len(await temp_db.get_preferences("umo")) == 3
    assert [
        item.key for item in await temp_db.get_preferences("umo", scope_id="session-a")
    ] == ["sel_conv_id", "theme"]
    assert [
        item.scope_id
        for item in await temp_db.get_preferences("umo", key="sel_conv_id")
    ] == ["session-a", "session-b"]

    await temp_db.remove_preference("umo", "session-a", "sel_conv_id")
    assert await temp_db.get_preference("umo", "session-a", "sel_conv_id") is None

    await temp_db.clear_preferences("umo", "session-a")
    assert await temp_db.get_preferences("umo", scope_id="session-a") == []
    remaining = await temp_db.get_preferences("umo")
    assert [(item.scope_id, item.key) for item in remaining] == [
        ("session-b", "sel_conv_id")
    ]


@pytest.mark.asyncio
async def test_update_persona_folder_can_clear_parent_and_description(
    temp_db: SQLiteDatabase,
):
    parent = await temp_db.insert_persona_folder(name="Parent")
    child = await temp_db.insert_persona_folder(
        name="Child",
        parent_id=parent.folder_id,
        description="desc",
        sort_order=5,
    )

    updated = await temp_db.update_persona_folder(
        child.folder_id,
        parent_id=None,
        description=None,
        sort_order=1,
    )

    assert updated is not None
    assert updated.parent_id is None
    assert updated.description is None
    assert updated.sort_order == 1


@pytest.mark.asyncio
async def test_upsert_umo_alias_updates_existing_row_and_filtered_reads(
    temp_db: SQLiteDatabase,
):
    created = await temp_db.upsert_umo_alias(
        "umo-1",
        "sender-1",
        "Auto One",
        "Alias One",
    )
    updated = await temp_db.upsert_umo_alias(
        "umo-1",
        "sender-2",
        None,
        "Alias Two",
    )
    await temp_db.upsert_umo_alias(
        "umo-2",
        "sender-3",
        "Auto Two",
        None,
    )

    assert created.umo == "umo-1"
    assert updated.umo == "umo-1"
    assert updated.creator_sender_id == "sender-2"
    assert updated.auto_name is None
    assert updated.user_alias == "Alias Two"

    filtered = await temp_db.get_umo_aliases(["umo-2"])
    assert [alias.umo for alias in filtered] == ["umo-2"]
    assert await temp_db.get_umo_aliases([]) == []


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
async def test_platform_message_history_update_and_offset_delete(
    temp_db: SQLiteDatabase,
):
    now = datetime.now()
    older = await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-1",
        content={"type": "user", "message": [{"type": "plain", "text": "old"}]},
        llm_checkpoint_id="ck-old",
    )
    newer = await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-1",
        content={"type": "bot", "message": [{"type": "plain", "text": "new"}]},
        llm_checkpoint_id="ck-new",
    )

    async with temp_db.get_db() as session:
        async with session.begin():
            await session.execute(
                update(PlatformMessageHistory)
                .where(col(PlatformMessageHistory.id) == older.id)
                .values(created_at=now - timedelta(days=3))
            )
            await session.execute(
                update(PlatformMessageHistory)
                .where(col(PlatformMessageHistory.id) == newer.id)
                .values(created_at=now)
            )

    await temp_db.update_platform_message_history(
        newer.id,
        content={"type": "bot", "message": [{"type": "plain", "text": "updated"}]},
        llm_checkpoint_id="ck-updated",
    )
    updated_before_delete = await temp_db.get_platform_message_history_by_id(newer.id)
    assert updated_before_delete is not None
    assert updated_before_delete.content == {
        "type": "bot",
        "message": [{"type": "plain", "text": "updated"}],
    }
    assert updated_before_delete.llm_checkpoint_id == "ck-updated"

    await temp_db.delete_platform_message_offset(
        "webchat",
        "session-1",
        offset_sec=3600,
    )

    remaining = await temp_db.get_platform_message_history("webchat", "session-1")
    assert [row.id for row in remaining] == [older.id]

    updated_row = await temp_db.get_platform_message_history_by_id(newer.id)
    assert updated_row is None
    preserved_row = await temp_db.get_platform_message_history_by_id(older.id)
    assert preserved_row is not None
    assert preserved_row.llm_checkpoint_id == "ck-old"


@pytest.mark.asyncio
async def test_attachment_reads_and_deletes_return_expected_counts(
    temp_db: SQLiteDatabase,
):
    first = await temp_db.insert_attachment(
        path="/tmp/a.txt",
        type="file",
        mime_type="text/plain",
    )
    second = await temp_db.insert_attachment(
        path="/tmp/b.png",
        type="image",
        mime_type="image/png",
    )

    fetched = await temp_db.get_attachments([second.attachment_id, first.attachment_id])
    assert {attachment.attachment_id for attachment in fetched} == {
        first.attachment_id,
        second.attachment_id,
    }
    assert await temp_db.delete_attachment("missing") is False

    deleted_count = await temp_db.delete_attachments(
        [first.attachment_id, "missing", second.attachment_id]
    )

    assert deleted_count == 2
    assert await temp_db.get_attachment_by_id(first.attachment_id) is None
    assert await temp_db.get_attachment_by_id(second.attachment_id) is None
    assert await temp_db.delete_attachments([]) == 0


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
async def test_webchat_thread_queries_and_bulk_delete_paths(temp_db: SQLiteDatabase):
    first = await temp_db.create_webchat_thread(
        creator="alice",
        parent_session_id="session-1",
        parent_message_id=10,
        base_checkpoint_id="ck-1",
        selected_text="quote one",
    )
    second = await temp_db.create_webchat_thread(
        creator="bob",
        parent_session_id="session-1",
        parent_message_id=11,
        base_checkpoint_id="ck-2",
        selected_text="quote two",
    )
    third = await temp_db.create_webchat_thread(
        creator="alice",
        parent_session_id="session-2",
        parent_message_id=10,
        base_checkpoint_id="ck-3",
        selected_text="quote three",
    )

    by_session = await temp_db.get_webchat_threads_by_parent_session(
        "session-1",
        creator="alice",
    )
    assert [thread.thread_id for thread in by_session] == [first.thread_id]

    same_text = await temp_db.get_webchat_thread_by_parent_message_and_text(
        "session-1",
        10,
        "quote one",
        creator="alice",
    )
    assert same_text is not None
    assert same_text.thread_id == first.thread_id
    assert (
        await temp_db.get_webchat_thread_by_parent_message_and_text(
            "session-1",
            10,
            "quote one",
            creator="bob",
        )
        is None
    )

    deleted_by_message = await temp_db.delete_webchat_threads_by_parent_message_ids(
        "session-1",
        [11, 99],
    )
    assert deleted_by_message == [second.thread_id]
    assert await temp_db.get_webchat_thread_by_id(second.thread_id) is None
    assert (
        await temp_db.delete_webchat_threads_by_parent_message_ids("session-1", [])
        == []
    )

    deleted_by_session = await temp_db.delete_webchat_threads_by_parent_session(
        "session-1"
    )
    assert deleted_by_session == [first.thread_id]
    assert await temp_db.get_webchat_thread_by_id(first.thread_id) is None
    assert await temp_db.get_webchat_thread_by_id(third.thread_id) is not None


@pytest.mark.asyncio
async def test_command_config_upsert_applies_defaults_and_preserves_on_none_updates(
    temp_db: SQLiteDatabase,
):
    created = await temp_db.upsert_command_config(
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha",
        module_path="plugin.alpha",
        original_command="hello",
    )

    assert created.enabled is True
    assert created.keep_original_alias is False
    assert created.conflict_key == "hello"
    assert created.auto_managed is False

    updated = await temp_db.upsert_command_config(
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha 2",
        module_path="plugin.alpha.v2",
        original_command="hello",
        resolved_command="/hello",
        enabled=False,
        note="updated",
        auto_managed=True,
    )
    preserved = await temp_db.upsert_command_config(
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha 3",
        module_path="plugin.alpha.v3",
        original_command="hello",
        resolved_command=None,
        enabled=None,
        note=None,
        auto_managed=None,
    )

    assert updated.resolved_command == "/hello"
    assert updated.enabled is False
    assert updated.note == "updated"
    assert updated.auto_managed is True
    assert preserved.plugin_name == "Alpha 3"
    assert preserved.module_path == "plugin.alpha.v3"
    assert preserved.resolved_command == "/hello"
    assert preserved.enabled is False
    assert preserved.note == "updated"
    assert preserved.auto_managed is True

    await temp_db.delete_command_configs(["plugin.alpha.handler"])
    assert await temp_db.get_command_config("plugin.alpha.handler") is None
    await temp_db.delete_command_configs([])


@pytest.mark.asyncio
async def test_command_conflict_upsert_filter_and_delete(temp_db: SQLiteDatabase):
    pending = await temp_db.upsert_command_conflict(
        conflict_key="hello",
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha",
    )
    resolved = await temp_db.upsert_command_conflict(
        conflict_key="hello",
        handler_full_name="plugin.beta.handler",
        plugin_name="Beta",
        status="resolved",
        resolution="rename",
        resolved_command="/hello_beta",
        auto_generated=True,
    )
    updated_pending = await temp_db.upsert_command_conflict(
        conflict_key="hello",
        handler_full_name="plugin.alpha.handler",
        plugin_name="Alpha v2",
        status="ignored",
        note="manual override",
    )

    assert pending.status == "pending"
    assert resolved.status == "resolved"
    assert resolved.auto_generated is True
    assert updated_pending.plugin_name == "Alpha v2"
    assert updated_pending.status == "ignored"
    assert updated_pending.note == "manual override"

    ignored_rows = await temp_db.list_command_conflicts(status="ignored")
    assert [row.handler_full_name for row in ignored_rows] == ["plugin.alpha.handler"]

    await temp_db.delete_command_conflicts([pending.id, resolved.id])
    remaining = await temp_db.list_command_conflicts()
    assert remaining == []
    await temp_db.delete_command_conflicts([])


@pytest.mark.asyncio
async def test_cron_job_update_distinguishes_not_set_from_explicit_none(
    temp_db: SQLiteDatabase,
):
    scheduled_time = datetime.now(UTC) + timedelta(hours=1)
    job = await temp_db.create_cron_job(
        name="Morning sync",
        job_type="sync",
        cron_expression="0 8 * * *",
        timezone="Asia/Shanghai",
        payload={"scope": "all"},
        description="daily",
        enabled=True,
        persistent=True,
        run_once=False,
        status="scheduled",
        job_id="job-1",
    )

    updated = await temp_db.update_cron_job(
        job.job_id,
        cron_expression=None,
        payload={"scope": "one"},
        enabled=False,
        next_run_time=scheduled_time,
        last_error=None,
    )

    assert updated is not None
    assert updated.job_id == "job-1"
    assert updated.name == "Morning sync"
    assert updated.cron_expression is None
    assert updated.timezone == "Asia/Shanghai"
    assert updated.payload == {"scope": "one"}
    assert updated.enabled is False
    assert updated.next_run_time == scheduled_time.replace(tzinfo=None)
    assert updated.last_error is None

    untouched = await temp_db.update_cron_job("missing-job", status="failed")
    assert untouched is None

    filtered = await temp_db.list_cron_jobs(job_type="sync")
    assert [item.job_id for item in filtered] == ["job-1"]


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


@pytest.mark.asyncio
async def test_get_platform_message_history_is_paginated_and_scoped_by_platform_and_user(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    first = await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-1",
        content={"type": "user", "message": [{"type": "plain", "text": "first"}]},
    )
    second = await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-1",
        content={"type": "bot", "message": [{"type": "plain", "text": "second"}]},
    )
    await temp_db.insert_platform_message_history(
        platform_id="telegram",
        user_id="session-1",
        content={
            "type": "user",
            "message": [{"type": "plain", "text": "other platform"}],
        },
    )
    await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-2",
        content={"type": "user", "message": [{"type": "plain", "text": "other user"}]},
    )

    async with temp_db.get_db() as session:
        async with session.begin():
            await session.execute(
                update(PlatformMessageHistory)
                .where(col(PlatformMessageHistory.id) == first.id)
                .values(created_at=now - timedelta(minutes=2))
            )
            await session.execute(
                update(PlatformMessageHistory)
                .where(col(PlatformMessageHistory.id) == second.id)
                .values(created_at=now - timedelta(minutes=1))
            )

    page_one = await temp_db.get_platform_message_history(
        "webchat",
        "session-1",
        page=1,
        page_size=1,
    )
    page_two = await temp_db.get_platform_message_history(
        "webchat",
        "session-1",
        page=2,
        page_size=1,
    )

    assert [row.id for row in page_one] == [second.id]
    assert [row.id for row in page_two] == [first.id]


@pytest.mark.asyncio
async def test_get_preferences_combines_scope_and_key_filters_and_returns_empty_for_miss(
    temp_db: SQLiteDatabase,
):
    await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "sel_conv_id",
        {"val": "conv-a"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "session-a",
        "theme",
        {"val": "dark"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "session-b",
        "sel_conv_id",
        {"val": "conv-b"},
    )

    scoped_key = await temp_db.get_preferences(
        "umo",
        scope_id="session-a",
        key="sel_conv_id",
    )
    missing = await temp_db.get_preferences(
        "umo",
        scope_id="session-c",
        key="sel_conv_id",
    )

    assert [(item.scope_id, item.key) for item in scoped_key] == [
        ("session-a", "sel_conv_id")
    ]
    assert missing == []


@pytest.mark.asyncio
async def test_get_attachments_returns_empty_for_empty_input(temp_db: SQLiteDatabase):
    assert await temp_db.get_attachments([]) == []


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


@pytest.mark.asyncio
async def test_get_webchat_threads_by_parent_session_without_creator_orders_by_created_at(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    first = await temp_db.create_webchat_thread(
        creator="alice",
        parent_session_id="session-1",
        parent_message_id=10,
        base_checkpoint_id="ck-1",
        selected_text="first",
    )
    second = await temp_db.create_webchat_thread(
        creator="bob",
        parent_session_id="session-1",
        parent_message_id=11,
        base_checkpoint_id="ck-2",
        selected_text="second",
    )

    async with temp_db.get_db() as session:
        async with session.begin():
            await session.execute(
                update(WebChatThread)
                .where(col(WebChatThread.thread_id) == second.thread_id)
                .values(created_at=now - timedelta(minutes=2))
            )
            await session.execute(
                update(WebChatThread)
                .where(col(WebChatThread.thread_id) == first.thread_id)
                .values(created_at=now - timedelta(minutes=1))
            )

    threads = await temp_db.get_webchat_threads_by_parent_session("session-1")

    assert [thread.thread_id for thread in threads] == [
        second.thread_id,
        first.thread_id,
    ]


@pytest.mark.asyncio
async def test_close_joins_aiosqlite_worker_threads(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "close-workers.db"))
    await db.initialize()
    async with db.get_db() as session:
        await session.execute(text("SELECT 1"))

    workers = [
        thread for thread in threading.enumerate() if is_aiosqlite_worker_thread(thread)
    ]
    assert workers
    await db.close()
    assert not any(thread.is_alive() for thread in workers)
