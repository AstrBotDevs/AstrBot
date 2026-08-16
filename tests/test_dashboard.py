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
from astrbot.core.db.po import DashboardAccount
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


def test_access_log_redacts_plugin_page_and_file_handles():
    logger = object.__new__(_ProxyAwareHypercornLogger)

    def atoms(path: str, query: bytes = b"secret=query"):
        return logger.atoms(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "query_string": query,
                "headers": [],
                "http_version": "1.1",
                "scheme": "https",
                "client": ("127.0.0.1", 1234),
            },
            {"status": 404, "headers": [(b"content-length", b"0")]},
            0.01,
        )

    page = atoms("/api/plugin-pages/v1/sessions/page-secret/")
    file = atoms("/api/plugin-files/v1/file-secret")
    assert "page-secret" not in page["r"]
    assert "file-secret" not in file["r"]
    assert page["U"] == "/api/plugin-pages/v1/sessions/<redacted>/"
    assert file["U"] == "/api/plugin-files/v1/<redacted>"
    assert page["q"] == file["q"] == ""


async def _wait_for_update_progress(
    test_client,
    authenticated_header: dict,
    progress_id: str,
) -> dict:
    """Wait until a core update task reaches a terminal status.

    Args:
        test_client: Quart/FastAPI adapter test client.
        authenticated_header: Headers for authenticated dashboard requests.
        progress_id: Update progress id to poll.

    Returns:
        The progress response payload.
    """
    for _ in range(100):
        response = await test_client.get(
            f"/api/v1/updates/progress/{progress_id}",
            headers=authenticated_header,
        )
        data = await response.get_json()
        if data["data"].get("status") in {"success", "error"}:
            return data
        await asyncio.sleep(0.01)
    pytest.fail(f"Update task did not finish: {progress_id}")


@pytest_asyncio.fixture(scope="module")
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
        core_lifecycle.astrbot_config["dashboard"]["password"] = (
            hash_md5_dashboard_password(dashboard_password)
        )
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


def test_dashboard_uses_bundled_dist_when_data_dist_is_stale(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "data"
    user_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    user_dist.mkdir(parents=True)
    bundled_dist.mkdir()
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.application.get_bundled_dashboard_dist_path",
        lambda: bundled_dist,
    )
    monkeypatch.setattr(
        "astrbot.application.get_repo_dashboard_dist_path",
        lambda: tmp_path / "repo-dist",
    )
    monkeypatch.setattr(
        "astrbot.application.should_use_bundled_dashboard_dist",
        lambda *_args, **_kwargs: True,
    )

    webui_dir = asyncio.run(resolve_dashboard_assets())
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
        webui_dir,
    )

    assert server.data_path == str(user_dist)


def test_dashboard_prefers_repo_dist_when_data_dist_matches(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    from astrbot.core.config.default import VERSION

    data_dir = tmp_path / "data"
    user_dist = data_dir / "dist"
    repo_dist = tmp_path / "repo-dist"
    (user_dist / "assets").mkdir(parents=True)
    (repo_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (user_dist / "index.html").write_text("user", encoding="utf-8")
    (repo_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (repo_dist / "index.html").write_text("repo", encoding="utf-8")

    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.application.get_repo_dashboard_dist_path",
        lambda: repo_dist,
    )
    monkeypatch.setattr(
        "astrbot.application.get_bundled_dashboard_dist_path",
        lambda: tmp_path / "bundled-dist",
    )

    webui_dir = asyncio.run(resolve_dashboard_assets())
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
        webui_dir,
    )

    assert server.data_path == str(repo_dist)


def test_dashboard_ignores_mismatched_data_dist_without_bundled(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "data"
    user_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    (user_dist / "index.html").write_text("stale", encoding="utf-8")

    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.application.get_bundled_dashboard_dist_path",
        lambda: bundled_dist,
    )
    monkeypatch.setattr(
        "astrbot.application.get_repo_dashboard_dist_path",
        lambda: tmp_path / "repo-dist",
    )

    webui_dir = asyncio.run(resolve_dashboard_assets())
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
        webui_dir,
    )

    assert server.data_path is None


def test_dashboard_ignores_incomplete_mismatched_data_dist_without_bundled(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "data"
    user_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")

    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.application.get_bundled_dashboard_dist_path",
        lambda: bundled_dist,
    )
    monkeypatch.setattr(
        "astrbot.application.get_repo_dashboard_dist_path",
        lambda: tmp_path / "repo-dist",
    )

    webui_dir = asyncio.run(resolve_dashboard_assets())
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
        webui_dir,
    )

    assert server.data_path is None


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
                account.password_hash = str(
                    dashboard_config.get("pbkdf2_password", "")
                )
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


@pytest_asyncio.fixture(scope="module")
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


@pytest.mark.asyncio
async def test_auth_login(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    """Tests the login functionality with both wrong and correct credentials."""
    monkeypatch.setitem(
        app.state.dashboard_config,
        "DASHBOARD_JWT_COOKIE_SECURE",
        False,
    )

    test_client = DashboardTestClient(app)
    response = await test_client.post(
        "/api/v1/auth/login",
        json={"username": "wrong", "password": "password"},
    )
    data = await response.get_json()
    assert data["status"] == "error"

    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    data = await response.get_json()
    assert data["status"] == "ok" and "token" in data["data"]
    set_cookie_headers = response.headers.getlist("Set-Cookie")
    jwt_cookie_header = next(
        (value for value in set_cookie_headers if DASHBOARD_JWT_COOKIE_NAME in value),
        "",
    )
    assert jwt_cookie_header
    assert "HttpOnly" in jwt_cookie_header
    _assert_cookie_samesite_strict(jwt_cookie_header)
    assert "Secure" not in jwt_cookie_header
    assert "Path=/api/v1" in jwt_cookie_header
    assert any(
        DASHBOARD_JWT_COOKIE_NAME in value
        and "Path=/" in value
        and "Max-Age=0" in value
        for value in set_cookie_headers
    )


@pytest.mark.asyncio
async def test_auth_login_secure_cookie_override(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setitem(
        app.state.dashboard_config,
        "DASHBOARD_JWT_COOKIE_SECURE",
        True,
    )

    test_client = DashboardTestClient(app)
    response = await test_client.post(
        "/api/v1/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    assert response.status_code == 200

    set_cookie_headers = response.headers.getlist("Set-Cookie")
    jwt_cookie_header = next(
        (value for value in set_cookie_headers if DASHBOARD_JWT_COOKIE_NAME in value),
        "",
    )
    assert jwt_cookie_header
    assert "Secure" in jwt_cookie_header
    _assert_cookie_samesite_strict(jwt_cookie_header)
    assert "Path=/api/v1" in jwt_cookie_header


@pytest.mark.asyncio
async def test_each_dashboard_login_uses_a_distinct_session_id(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    credentials = {
        "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
        "password": _resolve_dashboard_password(core_lifecycle_td),
    }

    first_response = await test_client.post("/api/v1/auth/login", json=credentials)
    second_response = await test_client.post("/api/v1/auth/login", json=credentials)
    first_token = (await first_response.get_json())["data"]["token"]
    second_token = (await second_response.get_json())["data"]["token"]

    first = app.state.dashboard_token_validator.validate(first_token)
    second = app.state.dashboard_token_validator.validate(second_token)
    assert first.sid != second.sid
    assert first.jti != second.jti


@pytest.mark.asyncio
async def test_auth_login_does_not_require_test_adapter_wrapper(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    asgi_app = app
    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(DASHBOARD_JWT_COOKIE_NAME in value for value in set_cookie_headers)


@pytest.mark.asyncio
async def test_auth_rate_limit_uses_same_bucket_across_paths(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    """Same client IP shares a rate-limit bucket across different auth endpoints."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    app.state.dashboard_server._rate_limiter_registry.clear()
    cfg = core_lifecycle_td.astrbot_config["dashboard"]
    rl_original = cfg.get("auth_rate_limit", {})
    tp_original = cfg.get("trust_proxy_headers", False)
    cfg["auth_rate_limit"] = {
        "enable": True,
        "average_interval": 3600.0,
        "max_burst": 1,
    }
    cfg["trust_proxy_headers"] = True

    try:
        client = DashboardTestClient(app)
        h = {"X-Forwarded-For": "198.51.100.10"}
        r1 = await client.post(
            "/api/v1/auth/login", json={"username": "u", "password": "p"}, headers=h
        )
        assert r1.status_code != 429, "first request from IP should not be rate limited"

        r2 = await client.post("/api/v1/auth/totp/setup", json={}, headers=h)
        assert r2.status_code == 429, (
            "second request from same IP should be rate limited"
        )
    finally:
        cfg["auth_rate_limit"] = rl_original
        cfg["trust_proxy_headers"] = tp_original


@pytest.mark.asyncio
async def test_auth_rate_limit_separates_different_client_ips(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    """Different client IPs have independent rate-limit buckets."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    app.state.dashboard_server._rate_limiter_registry.clear()
    cfg = core_lifecycle_td.astrbot_config["dashboard"]
    rl_original = cfg.get("auth_rate_limit", {})
    tp_original = cfg.get("trust_proxy_headers", False)
    cfg["auth_rate_limit"] = {
        "enable": True,
        "average_interval": 3600.0,
        "max_burst": 1,
    }
    cfg["trust_proxy_headers"] = True

    try:
        client = DashboardTestClient(app)
        r_a = await client.post(
            "/api/v1/auth/login",
            json={"username": "u", "password": "p"},
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
        assert r_a.status_code != 429

        r_b = await client.post(
            "/api/v1/auth/login",
            json={"username": "u", "password": "p"},
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
        assert r_b.status_code == 429, (
            "second request from same IP should be rate limited"
        )

        r_c = await client.post(
            "/api/v1/auth/login",
            json={"username": "u", "password": "p"},
            headers={"X-Forwarded-For": "198.51.100.11"},
        )
        assert r_c.status_code != 429, "different IP has its own bucket"
    finally:
        cfg["auth_rate_limit"] = rl_original
        cfg["trust_proxy_headers"] = tp_original


@pytest.mark.asyncio
async def test_auth_rate_limit_applies_to_v1_login(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    """The v1 login endpoint uses the dashboard token-bucket limiter."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    app.state.dashboard_server._rate_limiter_registry.clear()
    cfg = core_lifecycle_td.astrbot_config["dashboard"]
    rl_original = cfg.get("auth_rate_limit", {})
    tp_original = cfg.get("trust_proxy_headers", False)
    cfg["auth_rate_limit"] = {
        "enable": True,
        "average_interval": 3600.0,
        "max_burst": 1,
    }
    cfg["trust_proxy_headers"] = True

    try:
        client = DashboardTestClient(app)
        headers = {"X-Forwarded-For": "198.51.100.12"}
        first = await client.post(
            "/api/v1/auth/login",
            json={"username": "u", "password": "p"},
            headers=headers,
        )
        assert first.status_code != 429

        second = await client.post(
            "/api/v1/auth/login",
            json={"username": "u", "password": "p"},
            headers=headers,
        )
        assert second.status_code == 429, "v1 login should be rate limited"
    finally:
        cfg["auth_rate_limit"] = rl_original
        cfg["trust_proxy_headers"] = tp_original


@pytest.mark.asyncio
async def test_auth_rate_limit_ignores_proxy_headers_by_default(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    """When trust_proxy_headers is False, all proxy-spoofed IPs fall back to the connection IP."""
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    app.state.dashboard_server._rate_limiter_registry.clear()
    cfg = core_lifecycle_td.astrbot_config["dashboard"]
    rl_original = cfg.get("auth_rate_limit", {})
    tp_original = cfg.get("trust_proxy_headers", False)
    cfg["auth_rate_limit"] = {
        "enable": True,
        "average_interval": 3600.0,
        "max_burst": 1,
    }
    cfg["trust_proxy_headers"] = False

    try:
        client = DashboardTestClient(app)
        r1 = await client.post(
            "/api/v1/auth/login",
            json={"username": "u", "password": "p"},
            headers={"X-Forwarded-For": "198.51.100.20"},
        )
        assert r1.status_code != 429

        r2 = await client.post(
            "/api/v1/auth/login",
            json={"username": "u", "password": "p"},
            headers={"X-Forwarded-For": "198.51.100.21"},
        )
        assert r2.status_code == 429, (
            "same connection IP, same bucket despite proxy headers"
        )
    finally:
        cfg["auth_rate_limit"] = rl_original
        cfg["trust_proxy_headers"] = tp_original


def test_auth_rate_limiter_registry_evicts_oldest_entry_at_capacity(
    monkeypatch: pytest.MonkeyPatch,
):
    """An attacker cannot grow the per-IP limiter registry without bound."""
    monkeypatch.setattr(_RateLimiterRegistry, "_MAX_ENTRIES", 2)
    registry = _RateLimiterRegistry()
    oldest = registry.get_or_create("198.51.100.1", capacity=1, refill_rate=1.0)
    newest = registry.get_or_create("198.51.100.2", capacity=1, refill_rate=1.0)
    oldest.last_accessed = 1.0
    newest.last_accessed = 2.0

    registry.get_or_create("198.51.100.3", capacity=1, refill_rate=1.0)

    assert "198.51.100.1" not in registry
    assert "198.51.100.2" in registry
    assert "198.51.100.3" in registry


@pytest.mark.asyncio
async def test_auth_login_requires_totp_when_enabled_and_not_trusted(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    _, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        await _set_dashboard_account_totp(core_lifecycle_td, secret, recovery_code_hash)
        response = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
        )
        data = await response.get_json()
        assert response.status_code == 401
        assert data["status"] == "error"
        assert data["data"]["totp_required"] is True
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_auth_login_accepts_valid_totp_code(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    _, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        await _set_dashboard_account_totp(core_lifecycle_td, secret, recovery_code_hash)
        response = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
                "code": pyotp.TOTP(secret).now(),
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert "token" in data["data"]
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_auth_login_rejects_invalid_totp_code(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    _, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        await _set_dashboard_account_totp(core_lifecycle_td, secret, recovery_code_hash)
        valid_code = pyotp.TOTP(secret).now()
        invalid_code = str((int(valid_code) + 1) % 1_000_000).zfill(6)
        response = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
                "code": invalid_code,
            },
        )
        data = await response.get_json()
        assert response.status_code == 401
        assert data["status"] == "error"
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_auth_login_with_recovery_code_disables_totp(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    recovery_code, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        await _set_dashboard_account_totp(core_lifecycle_td, secret, recovery_code_hash)
        response = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
                "code": recovery_code,
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert core_lifecycle_td.astrbot_config["dashboard"]["totp"] == {
            "enable": False,
            "secret": "",
            "recovery_code_hash": "",
        }
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_auth_login_sets_trusted_device_cookie_when_flag_true(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    _, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        await _set_dashboard_account_totp(core_lifecycle_td, secret, recovery_code_hash)
        response = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
                "code": pyotp.TOTP(secret).now(),
                "trust_device_flag": True,
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        set_cookie_headers = response.headers.getlist("Set-Cookie")
        trusted_cookie_header = next(
            (
                value
                for value in set_cookie_headers
                if TOTP_TRUSTED_DEVICE_COOKIE_NAME in value
            ),
            "",
        )
        assert trusted_cookie_header
        assert "HttpOnly" in trusted_cookie_header
        _assert_cookie_samesite_strict(trusted_cookie_header)
        assert "Path=/api/v1/auth" in trusted_cookie_header
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_auth_login_skips_totp_when_trusted_cookie_valid(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    _, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        await _set_dashboard_account_totp(core_lifecycle_td, secret, recovery_code_hash)
        first_login = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
                "code": pyotp.TOTP(secret).now(),
                "trust_device_flag": True,
            },
        )
        first_data = await first_login.get_json()
        assert first_data["status"] == "ok"

        second_login = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
        )
        second_data = await second_login.get_json()
        assert second_login.status_code == 200
        assert second_data["status"] == "ok"
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_config_save_requires_two_factor_for_protected_totp_changes(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    _, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        post_config = copy.deepcopy(dict(core_lifecycle_td.astrbot_config))
        post_config["dashboard"]["totp"] = {
            "enable": False,
            "secret": "",
            "recovery_code_hash": "",
        }
        response = await test_client.put(
            "/api/v1/system-config",
            headers=authenticated_header,
            json=post_config,
        )
        data = await response.get_json()
        assert response.status_code == 401
        assert data["status"] == "error"
        assert data["data"]["totp_required"] is True
        assert core_lifecycle_td.astrbot_config["dashboard"]["totp"] == {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_config_save_accepts_totp_code_for_protected_totp_changes(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    _, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        post_config = copy.deepcopy(dict(core_lifecycle_td.astrbot_config))
        post_config["dashboard"]["totp"] = {
            "enable": False,
            "secret": "",
            "recovery_code_hash": "",
        }
        response = await test_client.put(
            "/api/v1/system-config",
            headers={
                **authenticated_header,
                "X-2FA-Code": pyotp.TOTP(secret).now(),
            },
            json=post_config,
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert core_lifecycle_td.astrbot_config["dashboard"]["totp"] == {
            "enable": False,
            "secret": "",
            "recovery_code_hash": "",
        }
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_config_save_rejects_recovery_code_for_protected_totp_changes(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    recovery_code, recovery_code_hash = generate_recovery_code()
    secret = pyotp.random_base32()

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
        post_config = copy.deepcopy(dict(core_lifecycle_td.astrbot_config))
        post_config["dashboard"]["totp"] = {
            "enable": False,
            "secret": "",
            "recovery_code_hash": recovery_code_hash,
        }
        response = await test_client.put(
            "/api/v1/system-config",
            headers={
                **authenticated_header,
                "X-2FA-Code": recovery_code,
            },
            json=post_config,
        )
        data = await response.get_json()
        assert response.status_code == 401
        assert data["status"] == "error"
        assert data["data"]["totp_required"] is True
        assert core_lifecycle_td.astrbot_config["dashboard"]["totp"] == {
            "enable": True,
            "secret": secret,
            "recovery_code_hash": recovery_code_hash,
        }
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_auth_totp_setup_with_valid_code_returns_recovery_code(
    app: FastAPI,
    authenticated_header: dict,
):
    test_client = DashboardTestClient(app)
    secret = pyotp.random_base32()
    response = await test_client.post(
        "/api/v1/auth/totp/setup",
        headers=authenticated_header,
        json={"secret": secret, "code": pyotp.TOTP(secret).now()},
    )
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"]["recovery_code"], str)
    assert isinstance(data["data"]["recovery_code_hash"], str)
    assert data["data"]["recovery_code"]
    assert data["data"]["recovery_code_hash"]


@pytest.mark.asyncio
async def test_totp_rotation_is_scoped_to_the_authenticated_dashboard_session(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    authenticated_header: dict,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    current_secret = pyotp.random_base32()
    replacement_secret = pyotp.random_base32()
    test_client = DashboardTestClient(app)

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["totp"] = {
            "enable": True,
            "secret": current_secret,
            "recovery_code_hash": "recovery-hash",
        }
        await _set_dashboard_account_totp(
            core_lifecycle_td, current_secret, "recovery-hash"
        )
        username = core_lifecycle_td.astrbot_config["dashboard"]["username"]
        bootstrap_token = authenticated_header["Authorization"].split(" ", 1)[1]
        account_id = app.state.dashboard_token_validator.validate(
            bootstrap_token
        ).account_id
        assert account_id is not None
        first_token = app.state.dashboard_token_validator.issue(
            username,
            account_id=account_id,
        )
        second_token = app.state.dashboard_token_validator.issue(
            username,
            account_id=account_id,
        )
        first_headers = {"Authorization": f"Bearer {first_token}"}
        second_headers = {"Authorization": f"Bearer {second_token}"}

        verified = await test_client.post(
            "/api/v1/auth/totp/setup",
            headers=first_headers,
            json={"code": pyotp.TOTP(current_secret).now()},
        )
        assert (await verified.get_json())["status"] == "ok"

        replacement_payload = {
            "secret": replacement_secret,
            "code": pyotp.TOTP(replacement_secret).now(),
        }
        rejected = await test_client.post(
            "/api/v1/auth/totp/setup",
            headers=second_headers,
            json=replacement_payload,
        )
        assert (await rejected.get_json())["status"] == "error"

        staged = await test_client.post(
            "/api/v1/auth/totp/setup",
            headers=first_headers,
            json=replacement_payload,
        )
        assert (await staged.get_json())["status"] == "ok"
    finally:
        await app.state.services.auth.totp_runtime_state.clear_all()
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )
        await test_client.aclose()


@pytest.mark.asyncio
async def test_md5_dashboard_password_keeps_md5_auth_until_edit(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    md5_password = "AstrbotMd5Pass123"
    changed_password = "AstrbotChanged123"

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["username"] = "astrbot"
        core_lifecycle_td.astrbot_config["dashboard"]["password"] = (
            hash_md5_dashboard_password(md5_password)
        )
        core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"] = ""
        await _set_dashboard_password_change_required(core_lifecycle_td, False)
        await set_password_storage_upgraded(
            core_lifecycle_td.astrbot_config,
            False,
        )
        await _set_dashboard_account_password(
            core_lifecycle_td,
            "astrbot",
            hash_md5_dashboard_password(md5_password),
        )

        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "astrbot", "password": md5_password},
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["change_pwd_hint"] is False
        assert data["data"]["md5_pwd_hint"] is True
        assert _removed_md5_hint_alias_key() not in data["data"]
        assert data["data"]["password_upgrade_required"] is True

        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "astrbot", "password": md5_password},
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["md5_pwd_hint"] is True
        assert _removed_md5_hint_alias_key() not in data["data"]
        assert data["data"]["password_upgrade_required"] is True

        response = await test_client.patch(
            "/api/v1/auth/account",
            headers={"Origin": "http://testserver"},
            json={
                "password": md5_password,
                "new_password": "",
                "confirm_password": "",
                "new_username": "astrbot-admin",
            },
        )
        data = await response.get_json()
        assert data["status"] == "error"
        assert (
            await is_password_storage_upgraded(
                core_lifecycle_td.astrbot_config,
            )
            is False
        )

        response = await test_client.patch(
            "/api/v1/auth/account",
            headers={"Origin": "http://testserver"},
            json={
                "password": md5_password,
                "new_password": changed_password,
                "confirm_password": changed_password,
                "new_username": "astrbot",
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert (
            await is_password_storage_upgraded(
                core_lifecycle_td.astrbot_config,
            )
            is True
        )
        assert verify_dashboard_password(
            core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"],
            changed_password,
        )
        assert verify_dashboard_password(
            core_lifecycle_td.astrbot_config["dashboard"]["password"],
            changed_password,
        )
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_md5_login_failure_includes_upgrade_faq_hint(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    md5_password = "AstrbotMd5Pass123"

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["username"] = "astrbot"
        core_lifecycle_td.astrbot_config["dashboard"]["password"] = (
            hash_md5_dashboard_password(md5_password)
        )
        core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"] = ""
        await _set_dashboard_password_change_required(core_lifecycle_td, False)
        await set_password_storage_upgraded(
            core_lifecycle_td.astrbot_config,
            False,
        )
        await _set_dashboard_account_password(
            core_lifecycle_td,
            "astrbot",
            hash_md5_dashboard_password(md5_password),
        )

        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "astrbot", "password": "WrongPassword123"},
        )
        data = await response.get_json()

        assert data["status"] == "error"
        assert data["message"].startswith("Incorrect username or password.")
        assert "请参考" in data["message"]
        assert "https://docs.astrbot.app/en/faq.html" in data["message"]
        assert "https://docs.astrbot.app/faq.html" in data["message"]
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_password_storage_flag_repairs_after_rollback_clears_pbkdf2(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    md5_password = "AstrbotRollback123"

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["username"] = "astrbot"
        core_lifecycle_td.astrbot_config["dashboard"]["password"] = (
            hash_md5_dashboard_password(md5_password)
        )
        core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"] = ""
        await _set_dashboard_password_change_required(core_lifecycle_td, False)
        await set_password_storage_upgraded(
            core_lifecycle_td.astrbot_config,
            True,
        )
        await _set_dashboard_account_password(
            core_lifecycle_td,
            "astrbot",
            hash_md5_dashboard_password(md5_password),
        )

        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "astrbot", "password": md5_password},
        )
        data = await response.get_json()

        assert data["status"] == "ok"
        assert data["data"]["md5_pwd_hint"] is True
        assert _removed_md5_hint_alias_key() not in data["data"]
        assert data["data"]["password_upgrade_required"] is True
        assert (
            await is_password_storage_upgraded(
                core_lifecycle_td.astrbot_config,
            )
            is False
        )
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_version_endpoints_use_md5_password_hint(
    app: FastAPI,
    authenticated_header: dict,
):
    test_client = DashboardTestClient(app)

    response = await test_client.get(
        "/api/v1/stats/version",
        headers=authenticated_header,
    )
    data = await response.get_json()

    assert data["status"] == "ok"
    assert "md5_pwd_hint" in data["data"]
    assert _removed_md5_hint_alias_key() not in data["data"]


@pytest.mark.asyncio
async def test_public_versions_endpoint_does_not_require_auth(app: FastAPI):
    test_client = DashboardTestClient(app)

    response = await test_client.get("/api/v1/stats/versions")
    data = await response.get_json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["data"]["astrbot_version"]
    assert "webui_version" in data["data"]
    assert "astrbot_code_version" in data["data"]
    assert "change_pwd_hint" not in data["data"]
    assert "md5_pwd_hint" not in data["data"]
    assert "password_upgrade_required" not in data["data"]


@pytest.mark.asyncio
async def test_legacy_public_dashboard_aliases_are_removed(app: FastAPI):
    test_client = DashboardTestClient(app)

    versions_response = await test_client.get("/api/stat/versions")
    login_response = await test_client.post("/api/auth/login", json={})
    logout_response = await test_client.post("/api/auth/logout")

    assert versions_response.status_code == 404
    assert login_response.status_code == 405
    assert logout_response.status_code == 405


def test_password_hash_lookup_falls_back_to_md5_when_pbkdf2_missing(
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    dashboard_config = copy.deepcopy(core_lifecycle_td.astrbot_config["dashboard"])
    md5_hash = hash_md5_dashboard_password("AstrbotRollback123")

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["password"] = md5_hash
        core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"] = ""

        assert (
            get_dashboard_password_hash(
                core_lifecycle_td.astrbot_config,
                upgraded=True,
            )
            == md5_hash
        )
    finally:
        core_lifecycle_td.astrbot_config["dashboard"] = dashboard_config


@pytest.mark.asyncio
async def test_generated_password_requires_password_change_until_changed(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    changed_password = "AstrbotChanged123"

    try:
        await _set_dashboard_password_change_required(core_lifecycle_td, True)

        response = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["change_pwd_hint"] is True

        response = await test_client.patch(
            "/api/v1/auth/account",
            headers={"Origin": "http://testserver"},
            json={
                "password": _resolve_dashboard_password(core_lifecycle_td),
                "new_password": "",
                "confirm_password": "",
                "new_username": core_lifecycle_td.astrbot_config["dashboard"][
                    "username"
                ],
            },
        )
        data = await response.get_json()
        assert data["status"] == "error"
        assert (
            await is_password_change_required(
                core_lifecycle_td.astrbot_config,
            )
            is True
        )

        response = await test_client.patch(
            "/api/v1/auth/account",
            headers={"Origin": "http://testserver"},
            json={
                "password": _resolve_dashboard_password(core_lifecycle_td),
                "new_password": changed_password,
                "confirm_password": changed_password,
                "new_username": core_lifecycle_td.astrbot_config["dashboard"][
                    "username"
                ],
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert (
            await is_password_change_required(
                core_lifecycle_td.astrbot_config,
            )
            is False
        )
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("new_username", ["ab", "   "])
async def test_account_edit_rejects_invalid_username(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    new_username: str,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    current_username = core_lifecycle_td.astrbot_config["dashboard"]["username"]
    current_password = _resolve_dashboard_password(core_lifecycle_td)

    try:
        login_response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": current_username, "password": current_password},
        )
        login_data = await login_response.get_json()
        assert login_data["status"] == "ok"
        headers = {"Authorization": f"Bearer {login_data['data']['token']}"}

        payload = {
            "password": current_password,
            "new_password": "",
            "confirm_password": "",
            "new_username": new_username,
        }
        response = await test_client.patch(
            "/api/v1/auth/account",
            headers=headers,
            json=payload,
        )
        data = await response.get_json()

        assert data["status"] == "error"
        assert data["message"] == "用户名长度至少3位"
        assert (
            core_lifecycle_td.astrbot_config["dashboard"]["username"]
            == (original_dashboard_config["username"])
        )
    finally:
        await test_client.aclose()
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_account_edit_trims_valid_username(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    current_username = core_lifecycle_td.astrbot_config["dashboard"]["username"]
    current_password = _resolve_dashboard_password(core_lifecycle_td)

    try:
        login_response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": current_username, "password": current_password},
        )
        login_data = await login_response.get_json()
        assert login_data["status"] == "ok"
        headers = {"Authorization": f"Bearer {login_data['data']['token']}"}

        response = await test_client.patch(
            "/api/v1/auth/account",
            headers=headers,
            json={
                "password": current_password,
                "new_password": "",
                "confirm_password": "",
                "new_username": "  astrbot-admin  ",
            },
        )
        data = await response.get_json()

        assert data["status"] == "ok"
        assert core_lifecycle_td.astrbot_config["dashboard"]["username"] == (
            "astrbot-admin"
        )
    finally:
        await test_client.aclose()
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_local_setup_can_skip_default_password_auth(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    setup_password = "AstrbotSetup123"
    setup_username = "astrbot-admin"

    try:
        monkeypatch.setenv("ASTRBOT_DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH", "true")
        core_lifecycle_td.astrbot_config["dashboard"]["host"] = "127.0.0.1"
        await _set_dashboard_password_change_required(core_lifecycle_td, True)

        response = await test_client.get("/api/v1/auth/setup-status")
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["setup_required"] is True
        assert data["data"]["skip_default_password_auth"] is True

        response = await test_client.post(
            "/api/v1/auth/setup",
            json={
                "username": setup_username,
                "password": setup_password,
                "confirm_password": setup_password,
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["username"] == setup_username
        assert data["data"]["token"]
        assert (
            await is_password_change_required(
                core_lifecycle_td.astrbot_config,
            )
            is False
        )
        assert (
            core_lifecycle_td.astrbot_config["dashboard"]["username"] == setup_username
        )
        assert verify_dashboard_password(
            core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"],
            setup_password,
        )
        assert verify_dashboard_password(
            core_lifecycle_td.astrbot_config["dashboard"]["password"],
            setup_password,
        )
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_authenticated_default_password_login_can_complete_setup(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)
    setup_password = "AstrbotSetup123"
    setup_username = "astrbot-admin"

    try:
        await _set_dashboard_password_change_required(core_lifecycle_td, True)

        login_response = await test_client.post(
            "/api/v1/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
        )
        login_data = await login_response.get_json()
        assert login_data["status"] == "ok"
        assert login_data["data"]["change_pwd_hint"] is True
        token = login_data["data"]["token"]

        response = await test_client.post(
            "/api/v1/auth/setup",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "username": setup_username,
                "password": setup_password,
                "confirm_password": setup_password,
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["username"] == setup_username
        assert (
            await is_password_change_required(
                core_lifecycle_td.astrbot_config,
            )
            is False
        )
        assert verify_dashboard_password(
            core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"],
            setup_password,
        )
        assert verify_dashboard_password(
            core_lifecycle_td.astrbot_config["dashboard"]["password"],
            setup_password,
        )
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_setup_skip_requires_local_host(
    app: FastAPI,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = DashboardTestClient(app)

    try:
        monkeypatch.setenv("ASTRBOT_DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH", "true")
        core_lifecycle_td.astrbot_config["dashboard"]["host"] = "0.0.0.0"
        await _set_dashboard_password_change_required(core_lifecycle_td, True)

        response = await test_client.get("/api/v1/auth/setup-status")
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["setup_required"] is True
        assert data["data"]["skip_default_password_auth"] is False

        response = await test_client.post(
            "/api/v1/auth/setup",
            json={
                "username": "astrbot-admin",
                "password": "AstrbotSetup123",
                "confirm_password": "AstrbotSetup123",
            },
        )
        data = await response.get_json()
        assert data["status"] == "error"
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


@pytest.mark.asyncio
async def test_dashboard_static_routes_disable_cache(app: FastAPI, tmp_path: Path):
    (tmp_path / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
    app.state.dashboard_static_folder = str(tmp_path)
    test_client = DashboardTestClient(app)
    response = await test_client.get("/platforms")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/extension/astrbot_plugin_palette",
        "/extension/io.github.example.palette/pages/settings",
    ],
)
@pytest.mark.parametrize(
    "static_relative",
    [
        "dashboard/dist",
        "data/dist",
        "astrbot/dashboard/dist",
        "explicit-webui-dir",
    ],
)
async def test_dashboard_dynamic_extension_routes_serve_spa_index(
    app: FastAPI,
    tmp_path: Path,
    path: str,
    static_relative: str,
):
    static_root = tmp_path / static_relative
    static_root.mkdir(parents=True)
    (static_root / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
    assets = static_root / "assets"
    assets.mkdir()
    (assets / "plugin-ui-protocol").write_text("1", encoding="utf-8")
    app.state.dashboard_static_folder = str(static_root)

    service = StaticFileService()
    assert service.matches_dynamic_index_route(path)
    assert service.is_plugin_ui_protocol_compatible(static_root)

    response = await DashboardTestClient(app).get(path)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert b"dashboard" in await response.get_data()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/plugin/page/entry",
        "/api/plugin/page/bridge-sdk.js",
        "/api/plugin/page/content/astrbot_plugin_palette/settings/app.js",
        "/api/plug/astrbot_plugin_palette/config",
        "/api/v1/plugins/extensions/astrbot_plugin_palette/config",
    ],
)
async def test_removed_plugin_web_routes_return_404_without_redirect(
    app: FastAPI,
    path: str,
):
    response = await DashboardTestClient(app).get(path, follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers


@pytest.mark.asyncio
async def test_get_stat(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    response = await test_client.get("/api/v1/stats")
    assert response.status_code == 401
    await core_lifecycle_td.db.insert_platform_stats(
        "test-platform",
        "test",
        count=3,
        timestamp=datetime.now(),
    )
    response = await test_client.get("/api/v1/stats", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok" and "platform" in data["data"]
    assert data["data"]["message_count"] >= 3
    assert any(
        item["name"] == "test-platform" and item["count"] >= 3
        for item in data["data"]["platform"]
    )


@pytest.mark.asyncio
async def test_get_t2i_runtime_stats_requires_system_scope(
    app: FastAPI,
    authenticated_header: dict,
):
    test_client = DashboardTestClient(app)

    unauthorized = await test_client.get("/api/v1/stats/t2i")
    response = await test_client.get(
        "/api/v1/stats/t2i",
        headers=authenticated_header,
    )
    data = await response.get_json()

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["data"]["successful_renders"] >= 0
    assert data["data"]["active_pages"] >= 0


@pytest.mark.asyncio
async def test_dashboard_ssl_missing_cert_and_key_falls_back_to_http(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    shutdown_event = asyncio.Event()
    server = await AstrBotDashboard.create(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
    )
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config.get("dashboard", {}),
    )
    warning_messages = []
    info_messages = []

    async def fake_serve(app, config, shutdown_trigger):
        return config

    def capture(messages):
        def append(message, *args):
            messages.append(message % args if args else message)

        return append

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["ssl"] = {
            "enable": True,
            "cert_file": "",
            "key_file": "",
        }
        monkeypatch.setattr(server, "check_port_in_use", lambda port: False)
        monkeypatch.setattr("astrbot.dashboard.server.serve", fake_serve)
        monkeypatch.setattr(
            "astrbot.dashboard.server.logger.warning",
            capture(warning_messages),
        )
        monkeypatch.setattr(
            "astrbot.dashboard.server.logger.info",
            capture(info_messages),
        )

        config = await server.run()

        assert getattr(config, "certfile", None) is None
        assert getattr(config, "keyfile", None) is None
        assert any(
            "cert_file or key_file is missing" in message
            for message in warning_messages
        )
        assert any("Starting WebUI at http://" in message for message in info_messages)
    finally:
        core_lifecycle_td.astrbot_config["dashboard"] = original_dashboard_config


@pytest.mark.asyncio
async def test_subagent_config_accepts_default_persona(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    old_cfg = copy.deepcopy(
        core_lifecycle_td.astrbot_config.get("subagent_orchestrator", {})
    )
    payload = {
        "main_enable": True,
        "remove_main_duplicate_tools": True,
        "agents": [
            {
                "name": "planner",
                "persona_id": "default",
                "public_description": "planner",
                "system_prompt": "",
                "enabled": True,
            }
        ],
    }

    try:
        response = await test_client.put(
            "/api/v1/subagents/config",
            json=payload,
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        get_response = await test_client.get(
            "/api/v1/subagents/config", headers=authenticated_header
        )
        assert get_response.status_code == 200
        get_data = await get_response.get_json()
        assert get_data["status"] == "ok"
        assert get_data["data"]["agents"][0]["persona_id"] == "default"
    finally:
        await test_client.put(
            "/api/v1/subagents/config",
            json=old_cfg,
            headers=authenticated_header,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], "x"])
async def test_batch_delete_sessions_rejects_non_object_payload(
    app: FastAPI, authenticated_header: dict, payload
):
    test_client = DashboardTestClient(app)
    response = await test_client.post(
        "/api/v1/chat/sessions/batch-delete",
        json=payload,
        headers=authenticated_header,
    )

    assert response.status_code == 422
    data = await response.get_json()
    assert data == {"status": "error", "message": "Invalid request payload"}


@pytest.mark.asyncio
async def test_batch_delete_sessions_masks_internal_error(
    app: FastAPI, authenticated_header: dict, monkeypatch
):
    test_client = DashboardTestClient(app)

    create_session_response = await test_client.get(
        "/api/v1/chat/sessions/new", headers=authenticated_header
    )
    assert create_session_response.status_code == 200
    create_session_data = await create_session_response.get_json()
    session_id = create_session_data["data"]["session_id"]

    async def _raise_error(*args, **kwargs):
        raise RuntimeError("secret-internal-error")

    monkeypatch.setattr(
        "astrbot.dashboard.services.chat_service.ChatService.delete_session_internal",
        _raise_error,
    )

    response = await test_client.post(
        "/api/v1/chat/sessions/batch-delete",
        json={"session_ids": [session_id]},
        headers=authenticated_header,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["deleted_count"] == 0
    assert data["data"]["failed_count"] == 1
    assert data["data"]["failed_items"][0]["session_id"] == session_id
    assert data["data"]["failed_items"][0]["reason"] == "internal_error"


@pytest.mark.asyncio
async def test_batch_delete_sessions_uses_batch_lookup(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    db = core_lifecycle_td.db

    create_session_response = await test_client.get(
        "/api/v1/chat/sessions/new", headers=authenticated_header
    )
    assert create_session_response.status_code == 200
    create_session_data = await create_session_response.get_json()
    session_id = create_session_data["data"]["session_id"]

    original_batch_lookup = db.get_platform_sessions_by_ids
    called = {"batch_lookup_count": 0}

    async def _wrapped_batch_lookup(session_ids: list[str]):
        called["batch_lookup_count"] += 1
        return await original_batch_lookup(session_ids)

    # Ensure the optimized batch lookup path is used.
    async def _should_not_call_single_lookup(session_id: str):
        raise AssertionError(
            f"single-session lookup should not be called: {session_id}"
        )

    monkeypatch.setattr(db, "get_platform_sessions_by_ids", _wrapped_batch_lookup)
    monkeypatch.setattr(
        db, "get_platform_session_by_id", _should_not_call_single_lookup
    )

    response = await test_client.post(
        "/api/v1/chat/sessions/batch-delete",
        json={"session_ids": [session_id]},
        headers=authenticated_header,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["deleted_count"] == 1
    assert data["data"]["failed_count"] == 0
    assert called["batch_lookup_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path_template", "expected_status", "expected_message"),
    [
        ("/api/chat/get_session?session_id={session_id}", 404, None),
        ("/api/v1/chat/sessions/{session_id}", 200, "Permission denied"),
    ],
)
async def test_get_chat_session_rejects_session_owned_by_another_user(
    app: DashboardTestClient,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    path_template: str,
    expected_status: int,
    expected_message: str | None,
):
    test_client = DashboardTestClient(app)
    session_id = f"foreign_get_session_{uuid.uuid4().hex[:8]}"
    await core_lifecycle_td.db.create_platform_session(
        creator="not_dashboard_user",
        platform_id="webchat",
        session_id=session_id,
        display_name="Foreign Session",
        is_group=0,
    )
    await core_lifecycle_td.platform_message_history_manager.insert(
        platform_id="webchat",
        user_id=session_id,
        content={
            "type": "user",
            "message": [{"type": "text", "text": "foreign session secret"}],
        },
        sender_id="not_dashboard_user",
        sender_name="not_dashboard_user",
    )

    response = await test_client.get(
        path_template.format(session_id=session_id),
        headers=authenticated_header,
    )

    assert response.status_code == expected_status
    if expected_message is None:
        return
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == expected_message


@pytest.mark.asyncio
async def test_plugins(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    """Tests plugin API endpoints with mocked install and update paths."""
    test_client = DashboardTestClient(app)

    async def plugin_deploy_headers() -> dict[str, str]:
        step_up = await test_client.post(
            "/api/v1/authorization/step-up",
            json={
                "action": "extension.plugin_install",
                "resource_type": "dashboard-api",
                "resource_id": "post-plugin",
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
            headers=authenticated_header,
        )
        assert step_up.status_code == 200
        return {
            **authenticated_header,
            "X-AstrBot-Step-Up": (await step_up.get_json())["data"]["token"],
        }

    async def mock_get_online_plugins(_service, *, custom_registry, force_refresh):
        del _service, custom_registry, force_refresh
        return [], None

    monkeypatch.setattr(
        PluginService,
        "get_online_plugins",
        mock_get_online_plugins,
    )

    response = await test_client.get("/api/v1/plugins", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    for plugin in data["data"]:
        assert "installed_at" in plugin
        assert "components" not in plugin
        installed_at = plugin["installed_at"]
        if installed_at is None:
            continue
        assert isinstance(installed_at, str)
        datetime.fromisoformat(installed_at)

    response = await test_client.get(
        "/api/v1/plugins/market",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    plugin_store_path = core_lifecycle_td.plugin_manager.packages.store_path
    builder = MockPluginBuilder(plugin_store_path)
    test_plugin_name = "test_mock_plugin"
    test_repo_url = f"https://github.com/test/{test_plugin_name}"
    mock_install = create_mock_updater_install(
        builder,
        repo_to_plugin={test_repo_url: test_plugin_name},
    )
    mock_update = create_mock_updater_update(builder)

    monkeypatch.setattr(
        core_lifecycle_td.plugin_manager.packages._updator, "install", mock_install
    )
    monkeypatch.setattr(
        core_lifecycle_td.plugin_manager.packages._updator,
        "update",
        mock_update,
    )

    try:
        response = await test_client.post(
            "/api/v1/plugins/install/github",
            json={"repository": test_repo_url},
            headers=await plugin_deploy_headers(),
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok", (
            f"安装失败: {data.get('message', 'unknown error')}"
        )

        response = await test_client.get(
            f"/api/v1/plugins?name={test_plugin_name}",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert len(data["data"]) >= 1
        target = next(
            (item for item in data["data"] if item["name"] == test_plugin_name),
            None,
        )
        assert target is not None
        assert "components" not in target
        installed_at = target["installed_at"]
        assert installed_at is not None
        datetime.fromisoformat(installed_at)
        assert target["install_source"]["install_method"] == "github"
        assert target["install_source"]["repo"] == test_repo_url
        assert target["updates_enabled"] is True
        assert target["update_disabled_reason"] == ""

        response = await test_client.get(
            f"/api/v1/plugins/{test_plugin_name}",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["name"] == test_plugin_name
        assert "components" in data["data"]
        assert isinstance(data["data"]["components"], list)

        exists = any(
            md.name == test_plugin_name
            for md in core_lifecycle_td.runtime.catalogs.plugins.all()
        )
        assert exists is True, f"插件 {test_plugin_name} 未成功载入"

        response = await test_client.post(
            f"/api/v1/plugins/{test_plugin_name}/update",
            json={},
            headers=await plugin_deploy_headers(),
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        plugin_dir = builder.get_plugin_path(test_plugin_name)
        assert (plugin_dir / ".updated").read_text(encoding="utf-8") == "ok"

        response = await test_client.delete(
            f"/api/v1/plugins/{test_plugin_name}",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        exists = any(
            md.name == test_plugin_name
            for md in core_lifecycle_td.runtime.catalogs.plugins.all()
        )
        assert exists is False, f"插件 {test_plugin_name} 未成功卸载"
        exists = any(
            test_plugin_name in md.handler_module_path
            for md in core_lifecycle_td.runtime.catalogs.handlers
        )
        assert exists is False, f"插件 {test_plugin_name} handler 未成功清理"
    finally:
        builder.cleanup(test_plugin_name)


@pytest.mark.asyncio
async def test_plugins_when_installed_at_unresolved(
    app: FastAPI,
    authenticated_header: dict,
    monkeypatch,
):
    """Tests plugin payload when installed_at cannot be resolved."""
    test_client = DashboardTestClient(app)

    monkeypatch.setattr(PluginService, "get_plugin_installed_at", lambda *_args: None)

    response = await test_client.get("/api/v1/plugins", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    for plugin in data["data"]:
        assert "name" in plugin
        assert "installed_at" in plugin
        assert plugin["installed_at"] is None


@pytest.mark.asyncio
async def test_commands_api(app: FastAPI, authenticated_header: dict):
    """Tests the command management API endpoints."""
    test_client = DashboardTestClient(app)

    # GET /api/v1/commands - list commands
    response = await test_client.get("/api/v1/commands", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "items" in data["data"]
    assert "summary" in data["data"]
    summary = data["data"]["summary"]
    assert "total" in summary
    assert "disabled" in summary
    assert "conflicts" in summary

    # GET /api/v1/commands/conflicts - list conflicts
    response = await test_client.get(
        "/api/v1/commands/conflicts", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    # conflicts is a list
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_t2i_set_active_template_syncs_all_configs(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    template_name = f"sync_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("sync-a", "sync-b"):
            response = await test_client.post(
                "/api/v1/config-profiles",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/v1/t2i/templates",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }}</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201
        data = await response.get_json()
        assert data["status"] == "ok"

        response = await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": template_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        conf_ids = set(core_lifecycle_td.astrbot_config_mgr.confs.keys())
        assert "default" in conf_ids
        for conf_id in conf_ids:
            conf = core_lifecycle_td.astrbot_config_mgr.confs[conf_id]
            assert conf.get("t2i_active_template") == template_name
            assert conf_id in core_lifecycle_td.pipeline_scheduler_mapping
    finally:
        await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/v1/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.delete(
                f"/api/v1/config-profiles/{conf_id}",
                headers=authenticated_header,
            )


@pytest.mark.asyncio
async def test_t2i_reset_default_template_syncs_all_configs(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    template_name = f"reset_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("reset-a", "reset-b"):
            response = await test_client.post(
                "/api/v1/config-profiles",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/v1/t2i/templates",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }} reset</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201
        data = await response.get_json()
        assert data["status"] == "ok"

        response = await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": template_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200

        response = await test_client.post(
            "/api/v1/t2i/templates/default/reset",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        conf_ids = set(core_lifecycle_td.astrbot_config_mgr.confs.keys())
        assert "default" in conf_ids
        for conf_id in conf_ids:
            conf = core_lifecycle_td.astrbot_config_mgr.confs[conf_id]
            assert conf.get("t2i_active_template") == "base"
            assert conf_id in core_lifecycle_td.pipeline_scheduler_mapping
    finally:
        await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/v1/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.delete(
                f"/api/v1/config-profiles/{conf_id}",
                headers=authenticated_header,
            )


@pytest.mark.asyncio
async def test_t2i_update_active_template_reloads_all_schedulers(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = DashboardTestClient(app)
    template_name = f"update_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("update-a", "update-b"):
            response = await test_client.post(
                "/api/v1/config-profiles",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/v1/t2i/templates",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }} v1</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201

        response = await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": template_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200

        conf_ids = list(core_lifecycle_td.astrbot_config_mgr.confs.keys())
        old_schedulers = {
            conf_id: core_lifecycle_td.pipeline_scheduler_mapping[conf_id]
            for conf_id in conf_ids
        }

        response = await test_client.put(
            f"/api/v1/t2i/templates/{template_name}",
            json={"content": "<html><body>{{ text }} v2</body></html>"},
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        for conf_id in conf_ids:
            assert conf_id in core_lifecycle_td.pipeline_scheduler_mapping
            assert (
                core_lifecycle_td.pipeline_scheduler_mapping[conf_id]
                is not old_schedulers[conf_id]
            )
    finally:
        await test_client.put(
            "/api/v1/t2i/templates/active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/v1/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.delete(
                f"/api/v1/config-profiles/{conf_id}",
                headers=authenticated_header,
            )


@pytest.mark.asyncio
async def test_check_update(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    """Tests the update-check endpoint with mocked network calls."""
    test_client = DashboardTestClient(app)

    # Mock the release check.
    async def mock_check_update(*args, **kwargs):
        """Mock the updater returning no release."""
        return None

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "check_update",
        mock_check_update,
    )
    response = await test_client.get(
        "/api/v1/updates/check", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "success"
    assert data["data"]["has_new_version"] is False


@pytest.mark.asyncio
async def test_restart_core_rejects_desktop_managed_backend(
    app: DashboardTestClient,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    restart_called = False

    async def mock_restart():
        nonlocal restart_called
        restart_called = True

    monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    monkeypatch.setattr(core_lifecycle_td, "restart", mock_restart)

    response = await test_client.post(
        "/api/v1/system/restart",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.restart",
            resource_id="restart",
        ),
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == DESKTOP_MANAGED_RESTART_MESSAGE
    assert restart_called is False


@pytest.mark.slow
@pytest.mark.asyncio
async def test_do_update(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path_factory,
):
    test_client = DashboardTestClient(app)

    # Use a temporary path for the mock update to avoid side effects
    temp_release_dir = tmp_path_factory.mktemp("release")
    release_path = temp_release_dir / "astrbot"
    calls = []

    async def mock_download_core(*args, **kwargs):
        calls.append("download-core")
        callback = kwargs.get("progress_callback")
        if callback:
            callback({"downloaded": 10, "total": 10, "percent": 1, "speed": 1})
        zip_path = kwargs["path"]
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("AstrBot-main/README.md", "core")
        return zip_path

    def mock_apply_core(*args, **kwargs):
        del args, kwargs
        calls.append("apply-core")
        os.makedirs(release_path, exist_ok=True)

    async def mock_pip_install(*args, **kwargs):
        """Mocks pip install to prevent actual installation."""
        return

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )
    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "apply_update_package",
        mock_apply_core,
    )
    app.state.services.updates.pip_install = mock_pip_install

    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "test-progress"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["id"] == "test-progress"

    progress_data = await _wait_for_update_progress(
        test_client,
        authenticated_header,
        "test-progress",
    )
    assert os.path.exists(release_path)
    assert calls[:2] == ["download-core", "apply-core"]

    assert progress_data["status"] == "ok"
    assert progress_data["data"]["status"] == "success"
    assert progress_data["data"]["overall_percent"] == 100


@pytest.mark.asyncio
async def test_do_update_does_not_apply_files_when_core_download_fails(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    calls = []

    async def mock_download_core(*args, **kwargs):
        del args, kwargs
        calls.append("download-core")
        raise RuntimeError("core download failed")

    def mock_apply_core(*args, **kwargs):
        del args, kwargs
        calls.append("apply-core")

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )
    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "apply_update_package",
        mock_apply_core,
    )
    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "atomic-fail"},
    )
    data = await response.get_json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    progress_data = await _wait_for_update_progress(
        test_client,
        authenticated_header,
        "atomic-fail",
    )
    assert progress_data["data"]["status"] == "error"
    assert calls == ["download-core"]


@pytest.mark.asyncio
async def test_do_update_rejects_desktop_managed_backend(
    app: DashboardTestClient,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    calls = []

    async def mock_download_core(*args, **kwargs):
        del args, kwargs
        calls.append("download-core")

    async def mock_restart():
        calls.append("restart")

    monkeypatch.setenv("ASTRBOT_DESKTOP_MANAGED", "1")
    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )
    monkeypatch.setattr(core_lifecycle_td, "restart", mock_restart)

    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "desktop-progress"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == DESKTOP_MANAGED_RESTART_MESSAGE
    assert calls == []


@pytest.mark.asyncio
async def test_do_update_does_not_apply_files_when_package_verification_fails(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)
    calls = []

    async def mock_download_core(*args, **kwargs):
        del args
        calls.append("download-core")
        zip_path = kwargs["path"]
        Path(zip_path).write_bytes(b"not a zip")
        return zip_path

    def mock_apply_core(*args, **kwargs):
        del args, kwargs
        calls.append("apply-core")

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )
    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "apply_update_package",
        mock_apply_core,
    )
    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "invalid-zip"},
    )
    data = await response.get_json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    progress_data = await _wait_for_update_progress(
        test_client,
        authenticated_header,
        "invalid-zip",
    )
    assert progress_data["data"]["status"] == "error"
    assert calls == ["download-core"]


@pytest.mark.asyncio
async def test_do_update_hides_internal_error_message_in_response_and_progress(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)

    async def mock_download_core(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("secret stack trace")

    monkeypatch.setattr(
        app.state.services.updates.astrbot_updator,
        "download_update_package",
        mock_download_core,
    )

    response = await test_client.post(
        "/api/v1/updates/core",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.update",
            resource_id="core-update",
        ),
        json={"version": "v3.4.0", "reboot": False, "progress_id": "failed-progress"},
    )
    data = await response.get_json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert "secret stack trace" not in str(data)

    progress_data = await _wait_for_update_progress(
        test_client,
        authenticated_header,
        "failed-progress",
    )

    assert progress_data["status"] == "ok"
    assert progress_data["data"]["status"] == "error"
    assert progress_data["data"]["message"] == "更新失败，请查看服务端日志。"
    assert "secret stack trace" not in str(progress_data)


@pytest.mark.asyncio
async def test_install_pip_package_returns_generic_error_message(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = DashboardTestClient(app)

    async def mock_pip_install(*args, **kwargs):
        del args, kwargs
        raise PipInstallError("install failed", code=2)

    app.state.services.updates.pip_install = mock_pip_install

    response = await test_client.post(
        "/api/v1/pip/install",
        headers=await _high_risk_headers(
            test_client,
            authenticated_header,
            core_lifecycle_td,
            action="system.pip_install",
            resource_id="pip-install",
        ),
        json={"package": "demo-package"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "An internal error has occurred."


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


@pytest.mark.asyncio
async def test_neo_skills_routes(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    provider_settings = core_lifecycle_td.astrbot_config.setdefault(
        "provider_settings", {}
    )
    sandbox = provider_settings.setdefault("sandbox", {})
    sandbox["shipyard_neo_endpoint"] = "http://neo.test"
    sandbox["shipyard_neo_access_token"] = "neo-token"

    fake_shipyard_neo_module = SimpleNamespace(BayClient=_FakeNeoBayClient)
    monkeypatch.setitem(sys.modules, "shipyard_neo", fake_shipyard_neo_module)

    async def _fake_sync_release(self, client, **kwargs):
        _ = self, client, kwargs
        return SimpleNamespace(
            skill_key="neo.demo",
            local_skill_name="neo_demo",
            release_id="rel-2",
            candidate_id="cand-1",
            payload_ref="pref-1",
            map_path="data/skills/neo_skill_map.json",
            synced_at="2026-01-01T00:00:00Z",
        )

    async def _fake_sync_skills_to_active_sandboxes():
        return

    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.NeoSkillSyncManager.sync_release",
        _fake_sync_release,
    )
    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )

    test_client = DashboardTestClient(app)

    response = await test_client.get(
        "/api/v1/skills/neo/candidates", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)
    assert data["data"][0]["id"] == "cand-1"

    response = await test_client.get(
        "/api/v1/skills/neo/releases", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)
    assert data["data"][0]["id"] == "rel-1"

    response = await test_client.get(
        "/api/v1/skills/neo/payload?payload_ref=pref-1", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["payload_ref"] == "pref-1"

    response = await test_client.post(
        "/api/v1/skills/neo/evaluate",
        json={"candidate_id": "cand-1", "passed": True, "score": 0.95},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["candidate_id"] == "cand-1"
    assert data["data"]["passed"] is True

    response = await test_client.post(
        "/api/v1/skills/neo/evaluate",
        json={"candidate_id": "cand-1", "passed": "false", "score": 0.0},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["passed"] is False

    response = await test_client.post(
        "/api/v1/skills/neo/promote",
        json={"candidate_id": "cand-1", "stage": "stable"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["release"]["id"] == "rel-2"
    assert data["data"]["sync"]["local_skill_name"] == "neo_demo"

    response = await test_client.post(
        "/api/v1/skills/neo/rollback",
        json={"release_id": "rel-2"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["rolled_back_release_id"] == "rel-2"

    response = await test_client.post(
        "/api/v1/skills/neo/sync",
        json={"release_id": "rel-2"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["skill_key"] == "neo.demo"


@pytest.mark.asyncio
async def test_batch_upload_skills_returns_error_when_all_files_invalid(
    app: FastAPI,
    authenticated_header: dict,
):
    test_client = DashboardTestClient(app)

    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=authenticated_header,
        files={
            "files": FileStorage(
                stream=io.BytesIO(b"not-a-zip"),
                filename="invalid.txt",
                content_type="text/plain",
            ),
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Upload failed for all 1 file(s)."


@pytest.mark.asyncio
async def test_batch_upload_skills_accepts_zip_files(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    async def _fake_sync_skills_to_active_sandboxes():
        return

    def _fake_install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
        skill_name_hint: str | None = None,
    ):
        _ = self, overwrite
        assert zip_path.endswith(".zip")
        assert skill_name_hint == "demo_skill"
        return "demo_skill"

    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.SkillManager.install_skill_from_zip",
        _fake_install_skill_from_zip,
    )

    test_client = DashboardTestClient(app)

    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=authenticated_header,
        files={
            "files": FileStorage(
                stream=io.BytesIO(b"fake-zip"),
                filename="demo_skill.zip",
                content_type="application/zip",
            ),
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["message"] == "All 1 skill(s) uploaded successfully."
    assert data["data"]["total"] == 1
    assert data["data"]["succeeded"] == [
        {"filename": "demo_skill.zip", "name": "demo_skill"}
    ]
    assert data["data"]["failed"] == []


@pytest.mark.asyncio
async def test_batch_upload_skills_accepts_valid_skill_archive(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "data"
    skills_dir = tmp_path / "skills"
    temp_dir = tmp_path / "temp"
    data_dir.mkdir()
    skills_dir.mkdir()
    temp_dir.mkdir()

    async def _fake_sync_skills_to_active_sandboxes():
        return

    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_skills_path",
        lambda: str(skills_dir),
    )
    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.get_astrbot_temp_path",
        lambda: str(temp_dir),
    )
    test_skill_manager = SkillManager(
        skills_root=str(skills_dir),
        plugins_root=str(tmp_path / "plugins"),
    )
    monkeypatch.setattr(
        app.state.services.skills,
        "skill_manager",
        test_skill_manager,
    )

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "demo_skill/SKILL.md",
            "---\nname: demo-skill\ndescription: Demo skill\n---\n",
        )
        zf.writestr("demo_skill/notes.txt", "hello")
        zf.writestr("__MACOSX/demo_skill/._SKILL.md", "")
        zf.writestr("__MACOSX/._demo_skill", "")
    archive.seek(0)

    test_client = DashboardTestClient(app)

    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=authenticated_header,
        files={
            "files": FileStorage(
                stream=archive,
                filename="demo_skill.zip",
                content_type="application/zip",
            ),
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["succeeded"] == [
        {"filename": "demo_skill.zip", "name": "demo_skill"}
    ]
    assert data["data"]["failed"] == []
    assert (skills_dir / "demo_skill" / "SKILL.md").exists()


@pytest.mark.asyncio
async def test_batch_upload_skills_partial_success(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    async def _fake_sync_skills_to_active_sandboxes():
        return

    def _fake_install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
        skill_name_hint: str | None = None,
    ):
        _ = self, overwrite
        assert skill_name_hint in {"ok_skill", "bad_skill"}
        if "ok_skill" in zip_path:
            return "ok_skill"
        raise RuntimeError("install failed")

    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.SkillManager.install_skill_from_zip",
        _fake_install_skill_from_zip,
    )

    test_client = DashboardTestClient(app)

    boundary = "----AstrBotBatchBoundary"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="ok_skill.zip"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode()
        + b"fake-zip-1\r\n"
        + (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="files"; filename="bad_skill.zip"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode()
        + b"fake-zip-2\r\n"
        + f"--{boundary}--\r\n".encode()
    )
    headers = dict(authenticated_header)
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=headers,
        data=body,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["message"] == "Partial success: 1/2 skill(s) uploaded."
    assert data["data"]["total"] == 2
    assert data["data"]["succeeded"] == [
        {"filename": "ok_skill.zip", "name": "ok_skill"}
    ]
    assert data["data"]["failed"] == [
        {"filename": "bad_skill.zip", "error": "Skill upload failed"}
    ]


@pytest.mark.asyncio
async def test_batch_upload_skills_does_not_retry_internal_type_error(
    app: FastAPI,
    authenticated_header: dict,
    monkeypatch,
):
    calls = 0

    def _fake_install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
        skill_name_hint: str | None = None,
    ):
        nonlocal calls
        _ = self, zip_path, overwrite, skill_name_hint
        calls += 1
        raise TypeError("internal archive parsing failure")

    monkeypatch.setattr(
        "astrbot.dashboard.services.skills_service.SkillManager.install_skill_from_zip",
        _fake_install_skill_from_zip,
    )

    test_client = DashboardTestClient(app)
    response = await test_client.post(
        "/api/v1/skills/batch",
        headers=authenticated_header,
        files={
            "files": FileStorage(
                stream=io.BytesIO(b"fake-zip"),
                filename="demo_skill.zip",
                content_type="application/zip",
            ),
        },
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert calls == 1
    assert data["data"]["failed"] == [
        {"filename": "demo_skill.zip", "error": "Skill upload failed"}
    ]


@pytest.mark.asyncio
async def test_skill_file_browser_and_editor_security(
    app: FastAPI,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    async def _fake_sync_skills_to_active_sandboxes():
        return

    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "demo_skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\ndescription: Demo skill\n---\n# Demo\n",
        encoding="utf-8",
    )
    (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")
    (skill_dir / "large.md").write_text("x" * (512 * 1024 + 1), encoding="utf-8")
    (skill_dir / "binary.md").write_bytes(b"\xff\xfe\x00")
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("outside", encoding="utf-8")
    if hasattr(os, "symlink"):
        os.symlink(outside_file, skill_dir / "outside-link.txt")

    monkeypatch.setattr(
        "astrbot.core.skills.skill_manager.get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    test_skill_manager = SkillManager(
        skills_root=str(skills_root),
        plugins_root=str(tmp_path / "plugins"),
    )
    monkeypatch.setattr(
        app.state.services.skills,
        "skill_manager",
        test_skill_manager,
    )
    monkeypatch.setattr(
        core_lifecycle_td.services.computer_runtime,
        "sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )

    test_client = DashboardTestClient(app)

    list_response = await test_client.get(
        "/api/v1/skills/demo_skill/files",
        headers=authenticated_header,
    )
    list_data = await list_response.get_json()
    assert list_data["status"] == "ok"
    listed_paths = {item["path"] for item in list_data["data"]["entries"]}
    assert "SKILL.md" in listed_paths
    assert "outside-link.txt" not in listed_paths

    read_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/SKILL.md",
        headers=authenticated_header,
    )
    read_data = await read_response.get_json()
    assert read_data["status"] == "ok"
    assert "# Demo" in read_data["data"]["content"]

    update_response = await test_client.put(
        "/api/v1/skills/demo_skill/files/SKILL.md",
        content="# Updated\n",
        headers={**authenticated_header, "Content-Type": "text/plain; charset=utf-8"},
    )
    update_data = await update_response.get_json()
    assert update_data["status"] == "ok"
    assert skill_md.read_text(encoding="utf-8") == "# Updated\n"

    traversal_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/..%2Foutside.txt",
        headers=authenticated_header,
    )
    traversal_data = await traversal_response.get_json()
    assert traversal_data["status"] == "error"

    symlink_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/outside-link.txt",
        headers=authenticated_header,
    )
    symlink_data = await symlink_response.get_json()
    assert symlink_data["status"] == "error"

    large_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/large.md",
        headers=authenticated_header,
    )
    large_data = await large_response.get_json()
    assert large_data["status"] == "error"
    assert large_data["message"] == "File is too large"

    binary_response = await test_client.get(
        "/api/v1/skills/demo_skill/files/binary.md",
        headers=authenticated_header,
    )
    binary_data = await binary_response.get_json()
    assert binary_data["status"] == "error"
    assert binary_data["message"] == "File is not valid UTF-8 text"
