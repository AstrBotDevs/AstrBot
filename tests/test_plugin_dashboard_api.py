import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict

from astrbot.core.star.dashboard_extension import (
    DashboardActionError,
    DashboardExtensionRegistry,
    DashboardFile,
    DashboardFileAction,
    DashboardJsonAction,
    DashboardUploadAction,
    validate_dashboard_manifest,
)
from astrbot.core.star.star import StarMetadata
from astrbot.dashboard.api.auth import router as auth_router
from astrbot.dashboard.api.plugin_dashboard import router as plugin_dashboard_router
from astrbot.dashboard.api.plugin_files import router as plugin_files_router
from astrbot.dashboard.api.plugin_page_assets import router as plugin_page_assets_router
from astrbot.dashboard.api.plugins import router as plugins_router
from astrbot.dashboard.api.router import build_api_router
from astrbot.dashboard.responses import ApiError, error
from astrbot.dashboard.services.auth_service import (
    DASHBOARD_JWT_COOKIE_NAME,
    DashboardTokenValidator,
)
from astrbot.dashboard.services.plugin_dashboard_service import PluginDashboardService
from astrbot.dashboard.services.plugin_file_ticket_service import (
    PluginFileTicketService,
)
from astrbot.dashboard.services.plugin_page_session_service import (
    PluginPageSessionService,
)

JWT_SECRET = "plugin-dashboard-api-secret-with-32-bytes"
EXTENSION_ID = "io.github.example.palette"


class ReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str


class ReadResult(BaseModel):
    value: str


class UploadFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str


class UploadResult(BaseModel):
    filename: str
    size: int
    label: str


class FileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class _AuthorizationServiceStub:
    """Explicit trusted authorization double for extension dispatcher tests."""

    def __init__(self) -> None:
        self.actions: list[str] = []
        self.allowed = True

    async def authorize(self, _subject, action, _resource, _context):
        self.actions.append(action)
        return SimpleNamespace(
            allowed=self.allowed,
            requires_step_up=False,
        )


def _write_asset(root: Path, relative: str, content: bytes) -> dict:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": relative,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


async def _registered_extension(tmp_path: Path):
    assets = [
        _write_asset(tmp_path, "pages/settings/app.js", b"export default 1;\n"),
        _write_asset(tmp_path, "pages/settings/style.css", b"body { color: red; }"),
    ]
    manifest_path = tmp_path / "pages/settings/assets.v1.json"
    manifest_path.write_text(
        json.dumps({"version": 1, "files": assets}),
        encoding="utf-8",
    )
    (tmp_path / "download.txt").write_text("download-content", encoding="utf-8")
    manifest = validate_dashboard_manifest(
        {
            "name": "astrbot_plugin_palette",
            "requires": {"dashboard_extension": 1},
            "dashboard": {
                "extension_id": EXTENSION_ID,
                "pages": [
                    {
                        "id": "settings",
                        "title": "Settings",
                        "module": "pages/settings/app.js",
                        "assets_manifest": "pages/settings/assets.v1.json",
                        "styles": ["pages/settings/style.css"],
                        "icon": "mdi-palette",
                        "actions": [
                            "config.read",
                            "config.fail",
                            "config.crash",
                            "image.upload",
                            "file.download",
                        ],
                    }
                ],
            },
        },
        tmp_path,
    )

    async def read_handler(payload, _context):
        return ReadResult(value=f"value:{payload.key}")

    async def fail_handler(_payload, _context):
        raise DashboardActionError("not_ready", "Palette is not ready")

    async def crash_handler(_payload, _context):
        raise RuntimeError("provider=https://secret.example token=secret")

    async def upload_handler(file, fields, _context):
        received = b"".join([chunk async for chunk in file.iter_chunks()])
        return UploadResult(
            filename=file.filename,
            size=len(received),
            label=fields.label,
        )

    async def file_handler(payload, _context):
        return DashboardFile(Path("download.txt"), filename=payload.name)

    owner = object()
    metadata = StarMetadata(
        name="astrbot_plugin_palette",
        root_dir_name="astrbot_plugin_palette",
        star_cls=owner,  # type: ignore[arg-type]
        dashboard=manifest,
        dashboard_root=tmp_path.resolve(),
    )
    registry = DashboardExtensionRegistry()
    registry.begin_registration(metadata, owner)  # type: ignore[arg-type]
    registrar = registry.registrar_for(owner)  # type: ignore[arg-type]
    registrar.register_json(
        DashboardJsonAction(
            name="config.read",
            input_model=ReadRequest,
            output_model=ReadResult,
        ),
        read_handler,
    )
    registrar.register_json(
        DashboardJsonAction(
            name="config.fail",
            input_model=ReadRequest,
            output_model=ReadResult,
        ),
        fail_handler,
    )
    registrar.register_json(
        DashboardJsonAction(
            name="config.crash",
            input_model=ReadRequest,
            output_model=ReadResult,
        ),
        crash_handler,
    )
    registrar.register_upload(
        DashboardUploadAction(
            name="image.upload",
            fields_model=UploadFields,
            output_model=UploadResult,
            allowed_content_types=frozenset({"image/png"}),
            allowed_extensions=frozenset({".png"}),
        ),
        upload_handler,
    )
    registrar.register_file(
        DashboardFileAction(
            name="file.download",
            input_model=FileRequest,
            disposition="attachment",
            allowed_content_types=frozenset({"text/plain"}),
        ),
        file_handler,
    )
    snapshot = await registry.commit_registration(owner)  # type: ignore[arg-type]
    assert snapshot is not None
    return registry, snapshot


@pytest_asyncio.fixture
async def plugin_api(tmp_path: Path):
    registry, snapshot = await _registered_extension(tmp_path)
    validator = DashboardTokenValidator(JWT_SECRET)
    page_sessions = PluginPageSessionService(registry, JWT_SECRET)
    file_tickets = PluginFileTicketService(registry, JWT_SECRET)
    dashboard = PluginDashboardService(registry, page_sessions, file_tickets)
    auth = SimpleNamespace(discard_totp_rotation=AsyncMock())
    authorization = _AuthorizationServiceStub()
    app = FastAPI()
    app.state.dashboard_token_validator = validator
    app.state.dashboard_config = {}
    app.state.dashboard_testing = True
    app.state.services = SimpleNamespace(
        plugin_dashboard=dashboard,
        plugin_page_sessions=page_sessions,
        plugin_file_tickets=file_tickets,
        auth=auth,
    )
    app.state.runtime = SimpleNamespace(
        services=SimpleNamespace(authorization=authorization),
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        return JSONResponse(
            error(exc.message, exc.data),
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, _exc: RequestValidationError):
        return JSONResponse(error("Invalid request payload"), status_code=422)

    api = APIRouter(prefix="/api/v1")
    api.include_router(plugin_dashboard_router)
    api.include_router(auth_router)
    app.include_router(api)
    app.include_router(plugin_page_assets_router)
    app.include_router(plugin_files_router)

    @app.get("/{path:path}")
    async def static_catch_all(path: str):
        return PlainTextResponse(f"static:{path}")

    token = validator.issue("astrbot")
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )
    client.cookies.set(
        DASHBOARD_JWT_COOKIE_NAME,
        token,
        domain="testserver.local",
        path="/api/v1",
    )
    yield SimpleNamespace(
        app=app,
        client=client,
        token=token,
        validator=validator,
        snapshot=snapshot,
        page_sessions=page_sessions,
        file_tickets=file_tickets,
        auth=auth,
        authorization=authorization,
    )
    await client.aclose()
    await page_sessions.shutdown()
    await file_tickets.shutdown()


def _headers(token: str, *, origin: str = "http://testserver") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Origin": origin}


async def _create_session(plugin_api):
    response = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/pages/settings/session",
        json={
            "protocol_version": 1,
            "expected_generation": plugin_api.snapshot.generation,
        },
        headers=_headers(plugin_api.token),
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_control_plane_requires_matching_bearer_and_cookie(plugin_api):
    path = f"/api/v1/plugins/{EXTENSION_ID}/dashboard"
    valid = await plugin_api.client.get(path, headers=_headers(plugin_api.token))
    assert valid.status_code == 200
    assert valid.json()["data"]["plugin_generation"] == plugin_api.snapshot.generation

    plugin_api.client.cookies.clear()
    bearer_only = await plugin_api.client.get(path, headers=_headers(plugin_api.token))
    assert bearer_only.status_code == 401

    other = plugin_api.validator.issue("astrbot")
    plugin_api.client.cookies.set(
        DASHBOARD_JWT_COOKIE_NAME,
        other,
        domain="testserver.local",
        path="/api/v1",
    )
    mismatch = await plugin_api.client.get(path, headers=_headers(plugin_api.token))
    assert mismatch.status_code == 401
    api_key = await plugin_api.client.get(
        path,
        headers={"Authorization": "ApiKey secret"},
    )
    assert api_key.status_code == 401


@pytest.mark.asyncio
async def test_control_plane_uses_runtime_authorization_service(plugin_api):
    catalog_path = f"/api/v1/plugins/{EXTENSION_ID}/dashboard"
    catalog = await plugin_api.client.get(
        catalog_path,
        headers=_headers(plugin_api.token),
    )
    assert catalog.status_code == 200
    assert plugin_api.authorization.actions == ["extension.read"]

    session = await _create_session(plugin_api)
    action = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/actions/config.read",
        json={
            "protocol_version": 1,
            "instance_id": session["instance_id"],
            "expected_generation": plugin_api.snapshot.generation,
            "payload": {"key": "theme"},
        },
        headers=_headers(plugin_api.token),
    )
    assert action.status_code == 200
    assert plugin_api.authorization.actions[-2:] == [
        "extension.read",
        "extension.manage",
    ]

    plugin_api.authorization.allowed = False
    denied = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/actions/config.read",
        json={
            "protocol_version": 1,
            "instance_id": session["instance_id"],
            "expected_generation": plugin_api.snapshot.generation,
            "payload": {"key": "theme"},
        },
        headers=_headers(plugin_api.token),
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_control_plane_fails_closed_without_authorization_service(plugin_api):
    plugin_api.app.state.runtime.services.authorization = None

    response = await plugin_api.client.get(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard",
        headers=_headers(plugin_api.token),
    )

    assert response.status_code == 503
    assert response.json()["message"] == "Authorization unavailable"


@pytest.mark.asyncio
async def test_control_plane_fails_closed_for_mismatched_dashboard_protocol(
    plugin_api,
    tmp_path: Path,
):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "plugin-ui-protocol").write_text("2", encoding="utf-8")
    plugin_api.app.state.dashboard_static_folder = str(tmp_path)
    path = f"/api/v1/plugins/{EXTENSION_ID}/dashboard"

    mismatch = await plugin_api.client.get(
        path,
        headers=_headers(plugin_api.token),
    )
    assert mismatch.status_code == 503
    assert "rebuild or replace" in mismatch.json()["message"]

    (assets / "plugin-ui-protocol").write_text("1", encoding="utf-8")
    compatible = await plugin_api.client.get(
        path,
        headers=_headers(plugin_api.token),
    )
    assert compatible.status_code == 200


@pytest.mark.asyncio
async def test_page_session_shell_and_public_bundle_contract(plugin_api):
    data = await _create_session(plugin_api)
    assert data["protocol_version"] == 1
    assert data["iframe_url"].startswith("/api/plugin-pages/v1/sessions/")

    shell = await plugin_api.client.get(data["iframe_url"])
    assert shell.status_code == 200
    assert "sandbox allow-scripts" in shell.headers["content-security-policy"]
    assert 'crossorigin="anonymous"' in shell.text
    bundle_path = re.search(
        r"(/api/plugin-pages/v1/bundles/[0-9a-f]{64}/pages/settings/app\.js)",
        shell.text,
    ).group(1)
    asset = await plugin_api.client.get(bundle_path, headers={"Origin": "null"})
    assert asset.status_code == 200
    assert asset.headers["access-control-allow-origin"] == "null"
    assert "immutable" in asset.headers["cache-control"]
    with_cookie = await plugin_api.client.get(
        bundle_path,
        headers={"Origin": "null", "Cookie": "unexpected=value"},
    )
    assert with_cookie.status_code == 403
    traversal = await plugin_api.client.get(
        bundle_path.rsplit("/", 1)[0] + "/%2e%2e/app.js",
        headers={"Origin": "null"},
    )
    assert traversal.status_code == 404


@pytest.mark.asyncio
async def test_json_action_validates_instance_generation_kind_and_schema(plugin_api):
    session = await _create_session(plugin_api)
    path = f"/api/v1/plugins/{EXTENSION_ID}/dashboard/actions/config.read"
    payload = {
        "protocol_version": 1,
        "instance_id": session["instance_id"],
        "expected_generation": plugin_api.snapshot.generation,
        "payload": {"key": "theme"},
    }
    response = await plugin_api.client.post(
        path,
        json=payload,
        headers=_headers(plugin_api.token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"value": "value:theme"}

    unknown = await plugin_api.client.post(
        path,
        json={**payload, "unknown": True},
        headers=_headers(plugin_api.token),
    )
    assert unknown.status_code == 422
    stale = await plugin_api.client.post(
        path,
        json={**payload, "expected_generation": "stale"},
        headers=_headers(plugin_api.token),
    )
    assert stale.status_code == 409
    wrong_kind = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/actions/file.download",
        json={**payload, "payload": {"name": "report.txt"}},
        headers=_headers(plugin_api.token),
    )
    assert wrong_kind.status_code == 409


@pytest.mark.asyncio
async def test_action_errors_keep_public_and_internal_boundaries(plugin_api, caplog):
    session = await _create_session(plugin_api)
    wrapper = {
        "protocol_version": 1,
        "instance_id": session["instance_id"],
        "expected_generation": plugin_api.snapshot.generation,
        "payload": {"key": "theme"},
    }
    public = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/actions/config.fail",
        json=wrapper,
        headers=_headers(plugin_api.token),
    )
    assert public.status_code == 400
    assert public.json()["message"] == "Palette is not ready"
    assert public.json()["data"]["code"] == "not_ready"
    assert public.json()["data"]["request_id"]

    internal = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/actions/config.crash",
        json=wrapper,
        headers=_headers(plugin_api.token),
    )
    assert internal.status_code == 500
    assert internal.json()["message"] == "Plugin operation failed"
    serialized = json.dumps(internal.json())
    assert "secret.example" not in serialized
    assert "token=secret" not in serialized
    assert "secret.example" not in caplog.text
    assert "token=secret" not in caplog.text


@pytest.mark.asyncio
async def test_page_session_rate_limit_has_retry_after(plugin_api):
    responses = []
    for _index in range(6):
        responses.append(
            await plugin_api.client.post(
                f"/api/v1/plugins/{EXTENSION_ID}/dashboard/pages/settings/session",
                json={
                    "protocol_version": 1,
                    "expected_generation": plugin_api.snapshot.generation,
                },
                headers=_headers(plugin_api.token),
            )
        )
    assert [response.status_code for response in responses[:5]] == [200] * 5
    assert responses[5].status_code == 429
    assert int(responses[5].headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_upload_action_uses_strict_two_part_multipart(plugin_api):
    session = await _create_session(plugin_api)
    metadata = {
        "protocol_version": 1,
        "instance_id": session["instance_id"],
        "expected_generation": plugin_api.snapshot.generation,
        "fields": {"label": "background"},
    }
    response = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/uploads/image.upload",
        files=[
            (
                "metadata",
                ("metadata.json", json.dumps(metadata), "application/json"),
            ),
            (
                "file",
                ("background.png", b"\x89PNG\r\n\x1a\ncontent", "image/png"),
            ),
        ],
        headers=_headers(plugin_api.token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "filename": "background.png",
        "size": 15,
        "label": "background",
    }
    invalid = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/uploads/image.upload",
        files=[("file", ("background.png", b"data", "image/png"))],
        headers=_headers(plugin_api.token),
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_file_ticket_streams_once_and_clears_cookie(plugin_api):
    session = await _create_session(plugin_api)
    response = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/files/file.download",
        json={
            "protocol_version": 1,
            "instance_id": session["instance_id"],
            "expected_generation": plugin_api.snapshot.generation,
            "expected_disposition": "attachment",
            "payload": {"name": "report.txt"},
        },
        headers=_headers(plugin_api.token),
    )
    assert response.status_code == 200
    ticket_url = response.json()["data"]["ticket_url"]
    downloaded = await plugin_api.client.get(ticket_url)
    assert downloaded.status_code == 200
    assert downloaded.content == b"download-content"
    assert downloaded.headers["accept-ranges"] == "none"
    assert "attachment" in downloaded.headers["content-disposition"]
    replay = await plugin_api.client.get(ticket_url)
    assert replay.status_code in {401, 404}


@pytest.mark.asyncio
async def test_cookie_csrf_and_logout_revoke_current_sid(plugin_api):
    rejected = await plugin_api.client.post(
        f"/api/v1/plugins/{EXTENSION_ID}/dashboard/pages/settings/session",
        json={
            "protocol_version": 1,
            "expected_generation": plugin_api.snapshot.generation,
        },
        headers=_headers(plugin_api.token, origin="null"),
    )
    assert rejected.status_code == 403
    session = await _create_session(plugin_api)
    logout = await plugin_api.client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver"},
    )
    assert logout.status_code == 200
    auth = plugin_api.auth.discard_totp_rotation
    auth.assert_awaited_once()
    shell = await plugin_api.client.get(session["iframe_url"])
    assert shell.status_code in {401, 404}


def test_plugin_dashboard_router_precedes_greedy_plugin_detail_route():
    included = [route.original_router for route in build_api_router().routes]
    assert included.index(plugin_dashboard_router) < included.index(plugins_router)
