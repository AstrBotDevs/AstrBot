import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_persona_runtime_sqlite_interfaces(temp_db: SQLiteDatabase):
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

    assert state.id == updated_state.id
    assert updated_state.agent_state == "wait"
    assert updated_state.extra_state == {"proactive_enabled": True}

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
