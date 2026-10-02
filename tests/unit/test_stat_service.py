import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from sqlmodel import select

import astrbot.dashboard.services.stat_service as stat_service
from astrbot.core.computer.process_sandbox import SandboxRunResult, SandboxTimeoutError
from astrbot.core.db.po import ConversationV2, ProviderStat
from astrbot.dashboard.services.stat_service import StatService


def _make_service(db) -> StatService:
    """Build a StatService with a real DB and a mocked core lifecycle."""
    core_lifecycle = MagicMock()
    core_lifecycle.star_context.get_all_stars.return_value = []
    core_lifecycle.platform_manager.get_insts.return_value = []
    core_lifecycle.start_time = int(time.time()) - 100
    return StatService(db_helper=db, core_lifecycle=core_lifecycle, config={})


@pytest.mark.parametrize(
    ("system", "arch", "executable", "backend", "status"),
    [
        ("Linux", "x86_64", "/usr/bin/bwrap", "bubblewrap", "detected"),
        ("Linux", "aarch64", None, "bubblewrap", "missing"),
        ("Darwin", "arm64", "/usr/bin/sandbox-exec", "seatbelt", "detected"),
        ("Darwin", "x86_64", None, "seatbelt", "missing"),
        ("Darwin", "arm64", "/opt/bin/sandbox-exec", "seatbelt", "missing"),
        ("Windows", "AMD64", None, None, "unsupported"),
        ("Windows", "ARM64", None, None, "unsupported"),
        ("FreeBSD", "", None, None, "unsupported"),
    ],
)
def test_runtime_detects_platform_dependencies(
    monkeypatch, tmp_path, system, arch, executable, backend, status
):
    """Only report a detected sandbox after its launch probe succeeds."""
    monkeypatch.setattr(
        stat_service,
        "platform",
        SimpleNamespace(system=lambda: system, machine=lambda: arch),
    )
    which = Mock(return_value=executable)
    monkeypatch.setattr(stat_service, "shutil", SimpleNamespace(which=which))
    sandbox = Mock()
    sandbox.run.return_value = SandboxRunResult(returncode=0)
    factory = Mock(return_value=sandbox)
    monkeypatch.setattr(stat_service, "create_process_sandbox", factory)
    monkeypatch.setattr(stat_service, "get_astrbot_temp_path", lambda: str(tmp_path))

    service = _make_service(MagicMock())

    assert service.runtime == {
        "os": system.lower(),
        "arch": arch,
        "sandbox": {"backend": backend, "status": status},
    }
    if system == "Linux":
        which.assert_called_once_with("bwrap")
    elif system == "Darwin":
        which.assert_called_once_with("sandbox-exec", path="/usr/bin")
    else:
        which.assert_not_called()
    if status == "detected":
        factory.assert_called_once_with()
        sandbox.run.assert_called_once()
        args, kwargs = sandbox.run.call_args
        assert args[0] == ["/bin/sh", "-c", ":"]
        assert args[1].filesystem_scope == "workspace"
        assert args[1].allow_network is False
        assert not args[1].workspace.exists()
        assert kwargs["timeout"] == 5
    else:
        factory.assert_not_called()


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
@pytest.mark.parametrize(
    ("outcome", "error"),
    [
        (
            SandboxRunResult(
                returncode=1, stderr=b"bwrap: setting up uid map: Permission denied\n"
            ),
            "bwrap: setting up uid map: Permission denied",
        ),
        (
            SandboxRunResult(
                returncode=1,
                stderr=b"bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted\n",
            ),
            "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted",
        ),
        (SandboxRunResult(returncode=2), "Sandbox probe exited with code 2."),
        (PermissionError("Operation not permitted"), "Operation not permitted"),
        (SandboxTimeoutError("Sandbox probe timed out."), "Sandbox probe timed out."),
        (RuntimeError("Sandbox launch failed."), "Sandbox launch failed."),
    ],
)
def test_runtime_reports_sandbox_startup_failure(
    monkeypatch, tmp_path, system, outcome, error
):
    """Distinguish installed but unusable sandboxes without preventing startup."""
    monkeypatch.setattr(stat_service.platform, "system", lambda: system)
    monkeypatch.setattr(
        stat_service,
        "shutil",
        SimpleNamespace(which=lambda name, **kwargs: f"/usr/bin/{name}"),
    )
    sandbox = Mock()
    if isinstance(outcome, Exception):
        sandbox.run.side_effect = outcome
    else:
        sandbox.run.return_value = outcome
    monkeypatch.setattr(stat_service, "create_process_sandbox", lambda: sandbox)
    monkeypatch.setattr(stat_service, "get_astrbot_temp_path", lambda: str(tmp_path))

    service = _make_service(MagicMock())

    assert service.runtime["sandbox"] == {
        "backend": "bubblewrap" if system == "Linux" else "seatbelt",
        "status": "unavailable",
        "error": error,
    }
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_get_stat_aggregates_platform_stats(temp_db):
    """Seeded rows must aggregate into windowed platform sums and a global total."""
    now = datetime.now()
    seed = [
        ("aiocqhttp", 3, now - timedelta(hours=1)),
        ("aiocqhttp", 5, now - timedelta(hours=1, minutes=30)),
        ("qqofficial", 2, now - timedelta(hours=2)),
        ("webchat", 7, now - timedelta(minutes=10)),
        # Outside the 24h window: counted in the total but not in window stats.
        ("aiocqhttp", 4, now - timedelta(hours=26)),
    ]
    for platform_id, count, ts in seed:
        await temp_db.insert_platform_stats(platform_id, platform_id, count, ts)

    result = await _make_service(temp_db).get_stat(86400)

    # Global total counts every row, including the one outside the window.
    assert result["message_count"] == 21

    # Windowed per-platform sums, serialized with the legacy response keys.
    platform = {entry["name"]: entry["count"] for entry in result["platform"]}
    assert platform == {"aiocqhttp": 8, "qqofficial": 2, "webchat": 7}
    for entry in result["platform"]:
        assert set(entry) == {"name", "count", "timestamp"}

    # Hourly buckets cover [now - offset, now) in ascending order.
    series = result["message_time_series"]
    assert len(series) == 24
    bucket_ends = [bucket_end for bucket_end, _ in series]
    assert bucket_ends == sorted(bucket_ends)
    assert all(count >= 0 for _, count in series)
    # Rows within the current partial hour are not bucketed yet, so the
    # series sum never exceeds the windowed total of 17.
    assert sum(count for _, count in series) <= 17

    assert set(result) == {
        "platform",
        "message_count",
        "platform_count",
        "plugin_count",
        "plugins",
        "message_time_series",
        "running",
        "memory",
        "cpu_percent",
        "thread_count",
        "start_time",
    }


@pytest.mark.asyncio
async def test_get_stat_empty_window(temp_db):
    """A window with no rows yields empty platform stats but keeps the total."""
    old_ts = datetime.now() - timedelta(hours=2)
    await temp_db.insert_platform_stats("aiocqhttp", "aiocqhttp", 4, old_ts)

    result = await _make_service(temp_db).get_stat(1)

    assert result["platform"] == []
    assert result["message_count"] == 4
    assert all(count == 0 for _, count in result["message_time_series"])


@pytest.mark.asyncio
async def test_provider_token_stats_include_detached_provider_calls(temp_db):
    for agent_type, provider_id, status, output in (
        ("internal", "agent", "completed", 3),
        ("provider", "sdk", "completed", 5),
        ("internal", "aborted", "aborted", 7),
        ("third_party", "excluded", "completed", 100),
    ):
        await temp_db.insert_provider_stat(
            umo=f"test:{provider_id}",
            provider_id=provider_id,
            provider_model=f"{provider_id}-model",
            status=status,
            stats={
                "token_usage": {"output": output},
                "start_time": 1.0,
                "end_time": 2.0,
            },
            agent_type=agent_type,
        )

    service = _make_service(temp_db)
    stats = await service.get_provider_token_stats(1)

    assert stats["range_total_calls"] == 3
    assert stats["range_total_tokens"] == 15
    assert stats["range_success_rate"] == pytest.approx(2 / 3)


@pytest.mark.asyncio
async def test_provider_token_ranking_includes_umo_display_names(temp_db):
    """UMO token rankings should prefer aliases and fall back to raw identifiers."""
    aliased_umo = "qq:GroupMessage:group-1"
    raw_umo = "webchat:FriendMessage:session-2"
    await temp_db.insert_provider_stat(
        umo=aliased_umo,
        provider_id="provider-1",
        stats={"token_usage": {"input_other": 3, "input_cached": 4, "output": 5}},
    )
    await temp_db.insert_provider_stat(
        umo=raw_umo,
        provider_id="provider-1",
        stats={"token_usage": {"input_other": 1, "input_cached": 1, "output": 1}},
    )
    await temp_db.upsert_umo_alias(
        umo=aliased_umo,
        creator_sender_id="creator-1",
        auto_name="研发群",
        user_alias="产品讨论群",
    )

    service = _make_service(temp_db)
    service.config = {
        "platform": [{"id": "qq", "type": "qq_official"}],
    }
    result = await service.get_provider_token_stats(1)

    assert result["range_by_umo"] == [
        {
            "umo": aliased_umo,
            "display_name": "产品讨论群",
            "platform_type": "qq_official",
            "tokens": 12,
        },
        {
            "umo": raw_umo,
            "display_name": raw_umo,
            "platform_type": "webchat",
            "tokens": 3,
        },
    ]


@pytest.mark.asyncio
async def test_provider_token_stats_include_internal_and_provider_records(temp_db):
    await temp_db.insert_provider_stat(
        umo="platform:internal",
        provider_id="standard",
        provider_model="standard-model",
        status="completed",
        stats={
            "token_usage": {
                "input_other": 3,
                "input_cached": 1,
                "output": 4,
            },
            "start_time": 1.0,
            "end_time": 2.0,
            "time_to_first_token": 0.1,
        },
        agent_type="internal",
    )
    await temp_db.insert_provider_stat(
        umo="provider:oauth:text",
        provider_id="oauth",
        provider_model="oauth-model",
        status="error",
        stats={
            "token_usage": {
                "input_other": 5,
                "input_cached": 2,
                "output": 6,
            },
            "start_time": 3.0,
            "end_time": 4.0,
            "time_to_first_token": 0.0,
        },
        agent_type="provider",
    )
    await temp_db.insert_provider_stat(
        umo="third-party",
        provider_id="excluded",
        provider_model="excluded-model",
        status="completed",
        stats={
            "token_usage": {
                "input_other": 100,
                "input_cached": 0,
                "output": 0,
            },
            "start_time": 5.0,
            "end_time": 6.0,
            "time_to_first_token": 0.0,
        },
        agent_type="third_party",
    )
    await temp_db.insert_provider_stat(
        umo="provider:oauth:test",
        provider_id="oauth",
        provider_model="oauth-model",
        status="completed",
        stats={
            "token_usage": {
                "input_other": 1,
                "input_cached": 0,
                "output": 2,
            },
            "start_time": 7.0,
            "end_time": 8.0,
            "time_to_first_token": 0.0,
        },
        agent_type="test",
    )

    service = StatService(temp_db, SimpleNamespace(), {})
    stats = await service.get_provider_token_stats(1)

    assert stats["range_total_calls"] == 4
    assert stats["range_total_tokens"] == 124
    assert stats["range_success_rate"] == pytest.approx(3 / 4)
    assert stats["range_call_counts"] == {
        "agent": 1,
        "provider": 1,
        "test": 1,
        "other": 1,
    }
    assert stats["range_token_totals"] == {
        "agent": 8,
        "provider": 13,
        "test": 3,
        "other": 100,
    }
    assert stats["today_total_calls"] == 4
    assert stats["today_total_tokens"] == 124
    assert stats["range_by_provider"] == [
        {"provider_id": "excluded", "tokens": 100},
        {"provider_id": "oauth", "tokens": 16},
        {"provider_id": "standard", "tokens": 8},
    ]
    assert stats["today_by_model"] == [
        {"provider_model": "excluded-model", "tokens": 100},
        {"provider_model": "oauth-model", "tokens": 16},
        {"provider_model": "standard-model", "tokens": 8},
    ]


@pytest.mark.asyncio
async def test_aborted_provider_call_is_not_counted_as_success(temp_db):
    await temp_db.insert_provider_stat(
        umo="platform:aborted",
        provider_id="standard",
        status="aborted",
        stats={"token_usage": {"output": 1}},
        agent_type="internal",
    )

    service = StatService(temp_db, SimpleNamespace(), {})
    stats = await service.get_provider_token_stats(1)

    assert stats["range_total_calls"] == 1
    assert stats["range_success_rate"] == 0


@pytest.mark.asyncio
async def test_provider_usage_breakdowns_keep_dimensions_and_missing_usage_separate(
    temp_db,
):
    session_umo = "qq:GroupMessage:group-1"
    for provider_id, usage, status, source_id, plugin_id, kind in (
        (
            "oauth-luna",
            {"input_other": 8, "input_cached": 4, "output": 6},
            "reported",
            "openai_oauth",
            "",
            "text",
        ),
        (
            "oauth-luna",
            {"input_other": 0, "input_cached": 0, "output": 0},
            "reported",
            "openai_oauth",
            "plugin-one",
            "text",
        ),
        ("oauth-sol", {}, "missing", "openai_oauth", "plugin-one", "image"),
    ):
        await temp_db.insert_provider_stat(
            umo=session_umo,
            provider_id=provider_id,
            provider_model=provider_id,
            stats={"token_usage": usage},
        )
        async with temp_db.get_db() as db:
            record = (
                (
                    await db.execute(
                        select(ProviderStat).order_by(ProviderStat.id.desc())
                    )
                )
                .scalars()
                .first()
            )
            record.stat_version = 1
            record.session_umo = session_umo
            record.source_id = source_id
            record.plugin_id = plugin_id
            record.request_kind = kind
            record.usage_status = status
            await db.commit()

    stats = await _make_service(temp_db).get_provider_token_stats(1)

    assert stats["range_total_tokens"] == 18
    assert stats["range_usage"]["reported_tokens"] == 18
    assert stats["range_usage"]["input_other"] == 8
    assert stats["range_usage"]["input_cached"] == 4
    assert stats["range_usage"]["output"] == 6
    assert stats["range_usage"]["reported_calls"] == 2
    assert stats["range_usage"]["missing_calls"] == 1
    assert stats["range_usage"]["coverage"] == pytest.approx(2 / 3)
    for entries in stats["range_breakdowns"].values():
        assert sum(entry["tokens"] for entry in entries) == 18
        assert sum(entry["calls"] for entry in entries) == 3
    assert stats["range_breakdowns"]["session"][0]["key"] == session_umo
    assert stats["range_breakdowns"]["source"][0]["key"] == "openai_oauth"
    assert {item["key"] for item in stats["range_breakdowns"]["plugin"]} == {
        None,
        "plugin-one",
    }


@pytest.mark.asyncio
async def test_new_provider_rows_classify_calls_by_origin_and_kind(temp_db):
    for origin_type, request_kind, tokens in (
        ("chat", "text", 2),
        ("background", "test", 3),
        ("plugin", "text", 5),
    ):
        await temp_db.insert_provider_stat(
            umo="qq:GroupMessage:group-1",
            provider_id="oauth",
            agent_type="provider",
            stats={"token_usage": {"output": tokens}},
        )
        async with temp_db.get_db() as db:
            record = (
                (
                    await db.execute(
                        select(ProviderStat).order_by(ProviderStat.id.desc())
                    )
                )
                .scalars()
                .first()
            )
            record.stat_version = 1
            record.origin_type = origin_type
            record.request_kind = request_kind
            record.usage_status = "reported"
            await db.commit()

    stats = await _make_service(temp_db).get_provider_token_stats(1)
    assert stats["range_call_counts"] == {
        "agent": 1,
        "test": 1,
        "provider": 1,
        "other": 0,
    }
    assert stats["range_token_totals"] == {
        "agent": 2,
        "test": 3,
        "provider": 5,
        "other": 0,
    }
    assert stats["today_call_counts"] == stats["range_call_counts"]


@pytest.mark.asyncio
async def test_legacy_pseudo_session_is_unattributed_but_historical_tokens_remain(
    temp_db,
):
    real_umo = "qq:GroupMessage:group-1"
    await temp_db.insert_provider_stat(
        umo=real_umo,
        provider_id="oauth",
        stats={"token_usage": {"input_other": 7}},
    )
    await temp_db.insert_provider_stat(
        umo="provider:oauth:sdk",
        provider_id="oauth",
        stats={"token_usage": {"input_other": 13}},
    )
    async with temp_db.get_db() as db:
        db.add(
            ConversationV2(
                platform_id="qq",
                user_id=real_umo,
                content=[],
            )
        )
        db.add(
            ConversationV2(
                platform_id="provider",
                user_id="provider:oauth:sdk",
                content=[],
            )
        )
        await db.commit()

    stats = await _make_service(temp_db).get_provider_token_stats(1)

    assert stats["range_total_tokens"] == 20
    assert stats["range_usage"]["legacy_tokens"] == 20
    assert stats["range_usage"]["legacy_calls"] == 2
    sessions = {entry["key"]: entry for entry in stats["range_breakdowns"]["session"]}
    assert sessions[real_umo]["tokens"] == 7
    assert sessions[real_umo]["can_open_conversation"] is True
    assert sessions[None]["tokens"] == 13
    assert sessions[None]["can_open_conversation"] is False
    assert len(stats["range_breakdowns"]["source"]) == 1
    assert stats["range_breakdowns"]["source"][0]["key"] is None
    assert stats["range_breakdowns"]["source"][0]["tokens"] == 20
    assert stats["range_breakdowns"]["source"][0]["legacy_calls"] == 2


@pytest.mark.asyncio
async def test_provider_range_uses_exact_24_hour_cutoff(temp_db, monkeypatch):
    fixed_now = datetime(2026, 9, 28, 12, 30, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now.astimezone(tz) if tz else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(stat_service, "datetime", FrozenDateTime)
    for minutes_before_cutoff, tokens in ((1, 100), (-1, 2)):
        await temp_db.insert_provider_stat(
            umo="qq:GroupMessage:group-1",
            provider_id="oauth",
            stats={"token_usage": {"input_other": tokens}},
        )
        async with temp_db.get_db() as db:
            record = (
                (
                    await db.execute(
                        select(ProviderStat).order_by(ProviderStat.id.desc())
                    )
                )
                .scalars()
                .first()
            )
            record.created_at = fixed_now - timedelta(
                days=1, minutes=minutes_before_cutoff
            )
            await db.commit()

    stats = await _make_service(temp_db).get_provider_token_stats(1)
    assert stats["range_total_tokens"] == 2
    assert stats["range_total_calls"] == 1
