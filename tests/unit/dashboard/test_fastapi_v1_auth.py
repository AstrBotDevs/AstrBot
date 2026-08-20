from __future__ import annotations

import pytest

from tests.unit.dashboard.fastapi_v1_support import *  # noqa: F403


def test_dashboard_uses_the_runtime_log_broker(
    fake_core_lifecycle,
    fake_db: FakeDb,
):
    """Dashboard logs must use the explicit completed-runtime dependency."""
    app = create_dashboard_asgi_app(
        runtime=fake_core_lifecycle,
        core_control=SimpleNamespace(),
        db=fake_db,
        jwt_secret=JWT_SECRET,
    )

    assert app.state.services.logs.log_broker is fake_core_lifecycle.log_broker


@pytest.mark.asyncio
async def test_dashboard_shutdown_owns_update_service(asgi_app: FastAPI, monkeypatch):
    update_shutdown = AsyncMock()
    page_shutdown = AsyncMock()
    ticket_shutdown = AsyncMock()
    monkeypatch.setattr(asgi_app.state.services.updates, "shutdown", update_shutdown)
    monkeypatch.setattr(
        asgi_app.state.services.plugin_page_sessions,
        "shutdown",
        page_shutdown,
    )
    monkeypatch.setattr(
        asgi_app.state.services.plugin_file_tickets,
        "shutdown",
        ticket_shutdown,
    )

    for handler in asgi_app.router.on_shutdown:
        await handler()

    update_shutdown.assert_awaited_once()
    page_shutdown.assert_awaited_once()
    ticket_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_versions_route_uses_static_folder(
    fake_core_lifecycle,
    fake_db: FakeDb,
    tmp_path: Path,
):
    static_folder = tmp_path / "dist"
    assets_folder = static_folder / "assets"
    assets_folder.mkdir(parents=True)
    (static_folder / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (assets_folder / "version").write_text("v9.8.7", encoding="utf-8")

    app = create_dashboard_asgi_app(
        runtime=fake_core_lifecycle,
        core_control=fake_core_lifecycle,
        db=fake_db,
        jwt_secret=JWT_SECRET,
        static_folder=str(static_folder),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/stats/versions")

    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert data["data"]["webui_version"] == "v9.8.7"
    assert data["data"]["astrbot_version"]
    assert "astrbot_code_version" in data["data"]


@pytest.mark.asyncio
async def test_dashboard_unhandled_errors_use_the_standard_error_envelope(
    asgi_app: FastAPI,
):
    handler = asgi_app.exception_handlers[Exception]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/test-unhandled-error",
            "headers": [],
        }
    )
    response = await handler(request, RuntimeError("api_key=secret-value"))

    assert response.status_code == 500
    assert json.loads(response.body) == {
        "status": "error",
        "message": "Internal server error",
    }


@pytest.mark.asyncio
async def test_v1_scope_dependencies_accept_dashboard_cookie(
    asgi_client: httpx.AsyncClient,
):
    token = DashboardTokenValidator(JWT_SECRET).issue(
        "fastapi-v1-cookie-test",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}={token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["data"]["bots"], list)


@pytest.mark.asyncio
async def test_accountless_dashboard_session_is_rejected(
    asgi_client: httpx.AsyncClient,
):
    token = DashboardTokenValidator(JWT_SECRET).issue("legacy-dashboard-user")

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legacy_dashboard_token_without_required_claims_is_rejected(
    asgi_client: httpx.AsyncClient,
):
    token = jwt.encode(
        {"username": "legacy-dashboard-user"},
        JWT_SECRET,
        algorithm="HS256",
    )

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("token_type", "wrong-token-type"),
        ("aud", "wrong-audience"),
        ("iss", "urn:astrbot:dashboard:wrong-instance"),
        ("sid", ""),
        ("jti", ""),
        ("sub", "different-user"),
    ],
)
async def test_dashboard_session_claim_mismatch_is_rejected(
    asgi_client: httpx.AsyncClient,
    claim: str,
    value: str,
):
    validator = DashboardTokenValidator(JWT_SECRET)
    payload = jwt.decode(
        validator.issue("fastapi-v1-test", account_id=TEST_DASHBOARD_ACCOUNT_ID),
        options={"verify_signature": False},
    )
    payload[claim] = value
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_claim",
    ["exp", "iat", "iss", "aud", "sub", "username", "sid", "jti", "token_type"],
)
async def test_dashboard_session_missing_required_claim_is_rejected(
    asgi_client: httpx.AsyncClient,
    missing_claim: str,
):
    validator = DashboardTokenValidator(JWT_SECRET)
    payload = jwt.decode(
        validator.issue("fastapi-v1-test", account_id=TEST_DASHBOARD_ACCOUNT_ID),
        options={"verify_signature": False},
    )
    del payload[missing_claim]
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    response = await asgi_client.get(
        "/api/v1/bots",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_each_dashboard_login_token_has_a_distinct_session_id(asgi_app: FastAPI):
    validator = asgi_app.state.dashboard_token_validator

    first = validator.validate(
        validator.issue("dashboard-user", account_id=TEST_DASHBOARD_ACCOUNT_ID)
    )
    second = validator.validate(
        validator.issue("dashboard-user", account_id=TEST_DASHBOARD_ACCOUNT_ID)
    )

    assert first.sid != second.sid
    assert first.jti != second.jti


@pytest.mark.asyncio
async def test_cookie_authenticated_mutation_rejects_untrusted_origins(
    asgi_client: httpx.AsyncClient,
):
    token = DashboardTokenValidator(JWT_SECRET).issue(
        "cookie-user",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )
    cookie = {"Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}={token}"}

    missing = await asgi_client.post("/api/v1/auth/logout", headers=cookie)
    opaque = await asgi_client.post(
        "/api/v1/auth/logout",
        headers={**cookie, "Origin": "null"},
    )
    cross_site = await asgi_client.post(
        "/api/v1/auth/logout",
        headers={**cookie, "Origin": "https://attacker.example"},
    )
    same_origin = await asgi_client.post(
        "/api/v1/auth/logout",
        headers={**cookie, "Origin": "http://testserver"},
    )

    assert missing.status_code == 403
    assert opaque.status_code == 403
    assert cross_site.status_code == 403
    assert same_origin.status_code == 200
    set_cookie_headers = same_origin.headers.get_list("set-cookie")
    assert any("Path=/api/v1" in header for header in set_cookie_headers)
    assert any("Path=/" in header for header in set_cookie_headers)


@pytest.mark.asyncio
async def test_logout_ignores_invalid_cookie_and_still_clears_it(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}=invalid"},
    )

    assert response.status_code == 200
    assert len(response.headers.get_list("set-cookie")) == 2


@pytest.mark.asyncio
async def test_cookie_csrf_uses_trusted_proxy_external_origin(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
):
    astrbot_config = asgi_app.state.astrbot_config
    previous_dashboard_config = astrbot_config.get("dashboard")
    astrbot_config["dashboard"] = {"trust_proxy_headers": True}
    token = DashboardTokenValidator(JWT_SECRET).issue(
        "proxy-user",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )
    try:
        response = await asgi_client.post(
            "/api/v1/auth/logout",
            headers={
                "Cookie": f"{DASHBOARD_JWT_COOKIE_NAME}={token}",
                "Origin": "https://dashboard.example",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "dashboard.example",
            },
        )
    finally:
        if previous_dashboard_config is None:
            del astrbot_config["dashboard"]
        else:
            astrbot_config["dashboard"] = previous_dashboard_config

    assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_v1_openapi_is_served_by_fastapi(asgi_client: httpx.AsyncClient):
    response = await asgi_client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.")
    assert all(path.startswith("/api/v1/") for path in spec["paths"])
    assert "/api/v1/bots" in spec["paths"]
    assert "/api/v1/providers" in spec["paths"]
    assert "/api/v1/plugins" in spec["paths"]
    plugin_dashboard_paths = [
        "/api/v1/plugins/{extension_id}/dashboard",
        "/api/v1/plugins/{extension_id}/dashboard/pages/{page_id}/session",
        "/api/v1/plugins/{extension_id}/dashboard/actions/{action_id}",
        "/api/v1/plugins/{extension_id}/dashboard/uploads/{action_id}",
        "/api/v1/plugins/{extension_id}/dashboard/files/{action_id}",
    ]
    for path in plugin_dashboard_paths:
        assert path in spec["paths"]
        operation = next(iter(spec["paths"][path].values()))
        assert operation["security"] == [
            {"DashboardBearerAuth": [], "DashboardCookieAuth": []}
        ]
    assert (
        spec["components"]["securitySchemes"]["DashboardBearerAuth"]["scheme"]
        == "bearer"
    )
    assert spec["components"]["securitySchemes"]["DashboardCookieAuth"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "astrbot_dashboard_jwt",
    }
    assert not any("/api/plugin-pages/" in path for path in spec["paths"])
    assert not any("/api/plugin-files/" in path for path in spec["paths"])
    session_operation = spec["paths"][plugin_dashboard_paths[1]]["post"]
    file_operation = spec["paths"][plugin_dashboard_paths[4]]["post"]
    assert "Set-Cookie" in session_operation["responses"]["200"]["headers"]
    assert "Set-Cookie" in file_operation["responses"]["200"]["headers"]
    upload_operation = spec["paths"][plugin_dashboard_paths[3]]["post"]
    upload_schema = upload_operation["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]
    assert upload_schema["required"] == ["metadata", "file"]
    assert "/api/v1/conversations" in spec["paths"]
    assert "/api/v1/mcp/servers" in spec["paths"]
    assert "/api/v1/skills" in spec["paths"]
    assert "/api/v1/file" in spec["paths"]
    assert "/api/v1/plugins/by-id" not in spec["paths"]
    assert "/api/v1/plugins/config" not in spec["paths"]
    assert "/api/v1/plugins/config/schema" not in spec["paths"]
    assert "/api/v1/plugins/config-files" not in spec["paths"]
    assert "/api/v1/plugins/readme" not in spec["paths"]
    assert "/api/v1/plugins/changelog" not in spec["paths"]
    assert "/api/v1/plugins/reload" not in spec["paths"]
    assert "/api/v1/plugins/enabled" not in spec["paths"]
    assert "/api/v1/plugins/version-support/check" not in spec["paths"]
    assert "/api/v1/plugins/validate/repo" not in spec["paths"]
    assert "/api/v1/plugin-sources/by-id" not in spec["paths"]
    assert "/api/v1/mcp/servers/by-name" not in spec["paths"]
    assert "/api/v1/mcp/servers/enabled" not in spec["paths"]
    assert "/api/v1/mcp/servers/test" not in spec["paths"]
    assert "/api/v1/skills/by-name" not in spec["paths"]
    assert "/api/v1/skills/archive" not in spec["paths"]
    assert "/api/v1/skills/files" not in spec["paths"]
    assert "/api/v1/skills/file" not in spec["paths"]
    assert "/api/v1/personas/by-id" not in spec["paths"]


def test_static_openapi_v1_paths_include_api_version():
    spec_path = Path(__file__).resolve().parents[3] / "openspec" / "openapi-v1.yaml"
    in_paths = False
    path_keys = []
    for line in spec_path.read_text(encoding="utf-8").splitlines():
        if line == "paths:":
            in_paths = True
            continue
        if line == "components:":
            in_paths = False
        if in_paths and line.startswith("  /") and line.endswith(":"):
            path_keys.append(line.strip()[:-1])

    assert path_keys
    assert all(path.startswith("/api/v1/") for path in path_keys)


@pytest.mark.asyncio
async def test_dashboard_static_dist_files_are_served(
    fake_core_lifecycle,
    fake_db: FakeDb,
    tmp_path: Path,
):
    static_folder = tmp_path / "dist"
    assets_folder = static_folder / "assets"
    assets_folder.mkdir(parents=True)
    (static_folder / "index.html").write_text(
        '<script type="module" src="/assets/index-demo.js"></script>',
        encoding="utf-8",
    )
    (static_folder / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (assets_folder / "index-demo.js").write_text(
        "window.__astrbotStaticTest = true;",
        encoding="utf-8",
    )
    (tmp_path / "secret.txt").write_text("outside static root", encoding="utf-8")

    app = create_dashboard_asgi_app(
        runtime=fake_core_lifecycle,
        core_control=fake_core_lifecycle,
        db=fake_db,
        jwt_secret=JWT_SECRET,
        static_folder=str(static_folder),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        asset_response = await client.get("/assets/index-demo.js")
        favicon_response = await client.get("/favicon.svg")
        page_response = await client.get("/config")
        missing_response = await client.get("/assets/missing.js")
        traversal_response = await client.get("/assets/%2E%2E/%2E%2E/secret.txt")
        api_response = await client.get("/api/not-found")

    assert asset_response.status_code == 200
    assert "window.__astrbotStaticTest" in asset_response.text
    assert favicon_response.status_code == 200
    assert favicon_response.text == "<svg></svg>"
    assert page_response.status_code == 200
    assert "/assets/index-demo.js" in page_response.text
    assert missing_response.status_code == 404
    assert traversal_response.status_code == 404
    assert api_response.status_code == 404


@pytest.mark.asyncio
async def test_v1_backup_path_rejects_traversal(asgi_client: httpx.AsyncClient):
    download_response = await asgi_client.get(
        "/api/v1/backups/%2E%2E/secret.zip",
        headers=_jwt_headers(),
    )
    delete_response = await asgi_client.delete(
        "/api/v1/backups/%2E%2E/secret.zip",
        headers=_jwt_headers(),
    )

    assert download_response.status_code == 200
    assert delete_response.status_code == 200
    assert download_response.json()["status"] == "error"
    assert delete_response.json()["status"] == "error"
    assert "非法路径" in download_response.json()["message"]
    assert "非法路径" in delete_response.json()["message"]


@pytest.mark.asyncio
async def test_v1_backup_download_requires_authorized_dashboard_bearer(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    tmp_path: Path,
):
    service = asgi_app.state.services.backups
    service.backup_dir = str(tmp_path)
    (tmp_path / "backup.zip").write_bytes(b"backup")
    valid_token = DashboardTokenValidator(JWT_SECRET).issue(
        "backup-user",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )

    bearer = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": f"bEaReR    {valid_token}"},
    )
    query_token = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        params={"token": valid_token},
    )

    assert bearer.status_code == 200
    assert bearer.content == b"backup"
    assert query_token.status_code == 401


@pytest.mark.asyncio
async def test_v1_backup_download_rejects_non_dashboard_credentials(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    tmp_path: Path,
):
    service = asgi_app.state.services.backups
    service.backup_dir = str(tmp_path)
    (tmp_path / "backup.zip").write_bytes(b"backup")
    valid_token = DashboardTokenValidator(JWT_SECRET).issue(
        "backup-user",
        account_id=TEST_DASHBOARD_ACCOUNT_ID,
    )
    expired_payload = jwt.decode(valid_token, options={"verify_signature": False})
    expired_payload["exp"] = 0
    expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm="HS256")

    empty_credentials = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": "Bearer    "},
    )
    wrong_scheme = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": f"ApiKey {valid_token}"},
    )
    expired = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    forged = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers={"Authorization": f"Bearer {valid_token}forged"},
    )

    assert empty_credentials.status_code == 401
    assert expired.status_code == 401
    # A malformed Dashboard bearer is checked as a legacy raw API-key input
    # only after JWT validation fails. Neither it nor an explicit API Key can
    # carry the Dashboard-only `system` capability.
    assert forged.status_code == 403
    assert wrong_scheme.status_code == 403


@pytest.mark.asyncio
async def test_v1_backup_download_rejects_missing_authorization_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
    tmp_path: Path,
):
    """Backup archives cannot bypass an unavailable authorization runtime."""

    service = asgi_app.state.services.backups
    service.backup_dir = str(tmp_path)
    (tmp_path / "backup.zip").write_bytes(b"backup")
    asgi_app.state.runtime.services.authorization = None

    response = await asgi_client.get(
        "/api/v1/backups/backup.zip",
        headers=_jwt_headers(),
    )

    assert response.status_code == 503
    assert response.json()["message"] == "Authorization unavailable"


@pytest.mark.asyncio
async def test_v1_openapi_uses_pydantic_request_bodies(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    spec = response.json()
    schemas = spec["components"]["schemas"]
    assert "BotRegistrationRequest" in schemas
    assert "BotActionRequest" in schemas
    assert "ConfigContentRequest" in schemas

    bot_registration = spec["paths"]["/api/v1/bot-types/{bot_type}/registration"][
        "post"
    ]
    assert bot_registration["parameters"][0]["name"] == "bot_type"
    assert bot_registration["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/BotRegistrationRequest")

    bot_action = spec["paths"]["/api/v1/bots/{bot_id}/actions"]["post"]
    assert bot_action["parameters"][0]["name"] == "bot_id"
    assert bot_action["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/BotActionRequest")

    config_profile_update = spec["paths"]["/api/v1/config-profiles/{config_id}"]["put"]
    assert config_profile_update["requestBody"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/ConfigContentRequest")

    system_config_update = spec["paths"]["/api/v1/system-config"]["put"]
    assert system_config_update["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ConfigContentRequest")

    open_api_file_upload = spec["paths"]["/api/v1/file"]["post"]
    assert open_api_file_upload["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]["$ref"].endswith("/Body_uploadOpenApiFile")
    assert open_api_file_upload["x-astrbot-scope"] == "file"


@pytest.mark.asyncio
async def test_v1_knowledge_base_create_validation_uses_api_error_shape(
    asgi_client: httpx.AsyncClient,
):
    headers = _jwt_headers()

    missing_name_response = await asgi_client.post(
        "/api/v1/knowledge-bases",
        json={"embedding_provider_id": "embedding-1"},
        headers=headers,
    )
    missing_provider_response = await asgi_client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Docs"},
        headers=headers,
    )

    assert missing_name_response.status_code == 200
    assert missing_name_response.json()["status"] == "error"
    assert missing_name_response.json()["message"] == "知识库名称不能为空"
    assert missing_provider_response.status_code == 200
    assert missing_provider_response.json()["status"] == "error"
    assert (
        missing_provider_response.json()["message"] == "缺少参数 embedding_provider_id"
    )


@pytest.mark.asyncio
async def test_v1_conversation_path_id_allows_slash(asgi_client: httpx.AsyncClient):
    response = await asgi_client.get(
        "/api/v1/conversations/conversation%2Fwith%2Fslash",
        params={"user_id": "webchat:FriendMessage:webchat!user!session-1"},
        headers=_jwt_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["cid"] == "conversation/with/slash"


@pytest.mark.asyncio
async def test_v1_conversation_detail_requires_user_id(
    asgi_client: httpx.AsyncClient,
):
    response = await asgi_client.get(
        "/api/v1/conversations/conversation%2Fwith%2Fslash",
        headers=_jwt_headers(),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_conversation_export_rejects_missing_authorization_service(
    asgi_app: FastAPI,
    asgi_client: httpx.AsyncClient,
):
    """A valid Dashboard JWT must not bypass unavailable authorization."""

    asgi_app.state.runtime.services.authorization = None

    response = await asgi_client.post(
        "/api/v1/conversations/export",
        json={"conversations": []},
        headers=_jwt_headers(),
    )

    assert response.status_code == 503
    assert response.json()["message"] == "Authorization unavailable"
