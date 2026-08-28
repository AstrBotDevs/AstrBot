import time
from datetime import datetime, timedelta
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
