from __future__ import annotations

import pytest

from tests.unit.agent_sub_stage_support import *  # noqa: F403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("aborted", "final_resp", "expected_status"),
    [
        (False, LLMResponse(role="assistant", completion_text="done"), "completed"),
        (False, LLMResponse(role="err", completion_text="boom"), "error"),
        (True, LLMResponse(role="assistant", completion_text="partial"), "aborted"),
    ],
)
async def test_record_internal_agent_stats_persists_expected_status(
    monkeypatch,
    aborted,
    final_resp,
    expected_status,
):
    insert_provider_stat = AsyncMock()
    db = SimpleNamespace(insert_provider_stat=insert_provider_stat)

    event = FakeEvent()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-stats"))
    runner = FakeInternalRunner(aborted=aborted)

    await internal._record_internal_agent_stats(event, req, runner, final_resp, db)

    insert_provider_stat.assert_awaited_once_with(
        umo=event.unified_msg_origin,
        conversation_id="conv-stats",
        provider_id="provider-1",
        provider_model="fake-model",
        status=expected_status,
        stats={"steps": 1},
        agent_type="internal",
    )


@pytest.mark.asyncio
async def test_record_internal_agent_stats_falls_back_to_provider_meta_id_without_request(
    monkeypatch,
):
    insert_provider_stat = AsyncMock()
    db = SimpleNamespace(insert_provider_stat=insert_provider_stat)

    runner = FakeInternalRunner()
    runner.provider.provider_config = {}

    await internal._record_internal_agent_stats(
        FakeEvent(),
        None,
        runner,
        LLMResponse(role="assistant", completion_text="done"),
        db,
    )

    insert_provider_stat.assert_awaited_once_with(
        umo="webchat:FriendMessage:test-session",
        conversation_id=None,
        provider_id="fake-provider",
        provider_model="fake-model",
        status="completed",
        stats={"steps": 1},
        agent_type="internal",
    )


@pytest.mark.asyncio
async def test_record_internal_agent_stats_skips_when_provider_or_stats_missing(
    monkeypatch,
):
    insert_provider_stat = AsyncMock()
    db = SimpleNamespace(insert_provider_stat=insert_provider_stat)

    event = FakeEvent()
    req = ProviderRequest(conversation=SimpleNamespace(cid="conv-stats"))
    no_provider_runner = FakeInternalRunner()
    no_provider_runner.provider = None
    no_stats_runner = FakeInternalRunner()
    no_stats_runner.stats = None

    await internal._record_internal_agent_stats(
        event, req, no_provider_runner, None, db
    )
    await internal._record_internal_agent_stats(event, req, no_stats_runner, None, db)

    insert_provider_stat.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_internal_agent_stats_swallows_persistence_failures(monkeypatch):
    warning = MagicMock()
    db = SimpleNamespace(
        insert_provider_stat=AsyncMock(side_effect=RuntimeError("db write failed"))
    )
    monkeypatch.setattr(internal.logger, "warning", warning)

    await internal._record_internal_agent_stats(
        FakeEvent(),
        ProviderRequest(conversation=SimpleNamespace(cid="conv-stats")),
        FakeInternalRunner(),
        LLMResponse(role="assistant", completion_text="done"),
        db,
    )

    warning.assert_called_once()
    assert "Persist provider stats failed" in warning.call_args.args[0]
