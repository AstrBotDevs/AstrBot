"""Tests for InitialLoader."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.initial_loader import InitialLoader


@pytest.mark.asyncio
async def test_initial_loader_start_awaits_initialize_and_schedules_runtime_bootstrap():
    """Test InitialLoader.start initializes core then starts dashboard."""
    loader = InitialLoader(MagicMock(), MagicMock())
    call_order: list[str] = []
    block_event = asyncio.Event()

    lifecycle = MagicMock()
    lifecycle.dashboard_shutdown_event = asyncio.Event()
    lifecycle.stop = AsyncMock()

    async def initialize_phase() -> None:
        call_order.append("initialize")

    async def start_core() -> None:
        call_order.append("core_start")
        await block_event.wait()

    async def run_dashboard() -> None:
        call_order.append("dashboard_run")
        await block_event.wait()

    lifecycle.initialize = AsyncMock(side_effect=initialize_phase)
    lifecycle.start = AsyncMock(side_effect=start_core)

    dashboard = MagicMock()
    dashboard.run = AsyncMock(side_effect=run_dashboard)

    def dashboard_factory(*args, **kwargs):
        del args, kwargs
        call_order.append("dashboard_init")
        return dashboard

    with (
        patch(
            "astrbot.core.initial_loader.AstrBotCoreLifecycle", return_value=lifecycle
        ),
        patch(
            "astrbot.core.initial_loader.AstrBotDashboard",
            side_effect=dashboard_factory,
        ),
    ):
        task = asyncio.create_task(loader.start())
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    lifecycle.initialize.assert_awaited_once()
    lifecycle.start.assert_awaited_once()
    dashboard.run.assert_awaited_once()
    lifecycle.stop.assert_awaited_once()
    assert "initialize" in call_order
    assert "dashboard_init" in call_order


@pytest.mark.asyncio
async def test_initial_loader_start_returns_without_partial_start_when_initialize_fails():
    """Test InitialLoader.start aborts cleanly if initialize fails."""
    loader = InitialLoader(MagicMock(), MagicMock())

    lifecycle = MagicMock()
    lifecycle.runtime_bootstrap_task = None
    expected_error = RuntimeError("core init failed")
    lifecycle.initialize = AsyncMock(side_effect=expected_error)
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

    lifecycle.initialize.assert_awaited_once()
    dashboard_cls.assert_not_called()
    create_task.assert_not_called()
    lifecycle.bootstrap_runtime.assert_not_called()
    lifecycle.start.assert_not_called()
    assert lifecycle.runtime_bootstrap_task is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failing_component", "expected_order"),
    [
        ("core", ["initialize", "core_start", "dashboard_run"]),
        (
            "dashboard",
            ["initialize", "core_start", "dashboard_run"],
        ),
    ],
)
async def test_initial_loader_start_propagates_runtime_task_errors(
    failing_component: str,
    expected_order: list[str],
):
    """Test InitialLoader.start propagates runtime task errors."""
    loader = InitialLoader(MagicMock(), MagicMock())
    call_order: list[str] = []
    runtime_error = RuntimeError(f"{failing_component} failed")

    lifecycle = MagicMock()
    lifecycle.dashboard_shutdown_event = asyncio.Event()

    async def initialize_phase() -> None:
        call_order.append("initialize")

    async def start_core() -> None:
        call_order.append("core_start")
        if failing_component == "core":
            raise runtime_error

    async def run_dashboard() -> None:
        call_order.append("dashboard_run")
        if failing_component == "dashboard":
            raise runtime_error

    lifecycle.initialize = AsyncMock(side_effect=initialize_phase)
    lifecycle.start = AsyncMock(side_effect=start_core)

    dashboard = MagicMock()
    dashboard.run = AsyncMock(side_effect=run_dashboard)

    with (
        patch(
            "astrbot.core.initial_loader.AstrBotCoreLifecycle",
            return_value=lifecycle,
        ),
        patch(
            "astrbot.core.initial_loader.AstrBotDashboard",
            return_value=dashboard,
        ),
    ):
        with pytest.raises(RuntimeError, match=f"{failing_component} failed"):
            await loader.start()

    assert call_order == expected_order
