import asyncio
import copy
import errno
import hashlib
import io
import os
import sys
import uuid
import zipfile
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from quart import Quart
from werkzeug.datastructures import FileStorage

from astrbot.cli.commands.cmd_conf import hash_dashboard_password_secure
from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.star import star_registry
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.utils.pip_installer import PipInstallError
from astrbot.dashboard.routes.plugin import PluginRoute
from astrbot.dashboard.server import AstrBotDashboard, _expand_env_placeholders
from tests.fixtures.helpers import (
    MockPluginBuilder,
    create_mock_updater_install,
    create_mock_updater_update,
)

TEST_DASHBOARD_PASSWORD = "astrbot-test-password"


def test_check_port_in_use_only_treats_eaddrinuse_as_occupied(
    monkeypatch: pytest.MonkeyPatch,
):
    server = AstrBotDashboard.__new__(AstrBotDashboard)

    class _Socket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def setsockopt(self, *args, **kwargs):
            return None

        def bind(self, address):
            raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(
        "astrbot.dashboard.server.socket.socket", lambda *args, **kwargs: _Socket()
    )

    assert server.check_port_in_use("127.0.0.1", 3002) is True


def test_check_port_in_use_ignores_permission_errors(monkeypatch: pytest.MonkeyPatch):
    server = AstrBotDashboard.__new__(AstrBotDashboard)

    class _Socket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def setsockopt(self, *args, **kwargs):
            return None

        def bind(self, address):
            raise PermissionError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(
        "astrbot.dashboard.server.socket.socket", lambda *args, **kwargs: _Socket()
    )

    assert server.check_port_in_use("127.0.0.1", 3002) is False


def test_expand_env_placeholders_resolves_env_and_default(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("HOST", "0.0.0.0")

    assert _expand_env_placeholders("${HOST}", "host") == "0.0.0.0"
    assert _expand_env_placeholders("${MISSING:-3002}", "port") == "3002"


def test_expand_env_placeholders_raises_for_unresolved_variable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("HOST", raising=False)
    with pytest.raises(ValueError, match="dashboard host: HOST"):
        _expand_env_placeholders("${HOST}", "host")


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    """Creates and initializes a core lifecycle instance with a temporary database."""
    tmp_db_path = tmp_path_factory.mktemp("data") / "test_data_v3.db"
    db = SQLiteDatabase(str(tmp_db_path))
    log_broker = LogBroker()
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    await core_lifecycle.initialize()
    core_lifecycle.astrbot_config["dashboard"]["username"] = "astrbot"
    core_lifecycle.astrbot_config["dashboard"]["password"] = (
        hash_dashboard_password_secure(TEST_DASHBOARD_PASSWORD)
    )
    try:
        yield core_lifecycle
    finally:
        # 优先停止核心生命周期以释放资源(包括关闭 MCP 等后台任务)
        try:
            _stop_res = core_lifecycle.stop()
            if asyncio.iscoroutine(_stop_res):
                await _stop_res
        except Exception:
            # 停止过程中如有异常,不影响后续清理
            pass


@pytest.fixture(scope="module")
def app(core_lifecycle_td: AstrBotCoreLifecycle):
    """Creates a Quart app instance for testing."""
    shutdown_event = asyncio.Event()
    # The db instance is already part of the core_lifecycle_td
    server = AstrBotDashboard(core_lifecycle_td, core_lifecycle_td.db, shutdown_event)
    return server.app


@pytest_asyncio.fixture(scope="module")
async def authenticated_header(app: Quart, core_lifecycle_td: AstrBotCoreLifecycle):
    """Handles login and returns an authenticated header."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": TEST_DASHBOARD_PASSWORD,
        },
    )
    data = await response.get_json()
    assert data["status"] == "ok"
    token = data["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_auth_login(app: Quart, core_lifecycle_td: AstrBotCoreLifecycle):
    """Tests the login functionality with both wrong and correct credentials."""
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
            "password": TEST_DASHBOARD_PASSWORD,
        },
    )
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "token" in data["data"]


@pytest.mark.asyncio
async def test_auth_login_rejects_legacy_md5_password(
    app: Quart, core_lifecycle_td: AstrBotCoreLifecycle
):
    test_client = app.test_client()
    username = core_lifecycle_td.astrbot_config["dashboard"]["username"]
    legacy_md5 = hashlib.md5(TEST_DASHBOARD_PASSWORD.encode("utf-8")).hexdigest()

    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": "",
            "password_md5": legacy_md5,
        },
    )
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_get_stat(app: Quart, authenticated_header: dict):
    test_client = app.test_client()
    response = await test_client.get("/api/stat/get")
    assert response.status_code == 401
    response = await test_client.get("/api/stat/get", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "platform" in data["data"]


@pytest.mark.asyncio
async def test_apikey_create_with_invalid_scopes(
    app: Quart,
    authenticated_header: dict,
):
    """Test that create_api_key returns error for invalid scopes."""
    test_client = app.test_client()

    # Invalid scopes type
    response = await test_client.post(
        "/api/apikey/create",
        headers=authenticated_header,
        json={"scopes": "not-a-list"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "Invalid scopes" in data["message"]

    # Empty scopes list
    response = await test_client.post(
        "/api/apikey/create",
        headers=authenticated_header,
        json={"scopes": []},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Invalid expires_in_days
    response = await test_client.post(
        "/api/apikey/create",
        headers=authenticated_header,
        json={"expires_in_days": "not-a-number"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # expires_in_days <= 0
    response = await test_client.post(
        "/api/apikey/create",
        headers=authenticated_header,
        json={"expires_in_days": 0},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_apikey_create_success(
    app: Quart,
    authenticated_header: dict,
):
    """Test successful api key creation."""
    test_client = app.test_client()

    response = await test_client.post(
        "/api/apikey/create",
        headers=authenticated_header,
        json={"name": "Test Key", "scopes": ["chat"]},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "api_key" in data["data"]
    assert data["data"]["name"] == "Test Key"
    assert data["data"]["scopes"] == ["chat"]


@pytest.mark.asyncio
async def test_apikey_list(
    app: Quart,
    authenticated_header: dict,
):
    """Test listing api keys."""
    test_client = app.test_client()

    response = await test_client.get("/api/apikey/list", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_apikey_revoke_missing_key_id(
    app: Quart,
    authenticated_header: dict,
):
    """Test that revoke_api_key returns error when key_id is missing."""
    test_client = app.test_client()

    response = await test_client.post(
        "/api/apikey/revoke",
        headers=authenticated_header,
        json={},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "key_id" in data["message"]


@pytest.mark.asyncio
async def test_apikey_delete_missing_key_id(
    app: Quart,
    authenticated_header: dict,
):
    """Test that delete_api_key returns error when key_id is missing."""
    test_client = app.test_client()

    response = await test_client.post(
        "/api/apikey/delete",
        headers=authenticated_header,
        json={},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "key_id" in data["message"]


@pytest.mark.asyncio
async def test_apikey_revoke_not_found(
    app: Quart,
    authenticated_header: dict,
):
    """Test that revoke_api_key returns error when key is not found."""
    test_client = app.test_client()

    response = await test_client.post(
        "/api/apikey/revoke",
        headers=authenticated_header,
        json={"key_id": "nonexistent-key"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_apikey_delete_not_found(
    app: Quart,
    authenticated_header: dict,
):
    """Test that delete_api_key returns error when key is not found."""
    test_client = app.test_client()

    response = await test_client.post(
        "/api/apikey/delete",
        headers=authenticated_header,
        json={"key_id": "nonexistent-key"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


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
    """测试插件 API 端点,使用 Mock 避免真实网络调用｡"""
    test_client = app.test_client()

    # 已经安装的插件
    response = await test_client.get("/api/plugin/get", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    for plugin in data["data"]:
        assert "installed_at" in plugin
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
        installed_at = data["data"][0]["installed_at"]
        assert installed_at is not None
        datetime.fromisoformat(installed_at)

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
async def test_commands_toggle_missing_params(
    app: Quart,
    authenticated_header: dict,
):
    """Test that toggle_command returns error when params are missing."""
    test_client = app.test_client()

    # Missing both params
    response = await test_client.post(
        "/api/commands/toggle",
        headers=authenticated_header,
        json={},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Missing enabled
    response = await test_client.post(
        "/api/commands/toggle",
        headers=authenticated_header,
        json={"handler_full_name": "test_command"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Missing handler_full_name
    response = await test_client.post(
        "/api/commands/toggle",
        headers=authenticated_header,
        json={"enabled": True},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_commands_rename_missing_params(
    app: Quart,
    authenticated_header: dict,
):
    """Test that rename_command returns error when params are missing."""
    test_client = app.test_client()

    # Missing both params
    response = await test_client.post(
        "/api/commands/rename",
        headers=authenticated_header,
        json={},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Missing new_name
    response = await test_client.post(
        "/api/commands/rename",
        headers=authenticated_header,
        json={"handler_full_name": "test_command"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Missing handler_full_name
    response = await test_client.post(
        "/api/commands/rename",
        headers=authenticated_header,
        json={"new_name": "new_test_command"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_commands_permission_missing_params(
    app: Quart,
    authenticated_header: dict,
):
    """Test that update_permission returns error when params are missing."""
    test_client = app.test_client()

    # Missing both params
    response = await test_client.post(
        "/api/commands/permission",
        headers=authenticated_header,
        json={},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Missing permission
    response = await test_client.post(
        "/api/commands/permission",
        headers=authenticated_header,
        json={"handler_full_name": "test_command"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Missing handler_full_name
    response = await test_client.post(
        "/api/commands/permission",
        headers=authenticated_header,
        json={"permission": "all"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


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
                "content": "<html><body>{{ content }}</body></html>",
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
                "content": "<html><body>{{ content }} reset</body></html>",
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
                "content": "<html><body>{{ content }} v1</body></html>",
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
            json={"content": "<html><body>{{ content }} v2</body></html>"},
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
    """测试检查更新 API,使用 Mock 避免真实网络调用｡"""
    test_client = app.test_client()

    # Mock 更新检查和网络请求
    async def mock_check_update(*args, **kwargs):
        """Mock 更新检查,返回无新版本｡"""
        return None  # None 表示没有新版本

    async def mock_get_dashboard_version(*args, **kwargs):
        """Mock Dashboard 版本获取｡"""
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

    async def mock_update(*args, **kwargs):
        """Mocks the update process by creating a directory in the temp path."""
        os.makedirs(release_path, exist_ok=True)

    async def mock_download_dashboard(*args, **kwargs):
        """Mocks the dashboard download to prevent network access."""
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
        json={"version": "v3.4.0", "reboot": False},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert os.path.exists(release_path)


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
async def test_tui_new_session(app: Quart, authenticated_header: dict):
    """Test creating a new TUI session."""
    test_client = app.test_client()

    response = await test_client.get("/api/tui/new_session", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "session_id" in data["data"]
    assert data["data"]["platform_id"] == "tui"


@pytest.mark.asyncio
async def test_tui_get_sessions(app: Quart, authenticated_header: dict):
    """Test getting TUI sessions."""
    test_client = app.test_client()

    # Create a session first
    new_session_response = await test_client.get(
        "/api/tui/new_session", headers=authenticated_header
    )
    new_session_data = await new_session_response.get_json()
    session_id = new_session_data["data"]["session_id"]

    # Get sessions
    response = await test_client.get("/api/tui/sessions", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)
    # Find our created session
    tui_sessions = [s for s in data["data"] if s["session_id"] == session_id]
    assert len(tui_sessions) == 1
    assert tui_sessions[0]["platform_id"] == "tui"


@pytest.mark.asyncio
async def test_tui_get_session_with_history(
    app: Quart, authenticated_header: dict
):
    """Test getting a single TUI session with history."""
    test_client = app.test_client()

    # Create a session first
    new_session_response = await test_client.get(
        "/api/tui/new_session", headers=authenticated_header
    )
    new_session_data = await new_session_response.get_json()
    session_id = new_session_data["data"]["session_id"]

    # Get the session
    response = await test_client.get(
        f"/api/tui/get_session?session_id={session_id}",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "history" in data["data"]
    assert isinstance(data["data"]["history"], list)
    assert data["data"]["is_running"] is False


@pytest.mark.asyncio
async def test_tui_get_session_missing_session_id(
    app: Quart, authenticated_header: dict
):
    """Test that get_session returns error when session_id is missing."""
    test_client = app.test_client()

    response = await test_client.get("/api/tui/get_session", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "session_id" in data["message"]


@pytest.mark.asyncio
async def test_tui_update_session_display_name(
    app: Quart, authenticated_header: dict
):
    """Test updating a TUI session's display name."""
    test_client = app.test_client()

    # Create a session first
    new_session_response = await test_client.get(
        "/api/tui/new_session", headers=authenticated_header
    )
    new_session_data = await new_session_response.get_json()
    session_id = new_session_data["data"]["session_id"]

    # Update the display name
    response = await test_client.post(
        "/api/tui/update_session_display_name",
        headers=authenticated_header,
        json={"session_id": session_id, "display_name": "My Test Session"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_tui_update_session_missing_params(
    app: Quart, authenticated_header: dict
):
    """Test that update_session_display_name returns error when params are missing."""
    test_client = app.test_client()

    # Missing session_id
    response = await test_client.post(
        "/api/tui/update_session_display_name",
        headers=authenticated_header,
        json={"display_name": "Test"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "session_id" in data["message"]

    # Missing display_name
    response = await test_client.post(
        "/api/tui/update_session_display_name",
        headers=authenticated_header,
        json={"session_id": "test-session"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "display_name" in data["message"]


@pytest.mark.asyncio
async def test_tui_delete_session(
    app: Quart, authenticated_header: dict
):
    """Test deleting a TUI session."""
    test_client = app.test_client()

    # Create a session first
    new_session_response = await test_client.get(
        "/api/tui/new_session", headers=authenticated_header
    )
    new_session_data = await new_session_response.get_json()
    session_id = new_session_data["data"]["session_id"]

    # Delete the session
    response = await test_client.get(
        f"/api/tui/delete_session?session_id={session_id}",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    # Verify by listing sessions - the deleted session should not appear
    sessions_response = await test_client.get(
        "/api/tui/sessions", headers=authenticated_header
    )
    sessions_data = await sessions_response.get_json()
    tui_sessions = [
        s for s in sessions_data["data"] if s["session_id"] == session_id
    ]
    assert len(tui_sessions) == 0


@pytest.mark.asyncio
async def test_tui_delete_session_missing_id(
    app: Quart, authenticated_header: dict
):
    """Test that delete_session returns error when session_id is missing."""
    test_client = app.test_client()

    response = await test_client.get("/api/tui/delete_session", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "session_id" in data["message"]


@pytest.mark.asyncio
async def test_tui_delete_session_not_found(
    app: Quart, authenticated_header: dict
):
    """Test that delete_session returns error when session is not found."""
    test_client = app.test_client()

    response = await test_client.get(
        "/api/tui/delete_session?session_id=nonexistent-session",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "not found" in data["message"]


@pytest.mark.asyncio
async def test_tui_stop_session(
    app: Quart, authenticated_header: dict
):
    """Test stopping a TUI session."""
    test_client = app.test_client()

    # Create a session first
    new_session_response = await test_client.get(
        "/api/tui/new_session", headers=authenticated_header
    )
    new_session_data = await new_session_response.get_json()
    session_id = new_session_data["data"]["session_id"]

    # Stop the session (will return 0 since no agent is running)
    response = await test_client.post(
        "/api/tui/stop",
        headers=authenticated_header,
        json={"session_id": session_id},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["stopped_count"] == 0


@pytest.mark.asyncio
async def test_tui_stop_session_missing_params(
    app: Quart, authenticated_header: dict
):
    """Test that stop_session returns error when params are missing."""
    test_client = app.test_client()

    # Missing session_id
    response = await test_client.post(
        "/api/tui/stop",
        headers=authenticated_header,
        json={},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "session_id" in data["message"]


@pytest.mark.asyncio
async def test_tui_stop_session_not_found(
    app: Quart, authenticated_header: dict
):
    """Test that stop_session returns error when session is not found."""
    test_client = app.test_client()

    response = await test_client.post(
        "/api/tui/stop",
        headers=authenticated_header,
        json={"session_id": "nonexistent-session"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "not found" in data["message"]


@pytest.mark.asyncio
async def test_tui_batch_delete_sessions(
    app: Quart, authenticated_header: dict
):
    """Test batch deleting TUI sessions."""
    test_client = app.test_client()

    # Create two sessions
    session1_response = await test_client.get(
        "/api/tui/new_session", headers=authenticated_header
    )
    session1_id = (await session1_response.get_json())["data"]["session_id"]

    session2_response = await test_client.get(
        "/api/tui/new_session", headers=authenticated_header
    )
    session2_id = (await session2_response.get_json())["data"]["session_id"]

    # Batch delete
    response = await test_client.post(
        "/api/tui/batch_delete_sessions",
        headers=authenticated_header,
        json={"session_ids": [session1_id, session2_id]},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["deleted_count"] == 2
    assert data["data"]["failed_count"] == 0


@pytest.mark.asyncio
async def test_tui_batch_delete_sessions_missing_params(
    app: Quart, authenticated_header: dict
):
    """Test that batch_delete_sessions returns error when params are missing."""
    test_client = app.test_client()

    # Missing session_ids
    response = await test_client.post(
        "/api/tui/batch_delete_sessions",
        headers=authenticated_header,
        json={},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Invalid session_ids type
    response = await test_client.post(
        "/api/tui/batch_delete_sessions",
        headers=authenticated_header,
        json={"session_ids": "not-a-list"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


# ═══════════════════════ Tools Route Tests ═══════════════════════════════════


@pytest.mark.asyncio
async def test_tools_get_tool_list(app: Quart, authenticated_header: dict):
    """Test getting the list of all tools."""
    test_client = app.test_client()
    response = await test_client.get(
        "/api/tools/list",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_tools_toggle_tool_missing_params(
    app: Quart, authenticated_header: dict
):
    """Test toggle_tool returns error when params are missing."""
    test_client = app.test_client()

    # Missing name
    response = await test_client.post(
        "/api/tools/toggle-tool",
        headers=authenticated_header,
        json={"activate": True},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"

    # Missing activate
    response = await test_client.post(
        "/api/tools/toggle-tool",
        headers=authenticated_header,
        json={"name": "some_tool"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_tools_toggle_tool_not_found(app: Quart, authenticated_header: dict):
    """Test toggle_tool returns error when tool doesn't exist."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/tools/toggle-tool",
        headers=authenticated_header,
        json={"name": "nonexistent_tool_xyz", "activate": True},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_tools_get_mcp_servers(app: Quart, authenticated_header: dict):
    """Test getting MCP server list."""
    test_client = app.test_client()
    response = await test_client.get(
        "/api/tools/mcp/servers",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_tools_add_mcp_server_empty_name(
    app: Quart, authenticated_header: dict
):
    """Test add_mcp_server returns error when name is empty."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/tools/mcp/add",
        headers=authenticated_header,
        json={"name": "", "active": True},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_tools_add_mcp_server_no_valid_config(
    app: Quart, authenticated_header: dict
):
    """Test add_mcp_server returns error when no valid config is provided."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/tools/mcp/add",
        headers=authenticated_header,
        json={"name": "test-server", "active": True},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_tools_add_mcp_server_connection_failure(
    app: Quart, authenticated_header: dict
):
    """Test add_mcp_server returns error when connection test fails."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/tools/mcp/add",
        headers=authenticated_header,
        json={
            "name": "test-server",
            "active": True,
            "url": "http://localhost:9999/nonexistent",
        },
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    # Should get a connection error
    assert "error" in data["status"].lower() or "failed" in data["message"].lower()


@pytest.mark.asyncio
async def test_tools_update_mcp_server_empty_name(
    app: Quart, authenticated_header: dict
):
    """Test update_mcp_server returns error when name is empty."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/tools/mcp/update",
        headers=authenticated_header,
        json={"name": "", "active": True},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_tools_update_mcp_server_not_found(app: Quart, authenticated_header: dict):
    """Test update_mcp_server returns error when server doesn't exist."""
    test_client = app.test_client()

    # When the server doesn't exist, the response will be an error
    # The actual behavior depends on the config state
    response = await test_client.post(
        "/api/tools/mcp/update",
        headers=authenticated_header,
        json={"name": "nonexistent-server-xyz", "active": True},
    )
    assert response.status_code == 200
    data = await response.get_json()
    # This should return an error because the server doesn't exist
    assert data["status"] == "error"
    assert "does not exist" in data["message"]


@pytest.mark.asyncio
async def test_tools_delete_mcp_server_empty_name(
    app: Quart, authenticated_header: dict
):
    """Test delete_mcp_server returns error when name is empty."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/tools/mcp/delete",
        headers=authenticated_header,
        json={"name": ""},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_tools_delete_mcp_server_not_found(app: Quart, authenticated_header: dict):
    """Test delete_mcp_server returns error when server doesn't exist."""
    test_client = app.test_client()

    response = await test_client.post(
        "/api/tools/mcp/delete",
        headers=authenticated_header,
        json={"name": "nonexistent-server-xyz"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "does not exist" in data["message"]


@pytest.mark.asyncio
async def test_tools_test_mcp_connection_invalid_config(
    app: Quart, authenticated_header: dict
):
    """Test test_mcp_connection returns error for invalid config."""
    test_client = app.test_client()

    # Empty config
    response = await test_client.post(
        "/api/tools/mcp/test",
        headers=authenticated_header,
        json={"mcp_server_config": {}},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_tools_sync_provider_unknown_provider(
    app: Quart, authenticated_header: dict
):
    """Test sync_provider returns error for unknown provider."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/tools/mcp/sync-provider",
        headers=authenticated_header,
        json={"name": "unknown_provider"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "Unknown provider" in data["message"]
