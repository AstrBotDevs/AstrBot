from types import SimpleNamespace

import pytest

from astrbot.dashboard.services.stat_service import StatService


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
