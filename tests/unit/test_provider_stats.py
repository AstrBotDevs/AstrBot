from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError
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
async def test_record_internal_agent_stats_retries_transient_database_lock(
    monkeypatch: pytest.MonkeyPatch,
):
    attempts = 0

    class LockedOnceDb:
        async def insert_provider_stat(self, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationalError(
                    "insert into provider_stats",
                    {},
                    Exception("database is locked"),
                )
            return SimpleNamespace(**kwargs)

    monkeypatch.setattr(internal, "db_helper", LockedOnceDb())

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(internal.asyncio, "sleep", no_sleep)

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-42")
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-123"))
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1", type="openai"),
        get_model=lambda: "gpt-4.1",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=AgentStats(),
        was_aborted=lambda: False,
    )

    await internal._record_internal_agent_stats(
        event,
        req,
        agent_runner,
        SimpleNamespace(role="assistant"),
    )

    assert attempts == 2


@pytest.mark.asyncio
async def test_record_internal_agent_stats_retries_database_table_lock(
    monkeypatch: pytest.MonkeyPatch,
):
    attempts = 0

    class LockedOnceDb:
        async def insert_provider_stat(self, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationalError(
                    "insert into provider_stats",
                    {},
                    Exception("database table is locked"),
                )
            return SimpleNamespace(**kwargs)

    monkeypatch.setattr(internal, "db_helper", LockedOnceDb())

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(internal.asyncio, "sleep", no_sleep)

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-42")
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1", type="openai"),
        get_model=lambda: "gpt-4.1",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=AgentStats(),
        was_aborted=lambda: False,
    )

    await internal._record_internal_agent_stats(
        event,
        ProviderRequest(conversation=SimpleNamespace(cid="conv-123")),
        agent_runner,
        SimpleNamespace(role="assistant"),
    )

    assert attempts == 2


@pytest.mark.asyncio
async def test_record_internal_agent_stats_does_not_retry_other_operational_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    attempts = 0
    warnings = []

    class FailingDb:
        async def insert_provider_stat(self, **kwargs):
            nonlocal attempts
            attempts += 1
            raise OperationalError(
                "insert into provider_stats",
                {},
                Exception("no such table: provider_stats"),
            )

    monkeypatch.setattr(internal, "db_helper", FailingDb())
    monkeypatch.setattr(
        internal.logger,
        "warning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )

    event = SimpleNamespace(unified_msg_origin="webchat:FriendMessage:session-42")
    provider = SimpleNamespace(
        provider_config={"id": "provider-1"},
        meta=lambda: SimpleNamespace(id="provider-1", type="openai"),
        get_model=lambda: "gpt-4.1",
    )
    agent_runner = SimpleNamespace(
        provider=provider,
        stats=AgentStats(),
        was_aborted=lambda: False,
    )

    await internal._record_internal_agent_stats(
        event,
        ProviderRequest(conversation=SimpleNamespace(cid="conv-123")),
        agent_runner,
        SimpleNamespace(role="assistant"),
    )

    assert attempts == 1
    assert len(warnings) == 1
