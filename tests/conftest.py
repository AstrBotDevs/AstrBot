"""
AstrBot test configuration

Shared pytest fixtures with isolated state and offline execution.
"""

import asyncio
import copy
import http.client
import ipaddress
import json
import os
import socket
import sys
from asyncio import Queue
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import httpx
import pytest
import pytest_asyncio

# Shared factories live in tests/fixtures/helpers.py.

# Make the project package available before collecting tests.
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configure the test environment before importing project code.

# Nested conftests can import astrbot.core before pytest_configure runs.
# Its global config reads and may write cmd_config.json during import.
_test_root = TemporaryDirectory(prefix="astrbot-pytest-")
_test_env = pytest.MonkeyPatch()
_test_env.setenv("ASTRBOT_ROOT", _test_root.name)
_test_env.setenv("TESTING", "true")
_test_env.setenv("ASTRBOT_TEST_MODE", "true")

# A loopback proxy can forward to the public internet, so it is not an offline boundary.
for _environment_key in tuple(os.environ):
    if _environment_key.lower().endswith("_proxy"):
        _test_env.delenv(_environment_key)

# Protect collection as well as test execution: project imports can start services.
_socket_connect = socket.socket.connect
_socket_connect_ex = socket.socket.connect_ex
_socket_sendto = socket.socket.sendto
_socket_getaddrinfo = socket.getaddrinfo


def _require_loopback(host: str | bytes | None) -> None:
    """Reject external destinations before DNS resolution or socket I/O.

    Args:
        host: Hostname or numeric address requested by a test.

    Raises:
        RuntimeError: If the destination is outside the local machine.
    """
    if host is None:
        return
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host.lower().rstrip(".") == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if address.is_loopback or (
            isinstance(address, ipaddress.IPv6Address)
            and address.ipv4_mapped is not None
            and address.ipv4_mapped.is_loopback
        ):
            return
    raise RuntimeError(f"External network access is disabled in tests: {host}")


def _local_connect(sock, address):
    """Allow Unix sockets and loopback TCP connections."""
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        _require_loopback(address[0])
    return _socket_connect(sock, address)


def _local_connect_ex(sock, address):
    """Apply the same destination policy to non-raising socket connections."""
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        _require_loopback(address[0])
    return _socket_connect_ex(sock, address)


def _local_sendto(sock, data, *args):
    """Allow datagrams only to explicit local destinations."""
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        _require_loopback(args[-1][0])
    return _socket_sendto(sock, data, *args)


def _local_getaddrinfo(host, *args, **kwargs):
    """Resolve only local hosts, including passive listener lookups."""
    _require_loopback(host)
    return _socket_getaddrinfo(host, *args, **kwargs)


_test_env.setattr(socket.socket, "connect", _local_connect)
_test_env.setattr(socket.socket, "connect_ex", _local_connect_ex)
_test_env.setattr(socket.socket, "sendto", _local_sendto)
_test_env.setattr(socket, "getaddrinfo", _local_getaddrinfo)


def _local_resolver(resolver):
    """Wrap each legacy DNS entry point with the test destination policy."""

    def resolve(host, *args, **kwargs):
        _require_loopback(host)
        return resolver(host, *args, **kwargs)

    return resolve


for _resolver_name in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
    _test_env.setattr(
        socket, _resolver_name, _local_resolver(getattr(socket, _resolver_name))
    )

if hasattr(socket.socket, "sendmsg"):
    _socket_sendmsg = socket.socket.sendmsg

    def _local_sendmsg(sock, buffers, ancdata=(), flags=0, address=None):
        """Validate explicit datagram destinations for scatter/gather sends."""
        if address is not None and sock.family in (socket.AF_INET, socket.AF_INET6):
            _require_loopback(address[0])
        if address is None:
            return _socket_sendmsg(sock, buffers, ancdata, flags)
        return _socket_sendmsg(sock, buffers, ancdata, flags, address)

    _test_env.setattr(socket.socket, "sendmsg", _local_sendmsg)


_httpx_request = httpx.HTTPTransport.handle_request
_httpx_async_request = httpx.AsyncHTTPTransport.handle_async_request
_aiohttp_connect = aiohttp.TCPConnector.connect
_http_connect = http.client.HTTPConnection.connect


def _local_httpx_request(transport, request):
    """Check the destination before a real transport can tunnel through a proxy."""
    _require_loopback(request.url.host)
    return _httpx_request(transport, request)


async def _local_httpx_async_request(transport, request):
    """Keep MockTransport and ASGITransport usable while guarding actual HTTP I/O."""
    _require_loopback(request.url.host)
    return await _httpx_async_request(transport, request)


async def _local_aiohttp_connect(connector, request, *args, **kwargs):
    """Validate the target URL before aiohttp selects a direct or proxied socket."""
    _require_loopback(request.url.host)
    return await _aiohttp_connect(connector, request, *args, **kwargs)


def _local_http_connect(connection):
    """Guard the target behind an HTTP CONNECT tunnel as well as direct requests."""
    _require_loopback(connection._tunnel_host or connection.host)
    return _http_connect(connection)


_test_env.setattr(httpx.HTTPTransport, "handle_request", _local_httpx_request)
_test_env.setattr(
    httpx.AsyncHTTPTransport, "handle_async_request", _local_httpx_async_request
)
_test_env.setattr(aiohttp.TCPConnector, "connect", _local_aiohttp_connect)
_test_env.setattr(http.client.HTTPConnection, "connect", _local_http_connect)


if find_spec("httpx2") is not None:
    # SDKs may use HTTPX2 independently of HTTPX. Broken installed imports must fail.
    import httpx2

    _httpx2_request = httpx2.HTTPTransport.handle_request
    _httpx2_async_request = httpx2.AsyncHTTPTransport.handle_async_request

    def _local_httpx2_request(transport, request):
        """Validate the target before HTTPX2 can forward it through a proxy."""
        _require_loopback(request.url.host)
        return _httpx2_request(transport, request)

    async def _local_httpx2_async_request(transport, request):
        """Guard real async HTTPX2 I/O while preserving in-process transports."""
        _require_loopback(request.url.host)
        return await _httpx2_async_request(transport, request)

    _test_env.setattr(httpx2.HTTPTransport, "handle_request", _local_httpx2_request)
    _test_env.setattr(
        httpx2.AsyncHTTPTransport, "handle_async_request", _local_httpx2_async_request
    )


# ============================================================
# Test collection and ordering
# ============================================================


def pytest_collection_modifyitems(session, config, items):  # noqa: ARG001
    """Order unit tests before integration tests and apply the selected profile."""
    unit_tests = []
    integration_tests = []
    deselected = []
    profile = config.getoption("--test-profile") or os.environ.get(
        "ASTRBOT_TEST_PROFILE", "all"
    )

    for item in items:
        item_path = Path(str(item.path))
        is_integration = "integration" in item_path.parts

        if is_integration:
            if item.get_closest_marker("integration") is None:
                item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.tier_d)
            integration_tests.append(item)
        else:
            if item.get_closest_marker("unit") is None:
                item.add_marker(pytest.mark.unit)
            if any(
                item.get_closest_marker(marker) is not None
                for marker in ("platform", "provider", "slow")
            ):
                item.add_marker(pytest.mark.tier_c)
            unit_tests.append(item)

    # Run unit tests before integration tests.
    ordered_items = unit_tests + integration_tests
    if profile == "blocking":
        selected_items = []
        for item in ordered_items:
            if item.get_closest_marker("tier_c") or item.get_closest_marker("tier_d"):
                deselected.append(item)
            else:
                selected_items.append(item)
        if deselected:
            config.hook.pytest_deselected(items=deselected)
        items[:] = selected_items
        return

    items[:] = ordered_items


def pytest_addoption(parser):
    """Register the optional test profile selection."""
    parser.addoption(
        "--test-profile",
        action="store",
        default=None,
        choices=["all", "blocking"],
        help="Select test profile. 'blocking' excludes auto-classified tier_c/tier_d tests.",
    )


def pytest_configure(config):
    """Register markers and deterministic session cleanup."""
    config.add_cleanup(_test_root.cleanup)
    config.add_cleanup(_test_env.undo)

    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow tests")
    config.addinivalue_line("markers", "platform: Platform adapter tests")
    config.addinivalue_line("markers", "provider: LLM provider tests")
    config.addinivalue_line("markers", "db: Database tests")
    config.addinivalue_line("markers", "tier_c: C-tier tests (optional / non-blocking)")
    config.addinivalue_line("markers", "tier_d: D-tier tests (extended / integration)")


def pytest_sessionfinish():
    """Release pooled connections before Windows removes the isolated data root."""
    if core := sys.modules.get("astrbot.core"):

        async def close_runtime_resources():
            try:
                await core.sp.close()
            finally:
                await core.db_helper.engine.dispose()

        asyncio.run(close_runtime_resources())


# ============================================================
# Temporary paths and files
# ============================================================


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Return the current test temporary directory."""
    return tmp_path


@pytest.fixture
def require_symlink(tmp_path: Path) -> Path:
    """Skip the test when symlink creation is denied by the OS.

    Windows only allows symbolic links with admin or developer-mode
    privileges, so tests that build symlink fixtures cannot run there.
    """
    probe = tmp_path / ".symlink_probe"
    try:
        probe.symlink_to(tmp_path)
    except OSError as exc:
        # 1314 (ERROR_PRIVILEGE_NOT_HELD): Windows requires admin or
        # developer mode. Anything else is a real error and must fail.
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("symlink creation is not permitted on this platform")
        raise
    probe.unlink()
    return tmp_path


@pytest.fixture
def event_queue() -> Queue:
    """Create a shared asyncio queue fixture for tests."""
    return Queue()


@pytest.fixture
def platform_settings() -> dict:
    """Create a shared empty platform settings fixture for adapter tests."""
    return {}


@pytest.fixture
def temp_data_dir(temp_dir: Path) -> Path:
    """Create the data directories used by the current test."""
    data_dir = temp_dir / "data"
    data_dir.mkdir()

    # Create the required data subdirectories.
    (data_dir / "config").mkdir()
    (data_dir / "plugins").mkdir()
    (data_dir / "temp").mkdir()
    (data_dir / "attachments").mkdir()

    return data_dir


@pytest.fixture
def temp_config_file(temp_data_dir: Path) -> Path:
    """Write a configuration file for the current test."""
    config_path = temp_data_dir / "config" / "cmd_config.json"
    default_config = {
        "provider": [],
        "platform": [],
        "provider_settings": {},
        "default_personality": None,
        "timezone": "Asia/Shanghai",
    }
    config_path.write_text(json.dumps(default_config, indent=2), encoding="utf-8")
    return config_path


@pytest.fixture
def temp_db_file(temp_data_dir: Path) -> Path:
    """Return an isolated SQLite database path."""
    return temp_data_dir / "test.db"


# ============================================================
# Mock Fixtures
# ============================================================


@pytest.fixture
def mock_provider():
    """Create a provider double with async boundaries."""
    provider = MagicMock()
    provider.provider_config = {
        "id": "test-provider",
        "type": "openai_chat_completion",
        "model": "gpt-4o-mini",
    }
    provider.get_model = MagicMock(return_value="gpt-4o-mini")
    provider.text_chat = AsyncMock()
    provider.text_chat_stream = AsyncMock()
    provider.terminate = AsyncMock()
    return provider


@pytest.fixture
def mock_platform():
    """Create a platform double with async boundaries."""
    platform = MagicMock()
    platform.platform_name = "test_platform"
    platform.platform_meta = MagicMock()
    platform.platform_meta.support_proactive_message = False
    platform.send_message = AsyncMock()
    platform.terminate = AsyncMock()
    return platform


@pytest.fixture
def mock_conversation():
    """Create a conversation record for the current test."""
    from astrbot.core.db.po import ConversationV2

    return ConversationV2(
        conversation_id="test-conv-id",
        platform_id="test_platform",
        user_id="test_user",
        content=[],
        persona_id=None,
    )


@pytest.fixture
def mock_event():
    """Create a message event double for the current test."""
    event = MagicMock()
    event.unified_msg_origin = "test_umo"
    event.session_id = "test_session"
    event.message_str = "Hello, world!"
    event.message_obj = MagicMock()
    event.message_obj.message = []
    event.message_obj.sender = MagicMock()
    event.message_obj.sender.user_id = "test_user"
    event.message_obj.sender.nickname = "Test User"
    event.message_obj.group_id = None
    event.message_obj.group = None
    event.get_platform_name = MagicMock(return_value="test_platform")
    event.get_platform_id = MagicMock(return_value="test_platform")
    event.get_group_id = MagicMock(return_value=None)
    event.get_extra = MagicMock(return_value=None)
    event.set_extra = MagicMock()
    event.trace = MagicMock()
    event.platform_meta = MagicMock()
    event.platform_meta.support_proactive_message = False
    return event


# ============================================================
# Configuration fixtures
# ============================================================


@pytest.fixture
def astrbot_config(temp_config_file: Path):
    """Create a configuration with independent defaults and storage."""
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.config.default import DEFAULT_CONFIG

    return AstrBotConfig(
        str(temp_config_file), default_config=copy.deepcopy(DEFAULT_CONFIG)
    )


@pytest.fixture(scope="module")
def dashboard_test_config(tmp_path_factory):
    """Create a separate persisted configuration for each dashboard test module."""
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.config.default import DEFAULT_CONFIG

    path = tmp_path_factory.mktemp("dashboard-config") / "cmd_config.json"
    return AstrBotConfig(str(path), default_config=copy.deepcopy(DEFAULT_CONFIG))


@pytest.fixture
def main_agent_build_config():
    """Create the built-in runtime main-agent configuration."""
    from astrbot.core.astr_agent_runtime.main_agent import MainAgentBuildConfig

    return MainAgentBuildConfig(
        tool_call_timeout=60,
        tool_schema_mode="full",
        provider_wake_prefix="",
        streaming_response=True,
        sanitize_context_by_modalities=False,
        kb_agentic_mode=False,
        file_extract_enabled=False,
        context_limit_reached_strategy="truncate_by_turns",
        llm_safety_mode=True,
        computer_use_runtime="local",
        add_cron_tools=True,
    )


# ============================================================
# Database fixtures
# ============================================================


@pytest_asyncio.fixture
async def temp_db(temp_db_file: Path):
    """Create a database and always dispose its connection pool."""
    from astrbot.core.db.sqlite import SQLiteDatabase

    db = SQLiteDatabase(str(temp_db_file))
    try:
        yield db
    finally:
        await db.engine.dispose()
        if temp_db_file.exists():
            temp_db_file.unlink()


# ============================================================
# Context Fixtures
# ============================================================


@pytest_asyncio.fixture
async def mock_context(
    astrbot_config,
    temp_db,
    mock_provider,
    mock_platform,
):
    """Create a plugin context with fixture-owned dependencies."""
    from asyncio import Queue

    from astrbot.core.star.context import Context

    event_queue = Queue()

    provider_manager = MagicMock()
    provider_manager.get_using_provider = MagicMock(return_value=mock_provider)
    provider_manager.get_using_provider_async = AsyncMock(
        side_effect=lambda *args, **kwargs: provider_manager.get_using_provider(
            *args,
            **kwargs,
        )
    )
    provider_manager.get_provider_by_id = MagicMock(return_value=mock_provider)

    platform_manager = MagicMock()
    conversation_manager = MagicMock()
    message_history_manager = MagicMock()
    persona_manager = MagicMock()
    persona_manager.personas_v3 = []
    astrbot_config_mgr = MagicMock()
    knowledge_base_manager = MagicMock()
    cron_manager = MagicMock()

    context = Context(
        event_queue,
        astrbot_config,
        temp_db,
        provider_manager,
        platform_manager,
        conversation_manager,
        message_history_manager,
        persona_manager,
        astrbot_config_mgr,
        knowledge_base_manager,
        cron_manager,
        agent_runtimes={},
    )

    return context


# ============================================================
# Provider Request Fixtures
# ============================================================


@pytest.fixture
def provider_request():
    """Create an independent provider request."""
    from astrbot.core.provider.entities import ProviderRequest

    return ProviderRequest(
        prompt="Hello",
        session_id="test_session",
        image_urls=[],
        contexts=[],
        system_prompt="You are a helpful assistant.",
    )


# ============================================================
# Explicit integration prerequisites
# ============================================================


def pytest_runtest_setup(item):
    """Check credentials only for explicitly marked integration tests."""
    if item.get_closest_marker("integration") is None:
        return

    # Only integration tests can require live provider credentials.
    if item.get_closest_marker("provider"):
        if not os.environ.get("TEST_PROVIDER_API_KEY"):
            pytest.skip("TEST_PROVIDER_API_KEY not set")

    # Explicit platform integration tests declare their prerequisites.
    if item.get_closest_marker("platform"):
        required_platform = None
        marker = item.get_closest_marker("platform")
        if marker and marker.args:
            required_platform = marker.args[0]

        if required_platform and not os.environ.get(
            f"TEST_{required_platform.upper()}_ENABLED"
        ):
            pytest.skip(f"TEST_{required_platform.upper()}_ENABLED not set")


@pytest_asyncio.fixture
async def database(temp_db):
    """Provide an initialized SQLite database for event-storage tests."""
    await temp_db.initialize()
    return temp_db


@pytest.fixture(autouse=True)
def isolated_runtime_config(monkeypatch, tmp_path: Path):
    """Give each test a data root and restore the shared configuration.

    Args:
        monkeypatch: Fixture that restores environment and attribute changes.
        tmp_path: Temporary directory owned by the current test.
    """
    root = tmp_path / "astrbot"
    for directory in ("config", "plugins", "temp", "attachments", "skills"):
        (root / "data" / directory).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ASTRBOT_ROOT", str(root))
    core = sys.modules.get("astrbot.core")
    if core is None:
        yield
        return
    config = core.astrbot_config
    original = copy.deepcopy(dict(config))
    original_path = config.config_path
    object.__setattr__(config, "config_path", str(root / "data" / "cmd_config.json"))
    try:
        yield
    finally:
        config.clear()
        config.update(original)
        object.__setattr__(config, "config_path", original_path)


@pytest_asyncio.fixture
async def shared_preferences(database, tmp_path: Path):
    """Provide real preference storage with fixture-scoped lifecycle.

    Args:
        database: Initialized SQLite database owned by the current test.
        tmp_path: Temporary directory used for legacy preference files.
    """
    from astrbot.core.utils.shared_preferences import SharedPreferences

    preferences = SharedPreferences(
        db_helper=database,
        json_storage_path=str(tmp_path / "shared_preferences.json"),
    )
    await preferences.initialize()
    try:
        yield preferences
    finally:
        await preferences.close()


@pytest.fixture(scope="session")
def require_linux_network_namespace() -> None:
    """Probe the real backend once before integrations that deny network access."""
    import shutil
    import subprocess

    if not sys.platform.startswith("linux"):
        return
    bubblewrap = shutil.which("bwrap")
    true_program = shutil.which("true")
    if bubblewrap is None or true_program is None:
        pytest.skip("Linux network isolation requires bubblewrap and true")
    command = [
        bubblewrap,
        "--die-with-parent",
        "--unshare-all",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--",
        true_program,
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=5, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail("Bubblewrap network namespace capability probe exceeded 5 seconds")
    if result.returncode == 0:
        return
    error = result.stderr.decode("utf-8", errors="replace").strip()
    unavailable = {
        "bwrap: loopback: Failed to create NETLINK_ROUTE socket: Operation not permitted",
        "bwrap: Creating new namespace failed: Operation not permitted",
    }
    if result.returncode == 1 and error in unavailable:
        pytest.skip(f"Linux network namespace is unavailable: {error}")
    pytest.fail(
        f"Unexpected bubblewrap capability probe failure "
        f"(exit {result.returncode}): {error}"
    )
