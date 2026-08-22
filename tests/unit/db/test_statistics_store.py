from datetime import datetime, timedelta

import pytest

from astrbot.core.db.po import ProviderStat
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
