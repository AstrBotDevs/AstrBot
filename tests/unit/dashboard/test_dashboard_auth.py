from __future__ import annotations

import pytest

from tests.unit.dashboard.dashboard_lifecycle_support import *  # noqa: F403


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
