from types import SimpleNamespace

import pytest
from sqlmodel import select

from astrbot.core.agent.response import AgentStats
from astrbot.core.db.po import ProviderStat
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.provider.entities import ProviderRequest, TokenUsage


@pytest.mark.asyncio
async def test_record_internal_agent_stats_persists_provider_stat(
    temp_db,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(internal, "db_helper", temp_db)

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-42")
    req = ProviderRequest(
        conversation=SimpleNamespace(cid="conv-123"),
    )
    stats = AgentStats(
        token_usage=TokenUsage(input_other=11, input_cached=3, output=7),
        start_time=100.0,
        end_time=108.5,
        time_to_first_token=0.6,
    )
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1", type="openai"),
        get_model=lambda: "gpt-4.1",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=stats,
        was_aborted=lambda: False,
    )
    final_resp = SimpleNamespace(role="assistant")

    await internal._record_internal_agent_stats(
        event,
        req,
        agent_runner,
        final_resp,
    )

    async with temp_db.get_db() as session:
        result = await session.execute(select(ProviderStat))
        records = result.scalars().all()

    assert len(records) == 1
    record = records[0]
    assert record.agent_type == "internal"
    assert record.status == "completed"
    assert record.umo == "webchat:FriendMessage:session-42"
    assert record.conversation_id == "conv-123"
    assert record.provider_id == "provider-1"
    assert record.provider_model == "gpt-4.1"
    assert record.token_input_other == 11
    assert record.token_input_cached == 3
    assert record.token_output == 7
    assert record.start_time == 100.0
    assert record.end_time == 108.5
    assert record.time_to_first_token == 0.6


@pytest.mark.asyncio
async def test_managed_stats_keep_caption_and_opaque_text_usage(temp_db, monkeypatch):
    from astrbot.core.image_request_budget import ImageRequestBudget

    monkeypatch.setattr(internal, "db_helper", temp_db)
    budget = ImageRequestBudget()
    with budget.scope(
        purpose="caption", provider_id="vision", model="visual", image_count=1
    ) as scope:
        budget.on_attempt(scope)
    turn = SimpleNamespace(
        configured=True,
        budget=budget,
        unmetered_stats=[
            {
                "purpose": "main",
                "provider_id": "custom",
                "model": "text",
                "attempts": 1,
                "attempts_kind": "logical",
                "image_submissions": 0,
                "encoded_bytes": 0,
                "unknown_calls": 0,
                "usage_known": True,
                "token_usage": {"input_other": 13, "input_cached": 0, "output": 5},
            }
        ],
    )
    provider = SimpleNamespace(
        provider_config={"id": "custom"}, get_model=lambda: "text"
    )
    runner = SimpleNamespace(
        provider=provider, stats=AgentStats(), was_aborted=lambda: False
    )
    await internal._record_internal_agent_stats(
        SimpleNamespace(unified_msg_origin="test"),
        ProviderRequest(image_context=turn),
        runner,
        SimpleNamespace(role="assistant"),
    )
    async with temp_db.get_db() as session:
        records = (await session.execute(select(ProviderStat))).scalars().all()
    assert len(records) == 2
    by_provider = {row.provider_id: row for row in records}
    assert by_provider["vision"].request_details["unknown_calls"] == 1
    assert by_provider["custom"].token_input_other == 13
    assert by_provider["custom"].token_output == 5
    assert by_provider["custom"].request_details["attempts_kind"] == "logical"
