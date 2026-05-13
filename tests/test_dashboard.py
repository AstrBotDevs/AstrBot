import asyncio
import copy
import io
import os
import re
import shutil
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit, urlunsplit

import pytest
import pytest_asyncio
from quart import Quart, jsonify
from werkzeug.datastructures import FileStorage

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.star import StarMetadata, star_registry
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_legacy_dashboard_password,
    verify_dashboard_password,
)
from astrbot.core.utils.pip_installer import PipInstallError
from astrbot.dashboard.password_state import (
    get_dashboard_password_hash,
    is_password_change_required,
    is_password_storage_upgraded,
    set_password_change_required,
    set_password_storage_upgraded,
)
from astrbot.dashboard.routes.auth import DASHBOARD_JWT_COOKIE_NAME
from astrbot.dashboard.routes.plugin import PluginRoute
from astrbot.dashboard.server import AstrBotDashboard
from tests.fixtures.helpers import (
    MockPluginBuilder,
    create_mock_updater_install,
    create_mock_updater_update,
)

_TEST_DASHBOARD_PASSWORD = "AstrbotTest123"
PLUGIN_PAGE_DEMO_NAME = "astrbot_plugin_page_demo"
PLUGIN_PAGE_DEMO_PAGE_NAME = "bridge-demo"


def _strip_query(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit(("", "", parsed.path, "", parsed.fragment))


@pytest.fixture
def registered_plugin_page(core_lifecycle_td: AstrBotCoreLifecycle, monkeypatch):
    plugin_root = (
        Path(core_lifecycle_td.plugin_manager.plugin_store_path) / PLUGIN_PAGE_DEMO_NAME
    )
    page_root = plugin_root / "pages" / PLUGIN_PAGE_DEMO_PAGE_NAME
    i18n_root = plugin_root / ".astrbot-plugin" / "i18n"
    shared_root = page_root / "shared"
    images_root = page_root / "images"
    shared_root.mkdir(parents=True, exist_ok=True)
    images_root.mkdir(parents=True, exist_ok=True)
    i18n_root.mkdir(parents=True, exist_ok=True)

    (page_root / "index.html").write_text(
        """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Plugin Page Demo</title>
    <link rel="stylesheet" href="shared/base.css" />
  </head>
  <body>
    <h1>Single plugin Page with internal navigation</h1>
    <div id="app"></div>
    <script type="module" src="app.js"></script>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )
    (page_root / "app.js").write_text(
        """
import React from "react";
import "./shared/common.js";

function renderTabs() {
  return ["dashboard", "settings"];
}

window.renderTabs = renderTabs;
""".strip(),
        encoding="utf-8",
    )
    (shared_root / "common.js").write_text(
        "window.__pluginCommonLoaded = true;\n", encoding="utf-8"
    )
    (shared_root / "base.css").write_text(
        'body { background-image: url("../images/logo.svg"); }\n',
        encoding="utf-8",
    )
    (images_root / "logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>\n',
        encoding="utf-8",
    )
    (i18n_root / "zh-CN.json").write_text(
        """
{
  "metadata": {
    "display_name": "插件页面演示"
  },
  "pages": {
    "bridge-demo": {
      "title": "Bridge 演示页"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    plugin = StarMetadata(
        name=PLUGIN_PAGE_DEMO_NAME,
        author="AstrBot Test",
        desc="Plugin Page demo",
        version="1.0.0",
        display_name="Plugin Page Demo",
        root_dir_name=PLUGIN_PAGE_DEMO_NAME,
        activated=True,
    )

    monkeypatch.setattr(
        core_lifecycle_td.plugin_manager.context,
        "get_all_stars",
        lambda: [plugin],
    )

    try:
        yield plugin
    finally:
        shutil.rmtree(plugin_root, ignore_errors=True)


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    """Creates and initializes a core lifecycle instance with a temporary database."""
    tmp_db_path = tmp_path_factory.mktemp("data") / "test_data_v3.db"
    db = SQLiteDatabase(str(tmp_db_path))
    log_broker = LogBroker()
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
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
            hash_legacy_dashboard_password(dashboard_password)
        )
        await set_password_storage_upgraded(
            core_lifecycle.db,
            core_lifecycle.astrbot_config,
            True,
        )
        await set_password_change_required(
            core_lifecycle.db,
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
        # 优先停止核心生命周期以释放资源（包括关闭 MCP 等后台任务）
        try:
            _stop_res = core_lifecycle.stop()
            if asyncio.iscoroutine(_stop_res):
                await _stop_res
        except Exception:
            # 停止过程中如有异常，不影响后续清理
            pass


@pytest.fixture(scope="module")
def app(core_lifecycle_td: AstrBotCoreLifecycle):
    """Creates a Quart app instance for testing."""
    shutdown_event = asyncio.Event()
    # The db instance is already part of the core_lifecycle_td
    server = AstrBotDashboard(core_lifecycle_td, core_lifecycle_td.db, shutdown_event)
    return server.app


def _resolve_dashboard_password(core_lifecycle_td: AstrBotCoreLifecycle) -> str:
    """Return a login password compatible with both hashed and plain defaults."""
    generated_password = getattr(core_lifecycle_td, "_dashboard_plain_password", None)
    if generated_password:
        return generated_password
    password = core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"]
    if isinstance(password, str) and password.startswith("pbkdf2_sha256$"):
        return "astrbot"
    return password


async def _set_dashboard_password_change_required(
    core_lifecycle_td: AstrBotCoreLifecycle,
    required: bool,
) -> None:
    await set_password_change_required(
        core_lifecycle_td.db,
        core_lifecycle_td.astrbot_config,
        required,
    )


async def _restore_dashboard_password_state(
    core_lifecycle_td: AstrBotCoreLifecycle,
    dashboard_config: dict,
) -> None:
    core_lifecycle_td.astrbot_config["dashboard"] = dashboard_config
    await set_password_change_required(
        core_lifecycle_td.db,
        core_lifecycle_td.astrbot_config,
        False,
    )
    await set_password_storage_upgraded(
        core_lifecycle_td.db,
        core_lifecycle_td.astrbot_config,
        bool(dashboard_config.get("pbkdf2_password")),
    )


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
    assert data["status"] == "ok"
    token = data["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_auth_login(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    """Tests the login functionality with both wrong and correct credentials."""
    monkeypatch.setitem(app.config, "DASHBOARD_JWT_COOKIE_SECURE", False)

    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={"username": "wrong", "password": "password"},
    )
    data = await response.get_json()
    assert data["status"] == "error"

    response = await test_client.post(
        "/api/auth/login",
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
    assert "SameSite=Strict" in jwt_cookie_header
    assert "Secure" not in jwt_cookie_header


@pytest.mark.asyncio
async def test_auth_login_secure_cookie_override(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setitem(app.config, "DASHBOARD_JWT_COOKIE_SECURE", True)

    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
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
    assert "SameSite=Strict" in jwt_cookie_header


@pytest.mark.asyncio
async def test_legacy_md5_dashboard_password_keeps_legacy_auth_until_edit(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = app.test_client()
    legacy_password = "AstrbotLegacy123"
    changed_password = "AstrbotChanged123"

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["username"] = "astrbot"
        core_lifecycle_td.astrbot_config["dashboard"]["password"] = (
            hash_legacy_dashboard_password(legacy_password)
        )
        core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"] = ""
        await _set_dashboard_password_change_required(core_lifecycle_td, False)
        await set_password_storage_upgraded(
            core_lifecycle_td.db,
            core_lifecycle_td.astrbot_config,
            False,
        )

        response = await test_client.post(
            "/api/auth/login",
            json={"username": "astrbot", "password": legacy_password},
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["change_pwd_hint"] is False
        assert data["data"]["legacy_pwd_hint"] is True
        assert data["data"]["password_upgrade_required"] is True

        response = await test_client.post(
            "/api/auth/account/edit",
            json={
                "password": legacy_password,
                "new_password": "",
                "confirm_password": "",
                "new_username": "astrbot-admin",
            },
        )
        data = await response.get_json()
        assert data["status"] == "error"
        assert (
            await is_password_storage_upgraded(
                core_lifecycle_td.db,
                core_lifecycle_td.astrbot_config,
            )
            is False
        )

        response = await test_client.post(
            "/api/auth/account/edit",
            json={
                "password": legacy_password,
                "new_password": changed_password,
                "confirm_password": changed_password,
                "new_username": "astrbot",
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert (
            await is_password_storage_upgraded(
                core_lifecycle_td.db,
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
async def test_password_storage_flag_repairs_after_rollback_clears_pbkdf2(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = app.test_client()
    legacy_password = "AstrbotRollback123"

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["username"] = "astrbot"
        core_lifecycle_td.astrbot_config["dashboard"]["password"] = (
            hash_legacy_dashboard_password(legacy_password)
        )
        core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"] = ""
        await _set_dashboard_password_change_required(core_lifecycle_td, False)
        await set_password_storage_upgraded(
            core_lifecycle_td.db,
            core_lifecycle_td.astrbot_config,
            True,
        )

        response = await test_client.post(
            "/api/auth/login",
            json={"username": "astrbot", "password": legacy_password},
        )
        data = await response.get_json()

        assert data["status"] == "ok"
        assert data["data"]["legacy_pwd_hint"] is True
        assert data["data"]["password_upgrade_required"] is True
        assert (
            await is_password_storage_upgraded(
                core_lifecycle_td.db,
                core_lifecycle_td.astrbot_config,
            )
            is False
        )
    finally:
        await _restore_dashboard_password_state(
            core_lifecycle_td,
            original_dashboard_config,
        )


def test_password_hash_lookup_falls_back_to_legacy_when_pbkdf2_missing(
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    dashboard_config = copy.deepcopy(core_lifecycle_td.astrbot_config["dashboard"])
    legacy_hash = hash_legacy_dashboard_password("AstrbotRollback123")

    try:
        core_lifecycle_td.astrbot_config["dashboard"]["password"] = legacy_hash
        core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"] = ""

        assert (
            get_dashboard_password_hash(
                core_lifecycle_td.astrbot_config,
                upgraded=True,
            )
            == legacy_hash
        )
    finally:
        core_lifecycle_td.astrbot_config["dashboard"] = dashboard_config


@pytest.mark.asyncio
async def test_generated_password_requires_password_change_until_changed(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = app.test_client()
    changed_password = "AstrbotChanged123"

    try:
        await _set_dashboard_password_change_required(core_lifecycle_td, True)

        response = await test_client.post(
            "/api/auth/login",
            json={
                "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
                "password": _resolve_dashboard_password(core_lifecycle_td),
            },
        )
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["change_pwd_hint"] is True

        response = await test_client.post(
            "/api/auth/account/edit",
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
                core_lifecycle_td.db,
                core_lifecycle_td.astrbot_config,
            )
            is True
        )

        response = await test_client.post(
            "/api/auth/account/edit",
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
                core_lifecycle_td.db,
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
async def test_local_setup_can_skip_default_password_auth(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = app.test_client()
    setup_password = "AstrbotSetup123"
    setup_username = "astrbot-admin"

    try:
        monkeypatch.setenv("ASTRBOT_DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH", "true")
        core_lifecycle_td.astrbot_config["dashboard"]["host"] = "127.0.0.1"
        await _set_dashboard_password_change_required(core_lifecycle_td, True)

        response = await test_client.get("/api/auth/setup-status")
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["setup_required"] is True
        assert data["data"]["skip_default_password_auth"] is True

        response = await test_client.post(
            "/api/auth/setup",
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
                core_lifecycle_td.db,
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
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = app.test_client()
    setup_password = "AstrbotSetup123"
    setup_username = "astrbot-admin"

    try:
        await _set_dashboard_password_change_required(core_lifecycle_td, True)

        login_response = await test_client.post(
            "/api/auth/login",
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
            "/api/auth/setup-authenticated",
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
                core_lifecycle_td.db,
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
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch: pytest.MonkeyPatch,
):
    original_dashboard_config = copy.deepcopy(
        core_lifecycle_td.astrbot_config["dashboard"]
    )
    test_client = app.test_client()

    try:
        monkeypatch.setenv("ASTRBOT_DASHBOARD_SKIP_DEFAULT_PASSWORD_AUTH", "true")
        core_lifecycle_td.astrbot_config["dashboard"]["host"] = "0.0.0.0"
        await _set_dashboard_password_change_required(core_lifecycle_td, True)

        response = await test_client.get("/api/auth/setup-status")
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["setup_required"] is True
        assert data["data"]["skip_default_password_auth"] is False

        response = await test_client.post(
            "/api/auth/setup",
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
async def test_plugin_web_api_supports_dynamic_route(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
    authenticated_header: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    async def group_detail(name: str):
        calls.append(name)
        return jsonify({"name": name})

    monkeypatch.setattr(
        core_lifecycle_td.star_context,
        "registered_web_apis",
        [
            (
                f"/{PLUGIN_PAGE_DEMO_NAME}/groups/<name>",
                group_detail,
                ["GET"],
                "Group detail",
            ),
        ],
    )

    test_client = app.test_client()
    response = await test_client.get(
        f"/api/plug/{PLUGIN_PAGE_DEMO_NAME}/groups/example",
        headers=authenticated_header,
    )
    data = await response.get_json()

    assert response.status_code == 200
    assert data == {"name": "example"}
    assert calls == ["example"]


def test_plugin_page_content_path_escapes_plugin_name():
    assert (
        PluginRoute._build_plugin_page_content_path("plugin with space", "main page")
        == "/api/plugin/page/content/plugin%20with%20space/main%20page/"
    )
    assert (
        PluginRoute._build_plugin_page_content_path(
            "plugin with space", "main page", "assets/main file.js"
        )
        == "/api/plugin/page/content/plugin%20with%20space/main%20page/assets/main%20file.js"
    )


@pytest.mark.asyncio
async def test_plugin_get_excludes_scanned_pages(
    app: Quart,
    authenticated_header: dict,
    registered_plugin_page: StarMetadata,
):
    test_client = app.test_client()
    response = await test_client.get("/api/plugin/get", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    plugin = next(
        item for item in data["data"] if item["name"] == PLUGIN_PAGE_DEMO_NAME
    )
    assert plugin["activated"] is True
    assert "page" not in plugin
    assert "pages" not in plugin


@pytest.mark.asyncio
async def test_plugin_detail_includes_scanned_page_component(
    app: Quart,
    authenticated_header: dict,
    registered_plugin_page: StarMetadata,
):
    test_client = app.test_client()
    response = await test_client.get(
        f"/api/plugin/detail?name={PLUGIN_PAGE_DEMO_NAME}",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    page_components = [
        component
        for component in data["data"]["components"]
        if component["type"] == "page"
    ]
    assert page_components == [
        {
            "type": "page",
            "name": PLUGIN_PAGE_DEMO_PAGE_NAME,
            "title": PLUGIN_PAGE_DEMO_PAGE_NAME,
            "page_name": PLUGIN_PAGE_DEMO_PAGE_NAME,
            "i18n_key": f"pages.{PLUGIN_PAGE_DEMO_PAGE_NAME}",
            "description": "Plugin Page entry",
            "plugin_name": PLUGIN_PAGE_DEMO_NAME,
        }
    ]


@pytest.mark.asyncio
async def test_plugin_page_entry_returns_signed_content_path(
    app: Quart,
    authenticated_header: dict,
    registered_plugin_page: StarMetadata,
):
    test_client = app.test_client()
    response = await test_client.get(
        (
            f"/api/plugin/page/entry?name={PLUGIN_PAGE_DEMO_NAME}"
            f"&page={PLUGIN_PAGE_DEMO_PAGE_NAME}"
        ),
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["name"] == PLUGIN_PAGE_DEMO_PAGE_NAME
    assert data["data"]["title"] == PLUGIN_PAGE_DEMO_PAGE_NAME
    assert data["data"]["i18n_key"] == f"pages.{PLUGIN_PAGE_DEMO_PAGE_NAME}"
    assert data["data"]["content_path"].startswith(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/"
    )
    assert "asset_token=" in data["data"]["content_path"]


@pytest.mark.asyncio
async def test_plugin_page_content_requires_auth(
    app: Quart,
    registered_plugin_page: StarMetadata,
):
    test_client = app.test_client()
    response = await test_client.get(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/"
    )
    assert response.status_code == 401
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_plugin_page_content_supports_cookie_auth(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
    registered_plugin_page: StarMetadata,
):
    test_client = app.test_client()
    login_response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    assert login_response.status_code == 200

    response = await test_client.get(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/"
    )
    assert response.status_code == 200
    content = (await response.get_data()).decode("utf-8")
    assert "Single plugin Page with internal navigation" in content
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]
    assert "asset_token=" in content

    asset_url_match = re.search(
        r'src="([^"]+/app\.js[^"]*)"',
        content,
    )
    assert asset_url_match is not None
    asset_response = await test_client.get(asset_url_match.group(1))
    assert asset_response.status_code == 200
    asset_content = (await asset_response.get_data()).decode("utf-8")
    assert "renderTabs" in asset_content
    assert 'from "react"' in asset_content
    assert (
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/shared/common.js"
        in asset_content
    )
    assert "asset_token=" in asset_content

    bridge_url_match = re.search(
        r'src="([^"]+/bridge-sdk\.js[^"]*)"',
        content,
    )
    assert bridge_url_match is not None
    bridge_response = await test_client.get(bridge_url_match.group(1))
    assert bridge_response.status_code == 200
    bridge_content = (await bridge_response.get_data()).decode("utf-8")
    assert "AstrBotPluginPage" in bridge_content


@pytest.mark.asyncio
async def test_plugin_page_content_issues_scoped_asset_token(
    app: Quart,
    authenticated_header: dict,
    registered_plugin_page: StarMetadata,
):
    authorized_client = app.test_client()
    response = await authorized_client.get(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    html_text = (await response.get_data()).decode("utf-8")

    app_js_url = re.search(
        r'src="([^"]+/app\.js[^"]*)"',
        html_text,
    )
    bridge_sdk_url = re.search(
        r'src="([^"]+/bridge-sdk\.js[^"]*)"',
        html_text,
    )
    css_url = re.search(
        r'href="([^"]+/base\.css[^"]*)"',
        html_text,
    )
    assert app_js_url is not None
    assert bridge_sdk_url is not None
    assert css_url is not None
    assert "asset_token=" in app_js_url.group(1)
    assert "asset_token=" in bridge_sdk_url.group(1)
    assert "asset_token=" in css_url.group(1)

    query = parse_qs(urlsplit(app_js_url.group(1)).query)
    asset_token = query.get("asset_token", [""])[0]
    assert asset_token

    anonymous_client = app.test_client()
    app_js_response = await anonymous_client.get(app_js_url.group(1))
    assert app_js_response.status_code == 200
    bridge_response = await anonymous_client.get(bridge_sdk_url.group(1))
    assert bridge_response.status_code == 200
    bridge_js = (await bridge_response.get_data()).decode("utf-8")
    assert "window.AstrBotPluginPage?.__setInitialContext" in bridge_js
    assert '"locale": "zh-CN"' in bridge_js
    assert '"displayName": "插件页面演示"' in bridge_js
    assert '"pageTitle": "Bridge 演示页"' in bridge_js
    css_response = await anonymous_client.get(css_url.group(1))
    assert css_response.status_code == 200

    out_of_scope_response = await anonymous_client.get(
        f"/api/plugin/get?asset_token={asset_token}"
    )
    assert out_of_scope_response.status_code == 401

    cross_plugin_response = await anonymous_client.get(
        f"/api/plugin/page/content/another_plugin/{PLUGIN_PAGE_DEMO_PAGE_NAME}/app.js?asset_token={asset_token}"
    )
    assert cross_plugin_response.status_code == 401

    cross_page_response = await anonymous_client.get(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/another-page/app.js?asset_token={asset_token}"
    )
    assert cross_page_response.status_code == 401


@pytest.mark.asyncio
async def test_plugin_page_assets_require_dashboard_auth(
    app: Quart,
    authenticated_header: dict,
    registered_plugin_page: StarMetadata,
):
    authorized_client = app.test_client()
    response = await authorized_client.get(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    html_text = (await response.get_data()).decode("utf-8")

    app_js_url = re.search(
        r'src="([^"]+/app\.js[^"]*)"',
        html_text,
    )
    bridge_sdk_url = re.search(
        r'src="([^"]+/bridge-sdk\.js[^"]*)"',
        html_text,
    )
    assert app_js_url is not None
    assert bridge_sdk_url is not None

    anonymous_client = app.test_client()
    app_js_response = await anonymous_client.get(_strip_query(app_js_url.group(1)))
    assert app_js_response.status_code == 401
    bridge_response = await anonymous_client.get(_strip_query(bridge_sdk_url.group(1)))
    assert bridge_response.status_code == 401


@pytest.mark.asyncio
async def test_plugin_page_content_blocks_path_traversal(
    app: Quart,
    authenticated_header: dict,
    registered_plugin_page: StarMetadata,
):
    test_client = app.test_client()
    response = await test_client.get(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/..%2Fmain.py",
        headers=authenticated_header,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_logout_clears_cookie_for_plugin_page(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
    registered_plugin_page: StarMetadata,
):
    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    assert response.status_code == 200

    response = await test_client.get(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/"
    )
    assert response.status_code == 200
    html_text = (await response.get_data()).decode("utf-8")
    asset_url_match = re.search(r'src="([^"]+/app\.js[^"]*)"', html_text)
    assert asset_url_match is not None

    logout_response = await test_client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    clear_cookie_header = next(
        (
            value
            for value in logout_response.headers.getlist("Set-Cookie")
            if DASHBOARD_JWT_COOKIE_NAME in value
        ),
        "",
    )
    assert clear_cookie_header
    assert f"{DASHBOARD_JWT_COOKIE_NAME}=;" in clear_cookie_header
    assert "Max-Age=0" in clear_cookie_header
    assert "SameSite=Strict" in clear_cookie_header

    response = await test_client.get(
        f"/api/plugin/page/content/{PLUGIN_PAGE_DEMO_NAME}/{PLUGIN_PAGE_DEMO_PAGE_NAME}/"
    )
    assert response.status_code == 401
    asset_response = await test_client.get(_strip_query(asset_url_match.group(1)))
    assert asset_response.status_code == 401


@pytest.mark.asyncio
async def test_get_stat(app: Quart, authenticated_header: dict):
    test_client = app.test_client()
    response = await test_client.get("/api/stat/get")
    assert response.status_code == 401
    response = await test_client.get("/api/stat/get", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok" and "platform" in data["data"]


@pytest.mark.asyncio
async def test_dashboard_ssl_missing_cert_and_key_falls_back_to_http(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    shutdown_event = asyncio.Event()
    server = AstrBotDashboard(core_lifecycle_td, core_lifecycle_td.db, shutdown_event)
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
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()
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
        response = await test_client.post(
            "/api/subagent/config",
            json=payload,
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        get_response = await test_client.get(
            "/api/subagent/config", headers=authenticated_header
        )
        assert get_response.status_code == 200
        get_data = await get_response.get_json()
        assert get_data["status"] == "ok"
        assert get_data["data"]["agents"][0]["persona_id"] == "default"
    finally:
        await test_client.post(
            "/api/subagent/config",
            json=old_cfg,
            headers=authenticated_header,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], "x"])
async def test_batch_delete_sessions_rejects_non_object_payload(
    app: Quart, authenticated_header: dict, payload
):
    test_client = app.test_client()
    response = await test_client.post(
        "/api/chat/batch_delete_sessions",
        json=payload,
        headers=authenticated_header,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Invalid JSON body: expected object"


@pytest.mark.asyncio
async def test_batch_delete_sessions_masks_internal_error(
    app: Quart, authenticated_header: dict, monkeypatch
):
    test_client = app.test_client()

    create_session_response = await test_client.get(
        "/api/chat/new_session", headers=authenticated_header
    )
    assert create_session_response.status_code == 200
    create_session_data = await create_session_response.get_json()
    session_id = create_session_data["data"]["session_id"]

    async def _raise_error(*args, **kwargs):
        raise RuntimeError("secret-internal-error")

    monkeypatch.setattr(
        "astrbot.dashboard.routes.chat.ChatRoute._delete_session_internal",
        _raise_error,
    )

    response = await test_client.post(
        "/api/chat/batch_delete_sessions",
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
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    test_client = app.test_client()
    db = core_lifecycle_td.db

    create_session_response = await test_client.get(
        "/api/chat/new_session", headers=authenticated_header
    )
    assert create_session_response.status_code == 200
    create_session_data = await create_session_response.get_json()
    session_id = create_session_data["data"]["session_id"]

    original_batch_lookup = db.get_platform_sessions_by_ids
    called = {"batch_lookup_count": 0}

    async def _wrapped_batch_lookup(session_ids: list[str]):
        called["batch_lookup_count"] += 1
        return await original_batch_lookup(session_ids)

    # 不应单个查询
    async def _should_not_call_single_lookup(session_id: str):
        raise AssertionError(
            f"single-session lookup should not be called: {session_id}"
        )

    monkeypatch.setattr(db, "get_platform_sessions_by_ids", _wrapped_batch_lookup)
    monkeypatch.setattr(
        db, "get_platform_session_by_id", _should_not_call_single_lookup
    )

    response = await test_client.post(
        "/api/chat/batch_delete_sessions",
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
async def test_plugins(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    """测试插件 API 端点，使用 Mock 避免真实网络调用。"""
    test_client = app.test_client()

    # 已经安装的插件
    response = await test_client.get("/api/plugin/get", headers=authenticated_header)
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

    # 插件市场
    response = await test_client.get(
        "/api/plugin/market_list",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    # 使用 MockPluginBuilder 创建测试插件
    plugin_store_path = core_lifecycle_td.plugin_manager.plugin_store_path
    builder = MockPluginBuilder(plugin_store_path)

    # 定义测试插件
    test_plugin_name = "test_mock_plugin"
    test_repo_url = f"https://github.com/test/{test_plugin_name}"

    # 创建 Mock 函数
    mock_install = create_mock_updater_install(
        builder,
        repo_to_plugin={test_repo_url: test_plugin_name},
    )
    mock_update = create_mock_updater_update(builder)

    # 设置 Mock
    monkeypatch.setattr(
        core_lifecycle_td.plugin_manager.updator, "install", mock_install
    )
    monkeypatch.setattr(core_lifecycle_td.plugin_manager.updator, "update", mock_update)

    try:
        # 插件安装
        response = await test_client.post(
            "/api/plugin/install",
            json={"url": test_repo_url},
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok", (
            f"安装失败: {data.get('message', 'unknown error')}"
        )

        response = await test_client.get(
            f"/api/plugin/get?name={test_plugin_name}",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert len(data["data"]) == 1
        assert "components" not in data["data"][0]
        installed_at = data["data"][0]["installed_at"]
        assert installed_at is not None
        datetime.fromisoformat(installed_at)

        response = await test_client.get(
            f"/api/plugin/detail?name={test_plugin_name}",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["name"] == test_plugin_name
        assert "components" in data["data"]
        assert isinstance(data["data"]["components"], list)

        # 验证插件已注册
        exists = any(md.name == test_plugin_name for md in star_registry)
        assert exists is True, f"插件 {test_plugin_name} 未成功载入"

        # 插件更新
        response = await test_client.post(
            "/api/plugin/update",
            json={"name": test_plugin_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        # 验证更新标记文件
        plugin_dir = builder.get_plugin_path(test_plugin_name)
        assert (plugin_dir / ".updated").exists()

        # 插件卸载
        response = await test_client.post(
            "/api/plugin/uninstall",
            json={"name": test_plugin_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

        # 验证插件已卸载
        exists = any(md.name == test_plugin_name for md in star_registry)
        assert exists is False, f"插件 {test_plugin_name} 未成功卸载"
        exists = any(
            test_plugin_name in md.handler_module_path for md in star_handlers_registry
        )
        assert exists is False, f"插件 {test_plugin_name} handler 未成功清理"

    finally:
        # 清理测试插件
        builder.cleanup(test_plugin_name)


@pytest.mark.asyncio
async def test_plugins_when_installed_at_unresolved(
    app: Quart,
    authenticated_header: dict,
    monkeypatch,
):
    """Tests plugin payload when installed_at cannot be resolved."""
    test_client = app.test_client()

    monkeypatch.setattr(PluginRoute, "_get_plugin_installed_at", lambda *_args: None)

    response = await test_client.get("/api/plugin/get", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    for plugin in data["data"]:
        assert "name" in plugin
        assert "installed_at" in plugin
        assert plugin["installed_at"] is None


@pytest.mark.asyncio
async def test_commands_api(app: Quart, authenticated_header: dict):
    """Tests the command management API endpoints."""
    test_client = app.test_client()

    # GET /api/commands - list commands
    response = await test_client.get("/api/commands", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "items" in data["data"]
    assert "summary" in data["data"]
    summary = data["data"]["summary"]
    assert "total" in summary
    assert "disabled" in summary
    assert "conflicts" in summary

    # GET /api/commands/conflicts - list conflicts
    response = await test_client.get(
        "/api/commands/conflicts", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    # conflicts is a list
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_t2i_set_active_template_syncs_all_configs(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()
    template_name = f"sync_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("sync-a", "sync-b"):
            response = await test_client.post(
                "/api/config/abconf/new",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/t2i/templates/create",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }}</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201
        data = await response.get_json()
        assert data["status"] == "ok"

        response = await test_client.post(
            "/api/t2i/templates/set_active",
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
        await test_client.post(
            "/api/t2i/templates/set_active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.post(
                "/api/config/abconf/delete",
                json={"id": conf_id},
                headers=authenticated_header,
            )


@pytest.mark.asyncio
async def test_t2i_reset_default_template_syncs_all_configs(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()
    template_name = f"reset_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("reset-a", "reset-b"):
            response = await test_client.post(
                "/api/config/abconf/new",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/t2i/templates/create",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }} reset</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201
        data = await response.get_json()
        assert data["status"] == "ok"

        response = await test_client.post(
            "/api/t2i/templates/set_active",
            json={"name": template_name},
            headers=authenticated_header,
        )
        assert response.status_code == 200

        response = await test_client.post(
            "/api/t2i/templates/reset_default",
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
        await test_client.post(
            "/api/t2i/templates/set_active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.post(
                "/api/config/abconf/delete",
                json={"id": conf_id},
                headers=authenticated_header,
            )


@pytest.mark.asyncio
async def test_t2i_update_active_template_reloads_all_schedulers(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()
    template_name = f"update_tpl_{uuid.uuid4().hex[:8]}"
    created_conf_ids: list[str] = []

    try:
        for name in ("update-a", "update-b"):
            response = await test_client.post(
                "/api/config/abconf/new",
                json={"name": name},
                headers=authenticated_header,
            )
            assert response.status_code == 200
            data = await response.get_json()
            assert data["status"] == "ok"
            created_conf_ids.append(data["data"]["conf_id"])

        response = await test_client.post(
            "/api/t2i/templates/create",
            json={
                "name": template_name,
                "content": "<html><body>{{ text }} v1</body></html>",
            },
            headers=authenticated_header,
        )
        assert response.status_code == 201

        response = await test_client.post(
            "/api/t2i/templates/set_active",
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
            f"/api/t2i/templates/{template_name}",
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
        await test_client.post(
            "/api/t2i/templates/set_active",
            json={"name": "base"},
            headers=authenticated_header,
        )
        await test_client.delete(
            f"/api/t2i/templates/{template_name}",
            headers=authenticated_header,
        )
        for conf_id in created_conf_ids:
            await test_client.post(
                "/api/config/abconf/delete",
                json={"id": conf_id},
                headers=authenticated_header,
            )


@pytest.mark.asyncio
async def test_check_update(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    """测试检查更新 API，使用 Mock 避免真实网络调用。"""
    test_client = app.test_client()

    # Mock 更新检查和网络请求
    async def mock_check_update(*args, **kwargs):
        """Mock 更新检查，返回无新版本。"""
        return None  # None 表示没有新版本

    async def mock_get_dashboard_version(*args, **kwargs):
        """Mock Dashboard 版本获取。"""
        from astrbot.core.config.default import VERSION

        return f"v{VERSION}"  # 返回当前版本

    monkeypatch.setattr(
        core_lifecycle_td.astrbot_updator,
        "check_update",
        mock_check_update,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.routes.update.get_dashboard_version",
        mock_get_dashboard_version,
    )

    response = await test_client.get("/api/update/check", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "success"
    assert data["data"]["has_new_version"] is False


@pytest.mark.asyncio
async def test_do_update(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path_factory,
):
    test_client = app.test_client()

    # Use a temporary path for the mock update to avoid side effects
    temp_release_dir = tmp_path_factory.mktemp("release")
    release_path = temp_release_dir / "astrbot"
    calls = []

    async def mock_update(*args, **kwargs):
        """Mocks the update process by creating a directory in the temp path."""
        calls.append("core")
        callback = kwargs.get("progress_callback")
        if callback:
            callback({"downloaded": 10, "total": 10, "percent": 1, "speed": 1})
        os.makedirs(release_path, exist_ok=True)

    async def mock_download_dashboard(*args, **kwargs):
        """Mocks the dashboard download to prevent network access."""
        calls.append("dashboard")
        callback = kwargs.get("progress_callback")
        if callback:
            callback({"downloaded": 10, "total": 10, "percent": 1, "speed": 1})
        return

    async def mock_pip_install(*args, **kwargs):
        """Mocks pip install to prevent actual installation."""
        return

    monkeypatch.setattr(core_lifecycle_td.astrbot_updator, "update", mock_update)
    monkeypatch.setattr(
        "astrbot.dashboard.routes.update.download_dashboard",
        mock_download_dashboard,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.routes.update.pip_installer.install",
        mock_pip_install,
    )

    response = await test_client.post(
        "/api/update/do",
        headers=authenticated_header,
        json={"version": "v3.4.0", "reboot": False, "progress_id": "test-progress"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert os.path.exists(release_path)
    assert calls[:2] == ["dashboard", "core"]

    progress_response = await test_client.get(
        "/api/update/progress?id=test-progress",
        headers=authenticated_header,
    )
    progress_data = await progress_response.get_json()
    assert progress_data["status"] == "ok"
    assert progress_data["data"]["status"] == "success"
    assert progress_data["data"]["overall_percent"] == 100


@pytest.mark.asyncio
async def test_install_pip_package_returns_pip_install_error_message(
    app: Quart,
    authenticated_header: dict,
    monkeypatch,
):
    test_client = app.test_client()

    async def mock_pip_install(*args, **kwargs):
        del args, kwargs
        raise PipInstallError("install failed", code=2)

    monkeypatch.setattr(
        "astrbot.dashboard.routes.update.pip_installer.install",
        mock_pip_install,
    )

    response = await test_client.post(
        "/api/update/pip-install",
        headers=authenticated_header,
        json={"package": "demo-package"},
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "install failed"


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
    app: Quart,
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
        "astrbot.dashboard.routes.skills.NeoSkillSyncManager.sync_release",
        _fake_sync_release,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.routes.skills.sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )

    test_client = app.test_client()

    response = await test_client.get(
        "/api/skills/neo/candidates", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)
    assert data["data"][0]["id"] == "cand-1"

    response = await test_client.get(
        "/api/skills/neo/releases", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)
    assert data["data"][0]["id"] == "rel-1"

    response = await test_client.get(
        "/api/skills/neo/payload?payload_ref=pref-1", headers=authenticated_header
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["payload_ref"] == "pref-1"

    response = await test_client.post(
        "/api/skills/neo/evaluate",
        json={"candidate_id": "cand-1", "passed": True, "score": 0.95},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["candidate_id"] == "cand-1"
    assert data["data"]["passed"] is True

    response = await test_client.post(
        "/api/skills/neo/evaluate",
        json={"candidate_id": "cand-1", "passed": "false", "score": 0.0},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["passed"] is False

    response = await test_client.post(
        "/api/skills/neo/promote",
        json={"candidate_id": "cand-1", "stage": "stable"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["release"]["id"] == "rel-2"
    assert data["data"]["sync"]["local_skill_name"] == "neo_demo"

    response = await test_client.post(
        "/api/skills/neo/rollback",
        json={"release_id": "rel-2"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["rolled_back_release_id"] == "rel-2"

    response = await test_client.post(
        "/api/skills/neo/sync",
        json={"release_id": "rel-2"},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["skill_key"] == "neo.demo"


@pytest.mark.asyncio
async def test_batch_upload_skills_returns_error_when_all_files_invalid(
    app: Quart,
    authenticated_header: dict,
):
    test_client = app.test_client()

    response = await test_client.post(
        "/api/skills/batch-upload",
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
    app: Quart,
    authenticated_header: dict,
    monkeypatch,
):
    async def _fake_sync_skills_to_active_sandboxes():
        return

    def _fake_install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
    ):
        _ = self, overwrite
        assert zip_path.endswith(".zip")
        return "demo_skill"

    monkeypatch.setattr(
        "astrbot.dashboard.routes.skills.sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.routes.skills.SkillManager.install_skill_from_zip",
        _fake_install_skill_from_zip,
    )

    test_client = app.test_client()

    response = await test_client.post(
        "/api/skills/batch-upload",
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
    app: Quart,
    authenticated_header: dict,
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
        "astrbot.dashboard.routes.skills.sync_skills_to_active_sandboxes",
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
        "astrbot.dashboard.routes.skills.get_astrbot_temp_path",
        lambda: str(temp_dir),
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

    test_client = app.test_client()

    response = await test_client.post(
        "/api/skills/batch-upload",
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
    app: Quart,
    authenticated_header: dict,
    monkeypatch,
):
    async def _fake_sync_skills_to_active_sandboxes():
        return

    def _fake_install_skill_from_zip(
        self,
        zip_path: str,
        *,
        overwrite: bool = True,
    ):
        _ = self, overwrite
        if "ok_skill" in zip_path:
            return "ok_skill"
        raise RuntimeError("install failed")

    monkeypatch.setattr(
        "astrbot.dashboard.routes.skills.sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.dashboard.routes.skills.SkillManager.install_skill_from_zip",
        _fake_install_skill_from_zip,
    )

    test_client = app.test_client()

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
        "/api/skills/batch-upload",
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
        {"filename": "bad_skill.zip", "error": "install failed"}
    ]


@pytest.mark.asyncio
async def test_skill_file_browser_and_editor_security(
    app: Quart,
    authenticated_header: dict,
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
    monkeypatch.setattr(
        "astrbot.dashboard.routes.skills.sync_skills_to_active_sandboxes",
        _fake_sync_skills_to_active_sandboxes,
    )

    test_client = app.test_client()

    list_response = await test_client.get(
        "/api/skills/files?name=demo_skill",
        headers=authenticated_header,
    )
    list_data = await list_response.get_json()
    assert list_data["status"] == "ok"
    listed_paths = {item["path"] for item in list_data["data"]["entries"]}
    assert "SKILL.md" in listed_paths
    assert "outside-link.txt" not in listed_paths

    read_response = await test_client.get(
        "/api/skills/file?name=demo_skill&path=SKILL.md",
        headers=authenticated_header,
    )
    read_data = await read_response.get_json()
    assert read_data["status"] == "ok"
    assert "# Demo" in read_data["data"]["content"]

    update_response = await test_client.post(
        "/api/skills/file",
        json={
            "name": "demo_skill",
            "path": "SKILL.md",
            "content": "# Updated\n",
        },
        headers=authenticated_header,
    )
    update_data = await update_response.get_json()
    assert update_data["status"] == "ok"
    assert skill_md.read_text(encoding="utf-8") == "# Updated\n"

    traversal_response = await test_client.get(
        "/api/skills/file?name=demo_skill&path=../outside.txt",
        headers=authenticated_header,
    )
    traversal_data = await traversal_response.get_json()
    assert traversal_data["status"] == "error"

    symlink_response = await test_client.get(
        "/api/skills/file?name=demo_skill&path=outside-link.txt",
        headers=authenticated_header,
    )
    symlink_data = await symlink_response.get_json()
    assert symlink_data["status"] == "error"

    large_response = await test_client.get(
        "/api/skills/file?name=demo_skill&path=large.md",
        headers=authenticated_header,
    )
    large_data = await large_response.get_json()
    assert large_data["status"] == "error"
    assert large_data["message"] == "File is too large"

    binary_response = await test_client.get(
        "/api/skills/file?name=demo_skill&path=binary.md",
        headers=authenticated_header,
    )
    binary_data = await binary_response.get_json()
    assert binary_data["status"] == "error"
    assert binary_data["message"] == "File is not valid UTF-8 text"
