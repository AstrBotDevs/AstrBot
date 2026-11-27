"""Tests for SQLiteDatabase.get_platform_stats aggregation and return types."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from astrbot.core.db.po import PlatformStat
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_get_platform_stats_aggregates_counts_and_returns_models(
    tmp_path: Path,
) -> None:
    """Verify get_platform_stats returns aggregated PlatformStat instances."""
    db = SQLiteDatabase(str(tmp_path / "stats.db"))
    await db.initialize()
    try:
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        # Empty table returns an empty list
        assert await db.get_platform_stats(offset_sec=86400) == []

        # Out-of-window record should be excluded
        await db.insert_platform_stats(
            "bot_a",
            "aiocqhttp",
            count=100,
            timestamp=now - timedelta(hours=48),
        )
        # Multiple in-window buckets for bot_a
        await db.insert_platform_stats(
            "bot_a",
            "aiocqhttp",
            count=5,
            timestamp=now - timedelta(hours=3),
        )
        await db.insert_platform_stats(
            "bot_a",
            "aiocqhttp",
            count=7,
            timestamp=now - timedelta(hours=1),
        )
        # Older latest timestamp for bot_b
        await db.insert_platform_stats(
            "bot_b",
            "telegram",
            count=4,
            timestamp=now - timedelta(hours=2),
        )

        stats = await db.get_platform_stats(offset_sec=86400)
        assert len(stats) == 2
        assert all(isinstance(item, PlatformStat) for item in stats)

        # Ordered by latest timestamp descending: bot_a (-1h) before bot_b (-2h)
        assert stats[0].platform_id == "bot_a"
        assert stats[0].platform_type == "aiocqhttp"
        assert stats[0].count == 12
        assert stats[0].timestamp == now - timedelta(hours=1)

        assert stats[1].platform_id == "bot_b"
        assert stats[1].platform_type == "telegram"
        assert stats[1].count == 4
        assert stats[1].timestamp == now - timedelta(hours=2)
    finally:
        await db.engine.dispose()
