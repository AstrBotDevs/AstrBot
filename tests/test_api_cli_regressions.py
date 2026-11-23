"""Behavioral regressions for dashboard binding and offline metrics opt-outs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI

import astrbot.core as core
from astrbot.core.utils import metrics
from astrbot.dashboard import server
from astrbot.dashboard.config_values import resolve_dashboard_host
from astrbot.dashboard.server import AstrBotDashboard
from astrbot.dashboard.services.auth_service import (
    SKIP_DEFAULT_PASSWORD_AUTH_ENV,
    SKIP_DEFAULT_PASSWORD_AUTH_ENV_OLD,
    AuthService,
)


@pytest.fixture
def dashboard_binding(monkeypatch):
    """Exercise the real server run path while replacing OS-facing boundaries."""
    for name in (
        "DASHBOARD_HOST",
        "ASTRBOT_DASHBOARD_HOST",
        "ASTRBOT_HOST",
        "DASHBOARD_PORT",
        "ASTRBOT_DASHBOARD_PORT",
        "ASTRBOT_TEST_PORT",
        "ASTRBOT_TEST_HOST",
        "DASHBOARD_SSL_ENABLE",
        "ASTRBOT_DASHBOARD_SSL_ENABLE",
        SKIP_DEFAULT_PASSWORD_AUTH_ENV,
        SKIP_DEFAULT_PASSWORD_AUTH_ENV_OLD,
    ):
        monkeypatch.delenv(name, raising=False)
    config = {
        "dashboard": {"host": "127.0.0.1", "port": 6185, "ssl": {"enable": False}}
    }
    dashboard = object.__new__(AstrBotDashboard)
    dashboard._webui_fallback = False
    dashboard.enable_webui = False
    dashboard.core_lifecycle = SimpleNamespace(astrbot_config=config)
    dashboard.config = config
    dashboard.asgi_app = FastAPI()
    dashboard.shutdown_trigger = AsyncMock()
    dashboard.check_port_in_use = Mock(return_value=False)
    dashboard._build_dashboard_credentials_display = Mock(return_value="")
    serve = AsyncMock()
    monkeypatch.setattr(server, "serve", serve)
    monkeypatch.setattr(server, "get_local_ip_addresses", lambda: [])
    return dashboard, serve


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_port", "environment", "expected"),
    [
        (6185, {}, 6185),
        ("6185", {}, 6185),
        (" 6185 ", {}, 6185),
        (1, {}, 1),
        (65535, {}, 65535),
        ("${ASTRBOT_TEST_PORT:-6185}", {}, 6185),
        ("${ASTRBOT_TEST_PORT}", {"ASTRBOT_TEST_PORT": "7001"}, 7001),
        (6185, {"ASTRBOT_DASHBOARD_PORT": "7002"}, 7002),
        (6185, {"DASHBOARD_PORT": "7003", "ASTRBOT_DASHBOARD_PORT": "7002"}, 7003),
    ],
)
async def test_dashboard_run_resolves_numeric_ports(
    dashboard_binding, monkeypatch, configured_port, environment, expected
):
    dashboard, serve = dashboard_binding
    dashboard.config["dashboard"]["port"] = configured_port
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    await dashboard.run()

    serve.assert_awaited_once()
    app, config = serve.await_args.args
    assert app is dashboard.asgi_app
    assert config.bind == [f"127.0.0.1:{expected}"]
    assert serve.await_args.kwargs["shutdown_trigger"] is dashboard.shutdown_trigger
    dashboard.check_port_in_use.assert_called_once_with("127.0.0.1", expected)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "port",
    [
        True,
        False,
        0,
        65536,
        -1,
        6185.5,
        "6185.5",
        "1e3",
        "0",
        "65536",
        "${ASTRBOT_TEST_PORT}",
    ],
)
async def test_dashboard_run_rejects_invalid_ports_before_serving(
    dashboard_binding, port
):
    dashboard, serve = dashboard_binding
    dashboard.config["dashboard"]["port"] = port

    with pytest.raises(ValueError):
        await dashboard.run()

    serve.assert_not_awaited()
    dashboard.check_port_in_use.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_host", "environment", "expected_host", "allow_skip"),
    [
        ("127.0.0.1", {}, "127.0.0.1", True),
        ("localhost", {}, "localhost", True),
        (" ::1 ", {}, "::1", True),
        ("0.0.0.0", {}, "0.0.0.0", False),
        ("example.invalid", {}, "example.invalid", False),
        ("127.0.0.1", {"ASTRBOT_HOST": "0.0.0.0"}, "0.0.0.0", False),
        (
            "0.0.0.0",
            {"ASTRBOT_DASHBOARD_HOST": "localhost", "ASTRBOT_HOST": "0.0.0.0"},
            "localhost",
            True,
        ),
        (
            "0.0.0.0",
            {"DASHBOARD_HOST": " ::1 ", "ASTRBOT_DASHBOARD_HOST": "0.0.0.0"},
            "::1",
            True,
        ),
        ("${ASTRBOT_TEST_HOST:-127.0.0.1}", {}, "127.0.0.1", True),
        ("${ASTRBOT_TEST_HOST}", {"ASTRBOT_TEST_HOST": "0.0.0.0"}, "0.0.0.0", False),
    ],
)
async def test_bind_host_and_local_auth_bypass_use_the_same_resolution(
    dashboard_binding,
    monkeypatch,
    configured_host,
    environment,
    expected_host,
    allow_skip,
):
    dashboard, serve = dashboard_binding
    dashboard.config["dashboard"]["host"] = configured_host
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    auth = AuthService(Mock(), dashboard.config)
    assert auth.can_skip_default_password_auth() is False
    monkeypatch.setenv(SKIP_DEFAULT_PASSWORD_AUTH_ENV, "true")

    assert resolve_dashboard_host(dashboard.config["dashboard"]) == expected_host
    assert auth.can_skip_default_password_auth() is allow_skip
    await dashboard.run()

    expected_bind = "[::1]:6185" if expected_host == "::1" else f"{expected_host}:6185"
    assert serve.await_args.args[1].bind == [expected_bind]


@pytest.mark.parametrize("host", [None, True, 1, "", "  ", "${ASTRBOT_TEST_HOST}"])
def test_invalid_hosts_fail_closed_for_password_bypass(
    dashboard_binding, monkeypatch, host
):
    dashboard, _ = dashboard_binding
    dashboard.config["dashboard"]["host"] = host
    monkeypatch.setenv(SKIP_DEFAULT_PASSWORD_AUTH_ENV, "true")
    auth = AuthService(Mock(), dashboard.config)

    with pytest.raises(ValueError):
        resolve_dashboard_host(dashboard.config["dashboard"])
    assert auth.can_skip_default_password_auth() is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", ["ASTRBOT_TEST_MODE", "ASTRBOT_DISABLE_METRICS", "config"]
)
@pytest.mark.parametrize("value", ["1", "true", "yes", "on", " TRUE ", "On"])
async def test_metrics_opt_out_stops_metadata_and_network_even_for_direct_post(
    monkeypatch, name, value
):
    monkeypatch.setenv("ASTRBOT_TEST_MODE", "false")
    monkeypatch.setenv("ASTRBOT_DISABLE_METRICS", "false")
    monkeypatch.setattr(core, "astrbot_config", {"disable_metrics": name == "config"})
    if name != "config":
        monkeypatch.setenv(name, value)
    hostname = Mock()
    installation_id = Mock()
    http_session = Mock()
    save_stats = AsyncMock()
    enqueue_metrics = AsyncMock()
    monkeypatch.setattr(metrics.socket, "gethostname", hostname)
    monkeypatch.setattr(metrics.Metric, "get_installation_id", installation_id)
    monkeypatch.setattr(metrics.aiohttp, "ClientSession", http_session)
    monkeypatch.setattr(metrics.Metric, "_save_platform_stats", save_stats)
    monkeypatch.setattr(metrics.Metric, "_add_pending_metrics", enqueue_metrics)

    assert metrics.Metric._is_disabled() is True
    await metrics.Metric.upload(msg_event_tick=1, adapter_name="test")
    await metrics.Metric._post_metrics({"msg_event_tick": 1})

    hostname.assert_not_called()
    installation_id.assert_not_called()
    http_session.assert_not_called()
    save_stats.assert_not_awaited()
    enqueue_metrics.assert_not_awaited()


@pytest.mark.parametrize("value", ["", "0", "false", "off", "no"])
def test_false_metrics_flags_preserve_configuration_choice(monkeypatch, value):
    monkeypatch.setenv("ASTRBOT_TEST_MODE", value)
    monkeypatch.setenv("ASTRBOT_DISABLE_METRICS", value)
    config = {"disable_metrics": False}
    monkeypatch.setattr(core, "astrbot_config", config)
    assert metrics.Metric._is_disabled() is False
    config["disable_metrics"] = True
    assert metrics.Metric._is_disabled() is True


@pytest.mark.asyncio
async def test_plugin_context_registrations_belong_to_one_context(mock_context):
    import asyncio

    from astrbot.core.star.context import Context

    sibling = Context(
        asyncio.Queue(),
        mock_context._config,
        mock_context._db,
        mock_context.provider_manager,
        mock_context.platform_manager,
        mock_context.conversation_manager,
        mock_context.message_history_manager,
        mock_context.persona_manager,
        mock_context.astrbot_config_mgr,
        mock_context.kb_manager,
        mock_context.cron_manager,
        agent_runtimes={},
    )

    async def first_handler():
        return {"version": 1}

    async def replacement_handler():
        return {"version": 2}

    mock_context.register_web_api("/plugin/status", first_handler, ["GET"], "first")
    mock_context.register_web_api(
        "/plugin/status", replacement_handler, ["GET"], "replacement"
    )
    future = asyncio.get_running_loop().create_future()
    try:
        with pytest.warns(DeprecationWarning, match="background tasks"):
            mock_context.register_task(future, "fixture-owned work")
        assert mock_context.registered_web_apis == [
            ("/plugin/status", replacement_handler, ["GET"], "replacement")
        ]
        assert await mock_context.registered_web_apis[0][1]() == {"version": 2}
        assert mock_context._register_tasks == [future]
        assert sibling.registered_web_apis == []
        assert sibling._register_tasks == []
    finally:
        future.cancel()


@pytest.mark.asyncio
@pytest.mark.parametrize("registration", ["tool", "command"])
async def test_legacy_plugin_registration_accepts_callable_objects(
    mock_context, monkeypatch, registration
):
    import astrbot.core.star.context as context_module
    from astrbot.core.provider.func_tool_manager import FunctionToolManager
    from astrbot.core.star.star_handler import EventType, StarHandlerRegistry

    class AsyncHandler:
        async def __call__(self, **kwargs):
            return "handled"

    handler = AsyncHandler()
    registry = StarHandlerRegistry()
    manager = FunctionToolManager()
    monkeypatch.setattr(context_module, "star_handlers_registry", registry)
    mock_context.provider_manager.llm_tools = manager
    with pytest.warns(DeprecationWarning):
        if registration == "tool":
            mock_context.register_llm_tool("fixture_tool", [], "fixture", handler)
        else:
            mock_context.register_commands("fixture", "hello", "fixture", 1, handler)

    metadata = list(registry)
    assert len(metadata) == 1
    assert metadata[0].handler is handler
    assert metadata[0].handler_name == "AsyncHandler"
    assert metadata[0].handler_full_name == f"{handler.__module__}_AsyncHandler"
    assert await metadata[0].handler() == "handled"
    if registration == "tool":
        tool = manager.get_func("fixture_tool")
        assert tool is not None
        assert tool.handler is handler
        assert metadata[0].event_type == EventType.OnLLMRequestEvent
    else:
        assert metadata[0].event_type == EventType.AdapterMessageEvent
        assert len(metadata[0].event_filters) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_password", ["astrbot", "InitialSecretA7Generated"])
async def test_dashboard_startup_redacts_password_and_clears_temporary_attribute(
    dashboard_binding, astrbot_config, monkeypatch, initial_password
):
    dashboard, serve = dashboard_binding
    astrbot_config["dashboard"].update(
        username="initial-admin",
        host="127.0.0.1",
        port=6185,
        ssl={"enable": False},
    )
    object.__setattr__(
        astrbot_config, "_generated_dashboard_password", initial_password
    )
    dashboard.config = astrbot_config
    dashboard.core_lifecycle.astrbot_config = astrbot_config
    monkeypatch.setattr(
        dashboard,
        "_build_dashboard_credentials_display",
        AstrBotDashboard._build_dashboard_credentials_display.__get__(dashboard),
    )
    logged = Mock()
    monkeypatch.setattr(server.logger, "info", logged)

    await dashboard.run()

    messages = "\n".join(str(call.args) for call in logged.call_args_list)
    assert initial_password not in messages
    assert "Initial username: initial-admin" in messages
    assert "Initial password: [REDACTED - not logged]" in messages
    assert astrbot_config._generated_dashboard_password is None
    assert "Initial password" not in dashboard._build_dashboard_credentials_display()
    serve.assert_awaited_once()
