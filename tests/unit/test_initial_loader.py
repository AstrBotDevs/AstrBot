"""Tests for InitialLoader."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.initial_loader import InitialLoader


@pytest.mark.asyncio
async def test_initial_loader_start_awaits_initialize_core_and_schedules_runtime_bootstrap():
    """Test InitialLoader.start splits core init from background runtime bootstrap."""
    loader = InitialLoader(MagicMock(), MagicMock())
    call_order: list[str] = []
    real_create_task = asyncio.create_task
    created_tasks: list[asyncio.Task] = []

    lifecycle = MagicMock()
    lifecycle.dashboard_shutdown_event = asyncio.Event()
    lifecycle.runtime_bootstrap_task = None

    async def initialize_core() -> None:
        call_order.append("initialize_core")

    async def bootstrap_runtime() -> None:
        call_order.append("bootstrap_runtime")

    async def start_core() -> None:
        call_order.append("core_start")

    async def run_dashboard() -> None:
        call_order.append("dashboard_run")

    lifecycle.initialize = AsyncMock(
        side_effect=AssertionError("initialize should not be used")
    )
    lifecycle.initialize_core = AsyncMock(side_effect=initialize_core)
    lifecycle.bootstrap_runtime = AsyncMock(side_effect=bootstrap_runtime)
    lifecycle.start = AsyncMock(side_effect=start_core)

    dashboard = MagicMock()
    dashboard.run = AsyncMock(side_effect=run_dashboard)

    def dashboard_factory(*args, **kwargs):
        del args, kwargs
        call_order.append("dashboard_init")
        return dashboard

    def create_task(coro, *args, **kwargs):
        call_order.append("create_task")
        task = real_create_task(coro, *args, **kwargs)
        created_tasks.append(task)
        return task

    with (
        patch(
            "astrbot.core.initial_loader.AstrBotCoreLifecycle", return_value=lifecycle
        ),
        patch(
            "astrbot.core.initial_loader.AstrBotDashboard",
            side_effect=dashboard_factory,
        ),
        patch(
            "astrbot.core.initial_loader.asyncio.create_task", side_effect=create_task
        ),
    ):
        await loader.start()

    lifecycle.initialize.assert_not_called()
    lifecycle.initialize_core.assert_awaited_once()
    lifecycle.bootstrap_runtime.assert_awaited_once()
    lifecycle.start.assert_awaited_once()
    dashboard.run.assert_awaited_once()
    assert call_order[:3] == ["initialize_core", "create_task", "dashboard_init"]
    assert len(created_tasks) == 1
    assert lifecycle.runtime_bootstrap_task is created_tasks[0]


@pytest.mark.asyncio
async def test_initial_loader_start_returns_without_partial_start_when_initialize_core_fails():
    """Test InitialLoader.start aborts cleanly if initialize_core fails."""
    loader = InitialLoader(MagicMock(), MagicMock())

    lifecycle = MagicMock()
    lifecycle.runtime_bootstrap_task = None
    expected_error = RuntimeError("core init failed")
    lifecycle.initialize_core = AsyncMock(side_effect=expected_error)
    lifecycle.bootstrap_runtime = AsyncMock()
    lifecycle.start = AsyncMock()

    with (
        patch(
            "astrbot.core.initial_loader.AstrBotCoreLifecycle", return_value=lifecycle
        ),
        patch("astrbot.core.initial_loader.AstrBotDashboard") as dashboard_cls,
        patch("astrbot.core.initial_loader.asyncio.create_task") as create_task,
    ):
        await loader.start()

    lifecycle.initialize_core.assert_awaited_once()
    dashboard_cls.assert_not_called()
    create_task.assert_not_called()
    lifecycle.bootstrap_runtime.assert_not_called()
    lifecycle.start.assert_not_called()
    assert lifecycle.runtime_bootstrap_task is None
