import asyncio
import copy
import io
import os
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlmodel import col, select
from werkzeug.datastructures import FileStorage

from astrbot.application import resolve_dashboard_assets
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.po import AuthStepUpCredential, DashboardAccount
from astrbot.core.desktop_runtime import DESKTOP_MANAGED_RESTART_MESSAGE
from astrbot.core.log import LogBroker
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_md5_dashboard_password,
    verify_dashboard_password,
)
from astrbot.core.utils.pip_installer import PipInstallError
from astrbot.core.utils.totp import (
    TOTP_TRUSTED_DEVICE_COOKIE_NAME,
    generate_recovery_code,
)
from astrbot.dashboard.password_state import (
    get_dashboard_password_hash,
    is_password_change_required,
    is_password_storage_upgraded,
    set_password_change_required,
    set_password_storage_upgraded,
)
from astrbot.dashboard.server import (
    AstrBotDashboard,
    _ProxyAwareHypercornLogger,
    _RateLimiterRegistry,
)
from astrbot.dashboard.services.auth_service import DASHBOARD_JWT_COOKIE_NAME
from astrbot.dashboard.services.plugin_service import PluginService
from astrbot.dashboard.services.static_file_service import StaticFileService
from tests.fixtures.helpers import (
    MockPluginBuilder,
    create_isolated_runtime_services,
    create_mock_updater_install,
    create_mock_updater_update,
)
from tests.helpers.dashboard_test_adapter import DashboardTestClient

_TEST_DASHBOARD_PASSWORD = "AstrbotTest123"


def _create_dashboard(
    runtime,
    core_control,
    db,
    shutdown_event: asyncio.Event,
    webui_dir: str | None = None,
) -> AstrBotDashboard:
    """Create a Dashboard after asynchronously persisting its JWT secret."""
    return asyncio.run(
        AstrBotDashboard.create(
            runtime,
            core_control,
            db,
            shutdown_event,
            webui_dir,
        )
    )


def _removed_md5_hint_alias_key() -> str:
    return "le" + "gacy_pwd_hint"


def _assert_cookie_samesite_strict(cookie_header: str) -> None:
    """Assert that a cookie header carries a strict SameSite attribute.

    Args:
        cookie_header: The raw Set-Cookie header value to inspect.
    """
    assert "samesite=strict" in cookie_header.lower()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def core_lifecycle_td(tmp_path_factory):
    """Creates and initializes a core lifecycle instance with a temporary database."""
    runtime_root = tmp_path_factory.mktemp("astrbot-runtime")
    tmp_db_path = runtime_root / "data" / "test_data_v3.db"
    log_broker = LogBroker()
    services = create_isolated_runtime_services(runtime_root, tmp_db_path)
    core_lifecycle = AstrBotCoreLifecycle(log_broker, services)
    await core_lifecycle.initialize()
    generated_password = getattr(
        core_lifecycle.astrbot_config,
        "_generated_dashboard_password",
        None,
    )
    dashboard_password = generated_password or _TEST_DASHBOARD_PASSWORD
    if not generated_password:
        core_lifecycle.astrbot_config["dashboard"]["pbkdf2_password"] = (
            hash_dashboard_password(dashboard_password)
        )
        core_lifecycle.astrbot_config["dashboard"]["password"] = ""
        await set_password_storage_upgraded(
            core_lifecycle.astrbot_config,
            True,
        )
        await set_password_change_required(
            core_lifecycle.astrbot_config,
            False,
        )
    object.__setattr__(
        core_lifecycle,
        "_dashboard_plain_password",
        dashboard_password,
    )
    try:
        yield core_lifecycle
    finally:
        # Stop the core lifecycle first to release background resources.
        try:
            _stop_res = core_lifecycle.stop()
            if asyncio.iscoroutine(_stop_res):
                await _stop_res
        except Exception:
            # Cleanup should continue even if lifecycle shutdown raises.
            pass


@pytest.fixture(scope="module")
def app(core_lifecycle_td: AstrBotCoreLifecycle):
    """Creates a FastAPI app instance for dashboard testing."""
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
    )
    return server.asgi_app


def _resolve_dashboard_password(core_lifecycle_td: AstrBotCoreLifecycle) -> str:
    """Return the login password for hashed and plain dashboard defaults."""
    generated_password = getattr(core_lifecycle_td, "_dashboard_plain_password", None)
    if generated_password:
        return generated_password
    password = core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"]
    if isinstance(password, str) and password.startswith("pbkdf2_sha256$"):
        return "astrbot"
    return password


async def _high_risk_headers(
    test_client: DashboardTestClient,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    *,
    action: str,
    resource_id: str,
) -> dict:
    """Issue the one-time step-up required for a system operation."""

    response = await test_client.post(
        "/api/v1/authorization/step-up",
        json={
            "action": action,
            "resource_type": "system",
            "resource_id": resource_id,
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
        headers=authenticated_header,
    )
    assert response.status_code == 200
    return {
        **authenticated_header,
        "X-AstrBot-Step-Up": (await response.get_json())["data"]["token"],
    }


async def _set_dashboard_password_change_required(
    core_lifecycle_td: AstrBotCoreLifecycle,
    required: bool,
) -> None:
    await set_password_change_required(
        core_lifecycle_td.astrbot_config,
        required,
    )


async def _set_dashboard_account_totp(
    core_lifecycle_td: AstrBotCoreLifecycle,
    secret: str,
    recovery_code_hash: str,
) -> None:
    async with core_lifecycle_td.db.get_db() as session:
        async with session.begin():
            account = (
                await session.execute(
                    select(DashboardAccount)
                    .where(col(DashboardAccount.is_active).is_(True))
                    .limit(1)
                )
            ).scalar_one()
            account.totp_enabled = True
            account.totp_secret = secret
            account.totp_recovery_code_hash = recovery_code_hash


async def _set_dashboard_account_password(
    core_lifecycle_td: AstrBotCoreLifecycle,
    username: str,
    password_hash: str,
) -> None:
    async with core_lifecycle_td.db.get_db() as session:
        async with session.begin():
            account = (
                await session.execute(
                    select(DashboardAccount)
                    .where(col(DashboardAccount.is_active).is_(True))
                    .limit(1)
                )
            ).scalar_one()
            account.username = username
            account.password_hash = password_hash


async def _restore_dashboard_password_state(
    core_lifecycle_td: AstrBotCoreLifecycle,
    dashboard_config: dict,
) -> None:
    core_lifecycle_td.astrbot_config["dashboard"] = dashboard_config
    await set_password_change_required(
        core_lifecycle_td.astrbot_config,
        False,
    )
    await set_password_storage_upgraded(
        core_lifecycle_td.astrbot_config,
        bool(dashboard_config.get("pbkdf2_password")),
    )
    async with core_lifecycle_td.db.get_db() as session:
        async with session.begin():
            account = (
                await session.execute(
                    select(DashboardAccount)
                    .where(col(DashboardAccount.is_active).is_(True))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if account is not None:
                account.username = str(dashboard_config.get("username", "astrbot"))
                account.password_hash = str(dashboard_config.get("pbkdf2_password", ""))
                totp = dashboard_config.get("totp", {})
                if isinstance(totp, dict):
                    account.totp_enabled = bool(totp.get("enable"))
                    account.totp_secret = str(totp.get("secret", "") or "")
                    account.totp_recovery_code_hash = str(
                        totp.get("recovery_code_hash", "") or ""
                    )
                else:
                    account.totp_enabled = False
                    account.totp_secret = ""
                    account.totp_recovery_code_hash = ""


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def authenticated_header(app: FastAPI, core_lifecycle_td: AstrBotCoreLifecycle):
    """Handles login and returns an authenticated header."""
    test_client = DashboardTestClient(app)
    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    data = await response.get_json()
    assert data["status"] == "ok"
    token = data["data"]["token"]
    await test_client.aclose()
    return {"Authorization": f"Bearer {token}"}


class _FakeNeoSkills:
    async def list_candidates(self, **kwargs):
        _ = kwargs
        return [
            {
                "id": "cand-1",
                "skill_key": "neo.demo",
                "status": "evaluated_pass",
                "payload_ref": "pref-1",
            }
        ]

    async def list_releases(self, **kwargs):
        _ = kwargs
        return [
            {
                "id": "rel-1",
                "skill_key": "neo.demo",
                "candidate_id": "cand-1",
                "stage": "stable",
                "active": True,
            }
        ]

    async def get_payload(self, payload_ref: str):
        return {
            "payload_ref": payload_ref,
            "payload": {"skill_markdown": "# Demo"},
        }

    async def evaluate_candidate(self, candidate_id: str, **kwargs):
        return {"candidate_id": candidate_id, **kwargs}

    async def promote_candidate(self, candidate_id: str, stage: str = "canary"):
        return {
            "id": "rel-2",
            "skill_key": "neo.demo",
            "candidate_id": candidate_id,
            "stage": stage,
        }

    async def rollback_release(self, release_id: str):
        return {"id": "rb-1", "rolled_back_release_id": release_id}


class _FakeNeoBayClient:
    def __init__(self, endpoint_url: str, access_token: str):
        self.endpoint_url = endpoint_url
        self.access_token = access_token
        self.skills = _FakeNeoSkills()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        _ = exc_type, exc, tb
        return False


__all__ = [name for name in globals() if not name.startswith("__")]
