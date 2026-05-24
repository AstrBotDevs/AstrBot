"""Shared fixtures for dashboard API tests."""

import asyncio

import pytest
import pytest_asyncio
from quart import Quart

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.server import AstrBotDashboard

TEST_DASHBOARD_PASSWORD = "AstrBotTest123"


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    """Creates and initializes a core lifecycle instance with a temporary database."""
    # Set a fully upgraded test dashboard password so auth does not depend on
    # the production first-run random password path.
    from astrbot.core import astrbot_config as global_cfg
    from astrbot.core.utils.auth_password import (
        hash_dashboard_password,
        hash_legacy_dashboard_password,
    )

    global_cfg["dashboard"]["username"] = "astrbot"
    global_cfg["dashboard"]["pbkdf2_password"] = hash_dashboard_password(
        TEST_DASHBOARD_PASSWORD,
    )
    global_cfg["dashboard"]["password"] = hash_legacy_dashboard_password(
        TEST_DASHBOARD_PASSWORD,
    )
    global_cfg["dashboard"]["password_storage_upgraded"] = True
    global_cfg["dashboard"]["password_change_required"] = False

    tmp_root = tmp_path_factory.mktemp("astrbot_root")
    tmp_db_path = tmp_root / "test_data_v3.db"
    db = SQLiteDatabase(str(tmp_db_path))
    log_broker = LogBroker()
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    await core_lifecycle.initialize()
    # Mark runtime as ready so the dashboard stops returning 503.
    # In production ``start()`` triggers this; in tests we skip the full startup.
    core_lifecycle.runtime_ready = True
    core_lifecycle.runtime_ready_event.set()
    try:
        yield core_lifecycle
    finally:
        try:
            _stop_res = core_lifecycle.stop()
            if asyncio.iscoroutine(_stop_res):
                await _stop_res
        except Exception:
            pass


@pytest.fixture(scope="module")
def app(core_lifecycle_td: AstrBotCoreLifecycle):
    """Creates a Quart app instance for testing."""
    shutdown_event = asyncio.Event()
    server = AstrBotDashboard(core_lifecycle_td, core_lifecycle_td.db, shutdown_event)
    return server.app


def _resolve_dashboard_password(core_lifecycle_td: AstrBotCoreLifecycle) -> str:
    """Return the raw password (not hash) for the test config."""
    return TEST_DASHBOARD_PASSWORD


@pytest_asyncio.fixture(scope="module")
async def authenticated_header(app: Quart, core_lifecycle_td: AstrBotCoreLifecycle):
    """Handles login and returns an authenticated header."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    data = await response.get_json()
    assert data["status"] == "ok", str(data)
    token = data["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
