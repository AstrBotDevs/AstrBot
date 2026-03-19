from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.builtin_commands.commands.context_compaction import (
    ContextCompactionCommands,
)
from astrbot.core.context_compaction_scheduler import PeriodicContextCompactionScheduler


class DummyConfigManager:
    def __init__(self, default_conf: dict):
        self.default_conf = default_conf


def _build_scheduler() -> PeriodicContextCompactionScheduler:
    cfg_mgr = DummyConfigManager(
        {
            "provider_settings": {
                "periodic_context_compaction": {
                    "enabled": True,
                    "interval_minutes": 3,
                    "max_conversations_per_run": 2,
                    "max_scan_per_run": 10,
                    "target_tokens": 1024,
                    "trigger_tokens": 2048,
                    "max_rounds": 2,
                }
            }
        }
    )
    return PeriodicContextCompactionScheduler(
        config_manager=cfg_mgr,
        conversation_manager=SimpleNamespace(),
        provider_manager=SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_status_when_scheduler_unavailable() -> None:
    command = ContextCompactionCommands(context=SimpleNamespace())
    event = SimpleNamespace(send=AsyncMock())

    await command.status(event)

    event.send.assert_awaited_once()
    chain = event.send.await_args.args[0]
    assert "不可用" in chain.get_plain_text(with_other_comps_mark=True)


@pytest.mark.asyncio
async def test_status_with_runtime_report() -> None:
    scheduler = _build_scheduler()
    scheduler._last_report = {
        "reason": "manual_command",
        "scanned": 8,
        "compacted": 2,
        "skipped": 6,
        "failed": 0,
        "elapsed_sec": 1.2,
    }
    scheduler._last_started_at = "2026-03-19T12:00:00+00:00"
    scheduler._last_finished_at = "2026-03-19T12:00:01+00:00"

    command = ContextCompactionCommands(
        context=SimpleNamespace(context_compaction_scheduler=scheduler)
    )
    event = SimpleNamespace(send=AsyncMock())

    await command.status(event)

    event.send.assert_awaited_once()
    chain = event.send.await_args.args[0]
    text = chain.get_plain_text(with_other_comps_mark=True)
    assert "定时上下文压缩状态" in text
    assert "最近任务[manual_command]" in text
    assert "compacted=2" in text


@pytest.mark.asyncio
async def test_run_with_invalid_limit() -> None:
    scheduler = _build_scheduler()
    scheduler.run_once = AsyncMock()

    command = ContextCompactionCommands(
        context=SimpleNamespace(context_compaction_scheduler=scheduler)
    )
    event = SimpleNamespace(send=AsyncMock())

    await command.run(event, 0)

    scheduler.run_once.assert_not_awaited()
    chain = event.send.await_args.args[0]
    assert "limit 必须 >= 1" in chain.get_plain_text(with_other_comps_mark=True)


@pytest.mark.asyncio
async def test_run_triggers_scheduler_once() -> None:
    scheduler = _build_scheduler()
    scheduler.run_once = AsyncMock(
        return_value={
            "scanned": 12,
            "compacted": 3,
            "skipped": 8,
            "failed": 1,
            "elapsed_sec": 2.5,
        }
    )

    command = ContextCompactionCommands(
        context=SimpleNamespace(context_compaction_scheduler=scheduler)
    )
    event = SimpleNamespace(send=AsyncMock())

    await command.run(event, 5)

    scheduler.run_once.assert_awaited_once_with(
        reason="manual_command",
        max_conversations_override=5,
    )
    chain = event.send.await_args.args[0]
    text = chain.get_plain_text(with_other_comps_mark=True)
    assert "手动触发完成" in text
    assert "compacted=3" in text
