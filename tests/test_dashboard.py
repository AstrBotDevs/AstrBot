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
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle, LifecycleState
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.star import star_registry
from astrbot.core.star.star_handler import star_handlers_registry
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


def _set_runtime_loading(core_lifecycle: AstrBotCoreLifecycle) -> None:
    core_lifecycle._set_lifecycle_state(LifecycleState.CORE_READY)
    core_lifecycle.runtime_ready_event.clear()
    core_lifecycle.runtime_failed_event.clear()
    core_lifecycle.runtime_bootstrap_error = None


def _restore_runtime_ready(core_lifecycle: AstrBotCoreLifecycle) -> None:
    core_lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_READY)
    core_lifecycle.runtime_ready_event.set()
    core_lifecycle.runtime_failed_event.clear()
    core_lifecycle.runtime_bootstrap_error = None


def _set_runtime_failed(
    core_lifecycle: AstrBotCoreLifecycle,
    message: str = "Runtime bootstrap failed.",
) -> None:
    core_lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_FAILED)
    core_lifecycle.runtime_ready_event.clear()
    core_lifecycle.runtime_failed_event.set()
    core_lifecycle.runtime_bootstrap_error = RuntimeError(message)


def _assert_runtime_loading_response(
    data: dict,
    state: LifecycleState = LifecycleState.CORE_READY,
) -> None:
    assert data == {
        "status": "error",
        "message": "Runtime is still loading. Please try again shortly.",
        "data": {
            "state": state.value,
            "ready": False,
            "failed": False,
            "failure_message": None,
        },
    }


def _assert_runtime_failed_response(
    data: dict,
    message: str | None,
    state: SimpleNamespace | LifecycleState = LifecycleState.RUNTIME_FAILED,
) -> None:
    assert data == {
        "status": "error",
        "message": "Runtime bootstrap failed. Please check logs and retry.",
        "data": {
            "state": state.value,
            "ready": False,
            "failed": True,
            "failure_message": message,
        },
    }


def _build_plugin_upload_files() -> dict:
    return {
        "files": {
            "file": FileStorage(
                stream=io.BytesIO(b"fake-plugin-archive"),
                filename="demo-plugin.zip",
                content_type="application/zip",
            )
        }
    }


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
async def test_runtime_status_reports_current_state(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()

    response = await test_client.get(
        "/api/stat/runtime-status",
        headers=authenticated_header,
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert data["data"]["state"] == LifecycleState.RUNTIME_READY.value
    assert data["data"]["ready"] is True
    assert data["data"]["failed"] is False
    assert data["data"]["failure_message"] is None

    _set_runtime_loading(core_lifecycle_td)
    try:
        response = await test_client.get(
            "/api/stat/runtime-status",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["state"] == LifecycleState.CORE_READY.value
        assert data["data"]["ready"] is False
        assert data["data"]["failed"] is False
        assert data["data"]["failure_message"] is None
    finally:
        _restore_runtime_ready(core_lifecycle_td)

    _set_runtime_failed(core_lifecycle_td, "bootstrap exploded during provider init")
    try:
        response = await test_client.get(
            "/api/stat/runtime-status",
            headers=authenticated_header,
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"
        assert data["data"]["state"] == "runtime_failed"
        assert data["data"]["ready"] is False
        assert data["data"]["failed"] is True
        assert (
            data["data"]["failure_message"] == "bootstrap exploded during provider init"
        )
    finally:
        _restore_runtime_ready(core_lifecycle_td)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "headers", "misleading_field"),
    [
        ("/api/stat/get", "auth", "platform"),
        ("/api/stat/start-time", None, "start_time"),
    ],
    ids=["stat-get", "stat-start-time"],
)
async def test_stat_endpoints_return_503_while_runtime_loading(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    path: str,
    headers: str | None,
    misleading_field: str,
):
    test_client = app.test_client()
    request_kwargs = {}
    if headers == "auth":
        request_kwargs["headers"] = authenticated_header

    _set_runtime_loading(core_lifecycle_td)
    try:
        response = await test_client.get(path, **request_kwargs)
        assert response.status_code == 503
        data = await response.get_json()
        _assert_runtime_loading_response(data)
        assert misleading_field not in data["data"]
    finally:
        _restore_runtime_ready(core_lifecycle_td)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "headers", "misleading_field"),
    [
        ("/api/stat/get", "auth", "platform"),
        ("/api/stat/start-time", None, "start_time"),
    ],
    ids=["stat-get", "stat-start-time"],
)
async def test_stat_endpoints_return_failure_aware_503_after_bootstrap_failure(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    path: str,
    headers: str | None,
    misleading_field: str,
):
    test_client = app.test_client()
    request_kwargs = {}
    if headers == "auth":
        request_kwargs["headers"] = authenticated_header

    _set_runtime_failed(core_lifecycle_td, "runtime bootstrap failed in plugin reload")
    try:
        response = await test_client.get(path, **request_kwargs)
        assert response.status_code == 503
        data = await response.get_json()
        _assert_runtime_failed_response(
            data,
            (
                None
                if path == "/api/stat/start-time"
                else "runtime bootstrap failed in plugin reload"
            ),
        )
        assert misleading_field not in data["data"]
    finally:
        _restore_runtime_ready(core_lifecycle_td)


@pytest.mark.asyncio
async def test_public_start_time_failure_response_does_not_leak_bootstrap_error(
    app: Quart,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()

    _set_runtime_failed(core_lifecycle_td, "provider api key leaked in stacktrace")
    try:
        response = await test_client.get("/api/stat/start-time")
        assert response.status_code == 503
        data = await response.get_json()
        assert data == {
            "status": "error",
            "message": "Runtime bootstrap failed. Please check logs and retry.",
            "data": {
                "state": LifecycleState.RUNTIME_FAILED.value,
                "ready": False,
                "failed": True,
                "failure_message": None,
            },
        }
    finally:
        _restore_runtime_ready(core_lifecycle_td)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "request_kwargs_factory", "guard_attr"),
    [
        ("get", "/api/plugin/get", lambda: {}, "context.get_all_stars"),
        (
            "get",
            "/api/plugin/source/get-failed-plugins",
            lambda: {},
            None,
        ),
        (
            "post",
            "/api/plugin/install",
            lambda: {"json": {"url": "https://example.com/plugin"}},
            "install_plugin",
        ),
        (
            "post",
            "/api/plugin/install-upload",
            _build_plugin_upload_files,
            "install_plugin_from_file",
        ),
        (
            "post",
            "/api/plugin/update",
            lambda: {"json": {"name": "demo-plugin"}},
            "update_plugin",
        ),
        (
            "post",
            "/api/plugin/update-all",
            lambda: {"json": {"names": ["demo-plugin"]}},
            "update_plugin",
        ),
        (
            "post",
            "/api/plugin/uninstall",
            lambda: {"json": {"name": "demo-plugin"}},
            "uninstall_plugin",
        ),
        (
            "post",
            "/api/plugin/uninstall-failed",
            lambda: {"json": {"dir_name": "demo-plugin"}},
            "uninstall_failed_plugin",
        ),
        (
            "post",
            "/api/plugin/off",
            lambda: {"json": {"name": "demo-plugin"}},
            "turn_off_plugin",
        ),
        (
            "post",
            "/api/plugin/on",
            lambda: {"json": {"name": "demo-plugin"}},
            "turn_on_plugin",
        ),
        (
            "post",
            "/api/plugin/reload",
            lambda: {"json": {"name": "demo-plugin"}},
            "reload",
        ),
        (
            "post",
            "/api/plugin/reload-failed",
            lambda: {"json": {"dir_name": "demo-plugin"}},
            "reload_failed_plugin",
        ),
        (
            "get",
            "/api/plugin/readme?name=demo-plugin",
            lambda: {},
            "context.get_all_stars",
        ),
        (
            "get",
            "/api/plugin/changelog?name=demo-plugin",
            lambda: {},
            "context.get_all_stars",
        ),
    ],
    ids=[
        "get",
        "get-failed-plugins",
        "install",
        "install-upload",
        "update",
        "update-all",
        "uninstall",
        "uninstall-failed",
        "off",
        "on",
        "reload",
        "reload-failed",
        "readme",
        "changelog",
    ],
)
async def test_plugin_api_returns_503_while_runtime_loading(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    method: str,
    path: str,
    request_kwargs_factory,
    guard_attr: str,
):
    test_client = app.test_client()
    plugin_manager = core_lifecycle_td.plugin_manager
    assert plugin_manager is not None

    if guard_attr == "context.get_all_stars":
        monkeypatch.setattr(
            plugin_manager.context,
            "get_all_stars",
            lambda: (_ for _ in ()).throw(
                AssertionError("plugin state should not be read")
            ),
        )
    elif guard_attr is not None:
        monkeypatch.setattr(
            plugin_manager,
            guard_attr,
            AsyncMock(side_effect=AssertionError(f"{guard_attr} should not be called")),
        )

    _set_runtime_loading(core_lifecycle_td)
    try:
        request_kwargs = request_kwargs_factory()
        response = await getattr(test_client, method)(
            path,
            headers=authenticated_header,
            **request_kwargs,
        )
        assert response.status_code == 503
        data = await response.get_json()
        _assert_runtime_loading_response(data)
    finally:
        _restore_runtime_ready(core_lifecycle_td)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "request_kwargs_factory", "guard_attr"),
    [
        ("get", "/api/plugin/get", lambda: {}, "context.get_all_stars"),
        (
            "get",
            "/api/plugin/source/get-failed-plugins",
            lambda: {},
            None,
        ),
        (
            "post",
            "/api/plugin/install",
            lambda: {"json": {"url": "https://example.com/plugin"}},
            "install_plugin",
        ),
    ],
    ids=["get", "get-failed-plugins", "install"],
)
async def test_plugin_api_returns_failed_response_after_runtime_bootstrap_failure(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    method: str,
    path: str,
    request_kwargs_factory,
    guard_attr: str,
):
    test_client = app.test_client()
    plugin_manager = core_lifecycle_td.plugin_manager
    assert plugin_manager is not None

    if guard_attr == "context.get_all_stars":
        monkeypatch.setattr(
            plugin_manager.context,
            "get_all_stars",
            lambda: (_ for _ in ()).throw(
                AssertionError("plugin state should not be read")
            ),
        )
    elif guard_attr is not None:
        monkeypatch.setattr(
            plugin_manager,
            guard_attr,
            AsyncMock(side_effect=AssertionError(f"{guard_attr} should not be called")),
        )

    _set_runtime_failed(core_lifecycle_td, "plugin bootstrap failed")
    try:
        request_kwargs = request_kwargs_factory()
        response = await getattr(test_client, method)(
            path,
            headers=authenticated_header,
            **request_kwargs,
        )
        assert response.status_code == 503
        data = await response.get_json()
        _assert_runtime_failed_response(data, "plugin bootstrap failed")
    finally:
        _restore_runtime_ready(core_lifecycle_td)


@pytest.mark.asyncio
async def test_plugin_web_route_returns_503_while_runtime_loading(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()
    route_called = False
    star_context = core_lifecycle_td.star_context
    assert star_context is not None

    async def dummy_plugin_route(*args, **kwargs):
        nonlocal route_called
        route_called = True
        return {"status": "ok", "message": None, "data": {"called": True}}

    registered_web_apis = star_context.registered_web_apis
    original_registered_web_apis = list(registered_web_apis)
    registered_web_apis[:] = [
        ("/runtime-guard-test", dummy_plugin_route, ["GET"], "runtime guard test"),
    ]

    _set_runtime_loading(core_lifecycle_td)
    try:
        response = await test_client.get(
            "/api/plug/runtime-guard-test",
            headers=authenticated_header,
        )
        assert response.status_code == 503
        data = await response.get_json()
        _assert_runtime_loading_response(data)
        assert route_called is False
    finally:
        registered_web_apis[:] = original_registered_web_apis
        _restore_runtime_ready(core_lifecycle_td)


@pytest.mark.asyncio
async def test_plugin_web_route_returns_failed_response_after_runtime_bootstrap_failure(
    app: Quart,
    authenticated_header: dict,
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    test_client = app.test_client()
    route_called = False
    star_context = core_lifecycle_td.star_context
    assert star_context is not None

    async def dummy_plugin_route(*args, **kwargs):
        nonlocal route_called
        route_called = True
        return {"status": "ok", "message": None, "data": {"called": True}}

    registered_web_apis = star_context.registered_web_apis
    original_registered_web_apis = list(registered_web_apis)
    registered_web_apis[:] = [
        (
            "/runtime-failed-guard-test",
            dummy_plugin_route,
            ["GET"],
            "runtime guard test",
        ),
    ]

    _set_runtime_failed(core_lifecycle_td, "plugin web runtime bootstrap failed")
    try:
        response = await test_client.get(
            "/api/plug/runtime-failed-guard-test",
            headers=authenticated_header,
        )
        assert response.status_code == 503
        data = await response.get_json()
        _assert_runtime_failed_response(
            data,
            "plugin web runtime bootstrap failed",
        )
        assert route_called is False
    finally:
        registered_web_apis[:] = original_registered_web_apis
        _restore_runtime_ready(core_lifecycle_td)


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
    plugin_manager = core_lifecycle_td.plugin_manager
    assert plugin_manager is not None
    plugin_store_path = plugin_manager.plugin_store_path
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
    monkeypatch.setattr(plugin_manager.updator, "install", mock_install)
    monkeypatch.setattr(plugin_manager.updator, "update", mock_update)

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
