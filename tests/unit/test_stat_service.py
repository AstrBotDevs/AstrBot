import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.dashboard.services.stat_service import StatService


def _make_service(db) -> StatService:
    """Build a StatService with a real DB and a mocked core lifecycle."""
    core_lifecycle = MagicMock()
    core_lifecycle.star_context.get_all_stars.return_value = []
    core_lifecycle.platform_manager.get_insts.return_value = []
    core_lifecycle.start_time = int(time.time()) - 100
    return StatService(db_helper=db, core_lifecycle=core_lifecycle, config={})


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

    service = StatService(temp_db, SimpleNamespace(), {})
    stats = await service.get_provider_token_stats(1)

    assert stats["range_total_calls"] == 3
    assert stats["range_total_tokens"] == 15
    assert stats["range_success_rate"] == pytest.approx(2 / 3)
