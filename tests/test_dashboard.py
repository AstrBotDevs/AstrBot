import asyncio
import io
import os
import sys
import zipfile
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from quart import Quart
from werkzeug.datastructures import FileStorage

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.star import star_registry
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.core.utils.pip_installer import PipInstallError
from astrbot.dashboard.routes.plugin import PluginRoute
from astrbot.dashboard.server import AstrBotDashboard
from tests.fixtures.helpers import (
    MockPluginBuilder,
    create_mock_updater_install,
    create_mock_updater_update,
)


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    """Creates and initializes a core lifecycle instance with a temporary database."""
    tmp_db_path = tmp_path_factory.mktemp("data") / "test_data_v3.db"
    db = SQLiteDatabase(str(tmp_db_path))
    log_broker = LogBroker()
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    await core_lifecycle.initialize()
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


@pytest_asyncio.fixture(scope="module")
async def authenticated_header(app: Quart, core_lifecycle_td: AstrBotCoreLifecycle):
    """Handles login and returns an authenticated header."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": core_lifecycle_td.astrbot_config["dashboard"]["password"],
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
            "password": core_lifecycle_td.astrbot_config["dashboard"]["password"],
        },
    )
    data = await response.get_json()
    assert data["status"] == "ok" and "token" in data["data"]


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
async def test_mcp_servers_api_exposes_client_capabilities(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    tool_mgr = core_lifecycle_td.provider_manager.llm_tools
    monkeypatch.setattr(
        tool_mgr,
        "load_mcp_config",
        lambda: {
            "mcpServers": {
                "demo": {
                    "url": "https://example.com/mcp",
                    "transport": "sse",
                    "active": True,
                    "client_capabilities": {
                        "elicitation": {
                            "enabled": True,
                            "timeout_seconds": 180,
                        },
                        "sampling": {
                            "enabled": True,
                        }
                    },
                }
            }
        },
    )

    test_client = app.test_client()
    response = await test_client.get(
        "/api/tools/mcp/servers",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"][0]["client_capabilities"]["elicitation"]["enabled"] is True
    assert data["data"][0]["client_capabilities"]["elicitation"]["timeout_seconds"] == 180
    assert data["data"][0]["client_capabilities"]["sampling"]["enabled"] is True


@pytest.mark.asyncio
async def test_mcp_servers_api_includes_resource_bridge_tools(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    tool_mgr = core_lifecycle_td.provider_manager.llm_tools
    monkeypatch.setattr(
        tool_mgr,
        "load_mcp_config",
        lambda: {
            "mcpServers": {
                "demo": {
                    "command": "node",
                    "args": ["stdio.js"],
                    "active": True,
                }
            }
        },
    )
    tool_mgr._mcp_server_runtime["demo"] = SimpleNamespace(
        client=SimpleNamespace(
            tools=[SimpleNamespace(name="demo_tool")],
            resource_bridge_tool_names=["mcp_demo_list_resources"],
            server_errlogs=[],
        )
    )

    test_client = app.test_client()
    try:
        response = await test_client.get(
            "/api/tools/mcp/servers",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"][0]["tools"] == [
            "demo_tool",
            "mcp_demo_list_resources",
        ]
    finally:
        tool_mgr._mcp_server_runtime.pop("demo", None)


@pytest.mark.asyncio
async def test_mcp_servers_api_includes_prompt_bridge_tools(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    tool_mgr = core_lifecycle_td.provider_manager.llm_tools
    monkeypatch.setattr(
        tool_mgr,
        "load_mcp_config",
        lambda: {
            "mcpServers": {
                "demo": {
                    "command": "node",
                    "args": ["stdio.js"],
                    "active": True,
                }
            }
        },
    )
    tool_mgr._mcp_server_runtime["demo"] = SimpleNamespace(
        client=SimpleNamespace(
            tools=[SimpleNamespace(name="demo_tool")],
            resource_bridge_tool_names=[],
            prompt_bridge_tool_names=["mcp_demo_list_prompts", "mcp_demo_get_prompt"],
            server_errlogs=[],
        )
    )

    test_client = app.test_client()
    try:
        response = await test_client.get(
            "/api/tools/mcp/servers",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"][0]["tools"] == [
            "demo_tool",
            "mcp_demo_list_prompts",
            "mcp_demo_get_prompt",
        ]
    finally:
        tool_mgr._mcp_server_runtime.pop("demo", None)


@pytest.mark.asyncio
async def test_add_mcp_server_persists_client_capabilities(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "astrbot.core.provider.func_tool_manager.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    tool_mgr = core_lifecycle_td.provider_manager.llm_tools
    monkeypatch.setattr(
        tool_mgr,
        "test_mcp_server_connection",
        AsyncMock(return_value=["demo_tool"]),
    )
    monkeypatch.setattr(
        tool_mgr,
        "enable_mcp_server",
        AsyncMock(return_value=None),
    )

    test_client = app.test_client()
    response = await test_client.post(
        "/api/tools/mcp/add",
        json={
            "name": "demo",
            "url": "https://example.com/mcp",
            "transport": "sse",
            "active": True,
            "client_capabilities": {
                "elicitation": {
                    "enabled": True,
                    "timeout_seconds": 240,
                },
                "sampling": {
                    "enabled": True,
                }
            },
        },
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    persisted = tool_mgr.load_mcp_config()
    assert (
        persisted["mcpServers"]["demo"]["client_capabilities"]["elicitation"][
            "enabled"
        ]
        is True
    )
    assert (
        persisted["mcpServers"]["demo"]["client_capabilities"]["elicitation"][
            "timeout_seconds"
        ]
        == 240
    )
    assert (
        persisted["mcpServers"]["demo"]["client_capabilities"]["sampling"]["enabled"]
        is True
    )


@pytest.mark.asyncio
async def test_chat_respond_elicitation_resolves_pending_reply_and_persists_message(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
):
    captured: dict[str, str] = {}

    def _fake_submit(umo: str, sender_id: str, reply_text: str, *, reply_outline=None):
        captured["umo"] = umo
        captured["sender_id"] = sender_id
        captured["reply_text"] = reply_text
        captured["reply_outline"] = reply_outline or ""
        return True

    monkeypatch.setattr(
        "astrbot.dashboard.routes.chat.submit_pending_mcp_elicitation_reply",
        _fake_submit,
    )

    test_client = app.test_client()
    new_session_response = await test_client.get(
        "/api/chat/new_session",
        headers=authenticated_header,
    )
    session_data = await new_session_response.get_json()
    session_id = session_data["data"]["session_id"]

    response = await test_client.post(
        "/api/chat/respond_elicitation",
        json={
            "session_id": session_id,
            "reply_text": '{"topic":"MCP 最小实现"}',
            "display_text": "topic: MCP 最小实现",
        },
        headers=authenticated_header,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    expected_username = core_lifecycle_td.astrbot_config["dashboard"]["username"]
    assert captured["sender_id"] == expected_username
    assert captured["reply_text"] == '{"topic":"MCP 最小实现"}'
    assert captured["reply_outline"] == "topic: MCP 最小实现"
    assert captured["umo"].endswith(f"webchat!{expected_username}!{session_id}")
    assert data["data"]["saved_message"]["content"]["message"] == [
        {"type": "plain", "text": "topic: MCP 最小实现"}
    ]


@pytest.mark.asyncio
async def test_chat_respond_elicitation_rejects_when_no_pending_request(
    app: Quart,
    authenticated_header: dict,
    monkeypatch,
):
    monkeypatch.setattr(
        "astrbot.dashboard.routes.chat.submit_pending_mcp_elicitation_reply",
        lambda *_args, **_kwargs: False,
    )

    test_client = app.test_client()
    new_session_response = await test_client.get(
        "/api/chat/new_session",
        headers=authenticated_header,
    )
    session_data = await new_session_response.get_json()
    session_id = session_data["data"]["session_id"]

    response = await test_client.post(
        "/api/chat/respond_elicitation",
        json={
            "session_id": session_id,
            "reply_text": "cancel",
            "display_text": "cancel",
        },
        headers=authenticated_header,
    )

    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "error"
    assert "No pending MCP elicitation" in data["message"]


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
