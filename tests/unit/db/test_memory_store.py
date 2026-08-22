import pytest

from astrbot.core.db.po import MemoryFact
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_memory_sqlite_interfaces(temp_db: SQLiteDatabase):
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
