import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from quart import Quart

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.star import star_registry
from astrbot.core.star.star_handler import star_handlers_registry
from astrbot.dashboard.server import AstrBotDashboard


# 测试用插件名称
TEST_PLUGIN_NAME = "test_mock_plugin"


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


def _create_mock_plugin_metadata(plugin_dir: Path, plugin_name: str, repo_url: str) -> None:
    """创建模拟的插件目录结构和元数据文件。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "metadata.yaml").write_text(
        "\n".join(
            [
                f"name: {plugin_name}",
                "author: Test Author",
                "desc: Test plugin for unit tests",
                "version: 1.0.0",
                f"repo: {repo_url}",
            ],
        )
        + "\n",
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(
        "\n".join(
            [
                "from astrbot.api import star",
                "",
                "class Main(star.Star):",
                "    pass",
                "",
            ],
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_plugins(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    """测试插件 API 端点，使用 Mock 避免真实网络调用。"""
    test_client = app.test_client()

    # 已经安装的插件
    response = await test_client.get("/api/plugin/get", headers=authenticated_header)
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    # 插件市场
    response = await test_client.get(
        "/api/plugin/market_list",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    # Mock 插件安装、更新、卸载操作
    # 使用真实的 plugin_store_path 而不是 tmp_path
    plugin_store_path = core_lifecycle_td.plugin_manager.plugin_store_path
    mock_plugin_dir = Path(plugin_store_path) / TEST_PLUGIN_NAME
    test_repo_url = f"https://github.com/test/{TEST_PLUGIN_NAME}"

    async def mock_updater_install(repo_url: str, proxy: str = "") -> str:
        """Mock updator.install - 返回插件目录路径字符串。"""
        if repo_url != test_repo_url:
            raise Exception(f"Unknown repo: {repo_url}")
        _create_mock_plugin_metadata(mock_plugin_dir, TEST_PLUGIN_NAME, repo_url)
        return str(mock_plugin_dir)

    async def mock_updater_update(plugin, proxy: str = ""):
        """Mock updator.update。"""
        if plugin.name != TEST_PLUGIN_NAME:
            raise Exception(f"Unknown plugin: {plugin.name}")
        (mock_plugin_dir / ".updated").write_text("ok", encoding="utf-8")

    # 设置 Mock - updator.install 必须返回字符串路径
    monkeypatch.setattr(
        core_lifecycle_td.plugin_manager.updator, "install", mock_updater_install
    )
    monkeypatch.setattr(
        core_lifecycle_td.plugin_manager.updator, "update", mock_updater_update
    )

    # 插件安装 - 使用测试 URL
    response = await test_client.post(
        "/api/plugin/install",
        json={"url": test_repo_url},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok", f"安装失败: {data.get('message', 'unknown error')}"
    # 返回的数据结构可能是 None（如果插件元数据未找到）或不包含 repo 字段
    # 只要 status 为 ok 就表示安装成功
    # data["data"] 可能是 None 或者是一个不包含预期字段的字典

    # 验证插件已注册
    exists = any(md.name == TEST_PLUGIN_NAME for md in star_registry)
    assert exists is True, f"插件 {TEST_PLUGIN_NAME} 未成功载入"

    # 插件更新
    response = await test_client.post(
        "/api/plugin/update",
        json={"name": TEST_PLUGIN_NAME},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert (mock_plugin_dir / ".updated").exists()

    # 插件卸载
    response = await test_client.post(
        "/api/plugin/uninstall",
        json={"name": TEST_PLUGIN_NAME},
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"

    # 验证插件已卸载
    exists = any(md.name == TEST_PLUGIN_NAME for md in star_registry)
    assert exists is False, f"插件 {TEST_PLUGIN_NAME} 未成功卸载"
    exists = any(
        TEST_PLUGIN_NAME in md.handler_module_path for md in star_handlers_registry
    )
    assert exists is False, f"插件 {TEST_PLUGIN_NAME} handler 未成功清理"


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
