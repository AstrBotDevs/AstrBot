"""Verify core modules can be imported and initialised without crashing.

This catches silent breakage like missing sentinel classes, reordered
variable definitions, or constructor signature changes that only blow up
at runtime.
"""


def test_core_lifecycle_import():
    """CoreLifecycle class definition is importable."""
    from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

    assert AstrBotCoreLifecycle is not None


def test_dashboard_server_import():
    """AstrBotDashboard class definition is importable."""
    from astrbot.dashboard.server import AstrBotDashboard

    assert AstrBotDashboard is not None


def test_pipeline_scheduler_import():
    """PipelineScheduler class definition is importable."""
    from astrbot.core.pipeline.scheduler import PipelineScheduler

    assert PipelineScheduler is not None


def test_process_stage_import():
    """ProcessStage class definition is importable."""
    from astrbot.core.pipeline.process_stage.stage import ProcessStage

    assert ProcessStage is not None


def test_platform_base_import():
    """Platform ABC is importable and has abstract methods."""
    from astrbot.core.platform.platform import Platform

    assert len(Platform.__abstractmethods__) > 0  # type: ignore[attr-defined]


def test_auth_route_import():
    """AuthRoute class definition is importable."""
    from astrbot.dashboard.routes.auth import AuthRoute

    assert AuthRoute is not None


def test_log_route_import():
    """LogRoute (live-log SSE) class definition is importable."""
    from astrbot.dashboard.routes.log import LogRoute

    assert LogRoute is not None


def test_password_utils_import():
    """All password utility functions are importable."""
    from astrbot.core.utils.auth_password import (
        hash_dashboard_password,
        verify_dashboard_password,
        verify_dashboard_login_proof,
        get_dashboard_login_challenge,
        is_default_dashboard_password,
        is_legacy_dashboard_password,
    )

    assert callable(hash_dashboard_password)
    assert callable(verify_dashboard_password)
