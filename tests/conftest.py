"""
AstrBot 测试配置

提供共享的 pytest fixtures 和测试工具。
"""

import asyncio
import json
import os
import sys
import threading
from asyncio import Queue
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# 使用 tests/fixtures/helpers.py 中的共享工具函数，避免重复定义

# 将项目根目录添加到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest_plugins = [
    "tests.unit.dashboard.dashboard_lifecycle_support",
    "tests.unit.dashboard.fastapi_v1_support",
]

# 设置测试环境变量
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("ASTRBOT_TEST_MODE", "true")
os.environ.setdefault("ASTRBOT_DISABLE_METRICS", "1")


@pytest.fixture(autouse=True)
def reset_global_network_config():
    """Keep explicit proxy routing isolated between tests."""
    from astrbot.core.utils.proxy_route import set_global_network_config

    set_global_network_config(http_proxy="", no_proxy=[])
    yield
    set_global_network_config(http_proxy="", no_proxy=[])


# ============================================================
# 测试收集和排序
# ============================================================


TEST_PROFILES = frozenset({"all", "blocking"})
NON_BLOCKING_MARKERS = frozenset({"slow", "integration", "live"})


def get_test_profile(config) -> str:
    """Return the selected test profile and reject invalid environment values."""
    profile = config.getoption("--test-profile")
    if profile is None:
        profile = os.environ.get("ASTRBOT_TEST_PROFILE", "all")
    if profile not in TEST_PROFILES:
        raise pytest.UsageError(
            f"Unknown test profile {profile!r}; expected one of {sorted(TEST_PROFILES)}"
        )
    return profile


def _relative_test_path(item) -> Path:
    """Return a collected item's path relative to the repository when possible."""
    item_path = Path(str(item.path)).resolve()
    try:
        return item_path.relative_to(PROJECT_ROOT)
    except ValueError:
        return item_path


def _is_integration_path(relative_path: Path) -> bool:
    """Return whether a test lives in an integration-owned directory."""
    parts = relative_path.parts
    return (
        len(parts) >= 2 and parts[0] == "tests" and parts[1] in {"integration", "e2e"}
    )


def _is_unit_path(relative_path: Path) -> bool:
    """Return whether a test lives in a unit-owned directory."""
    parts = relative_path.parts
    return len(parts) >= 2 and (
        (parts[0] == "tests" and parts[1] in {"unit", "agent"})
        or (parts[0] == "docs" and parts[1] == "tests")
    )


def pytest_collection_modifyitems(session, config, items):  # noqa: ARG001
    """Classify tests and select the requested profile."""
    profile = get_test_profile(config)

    for item in items:
        relative_path = _relative_test_path(item)
        is_integration = _is_integration_path(relative_path) or (
            item.get_closest_marker("integration") is not None
        )

        if is_integration and item.get_closest_marker("integration") is None:
            item.add_marker(pytest.mark.integration)
        elif _is_unit_path(relative_path) and item.get_closest_marker("unit") is None:
            item.add_marker(pytest.mark.unit)

        if not any(
            item.get_closest_marker(marker) is not None
            for marker in NON_BLOCKING_MARKERS
        ):
            item.add_marker(pytest.mark.blocking)

    if profile != "blocking":
        return

    selected_items = []
    deselected_items = []
    for item in items:
        if item.get_closest_marker("blocking") is None:
            deselected_items.append(item)
        else:
            selected_items.append(item)

    if deselected_items:
        config.hook.pytest_deselected(items=deselected_items)
    items[:] = selected_items


def pytest_addoption(parser):
    """Add test profile selection."""
    parser.addoption(
        "--test-profile",
        action="store",
        default=None,
        choices=sorted(TEST_PROFILES),
        help="Select the test profile. 'blocking' excludes slow/integration/live tests.",
    )


def pytest_configure(config):
    """Register repository test markers."""
    config.addinivalue_line("markers", "unit: isolated unit or component test")
    config.addinivalue_line("markers", "blocking: deterministic blocking-gate test")
    config.addinivalue_line("markers", "integration: integration or end-to-end test")
    config.addinivalue_line("markers", "slow: test with a larger execution budget")
    config.addinivalue_line("markers", "platform: platform-domain test")
    config.addinivalue_line("markers", "provider: provider-domain test")
    config.addinivalue_line(
        "markers",
        "live: real network, vendor SDK, or required external secret",
    )


def pytest_runtest_call(item) -> None:
    """Record live threads after fixture setup and before a test body runs."""
    item._astrbot_test_threads = set(threading.enumerate())  # noqa: SLF001


def _is_anyio_worker_thread(thread: threading.Thread) -> bool:
    """Return whether a thread belongs to AnyIO's process-wide worker pool."""
    thread_type = type(thread)
    return (
        thread.name == "AnyIO worker thread"
        and thread_type.__module__ == "anyio._backends._asyncio"
        and thread_type.__qualname__ == "WorkerThread"
    )


def _is_aiosqlite_worker_thread(thread: threading.Thread) -> bool:
    """Return whether a thread is an aiosqlite connection worker."""
    target = getattr(thread, "_target", None)
    return (
        getattr(target, "__name__", None) == "_connection_worker_thread"
        and getattr(target, "__module__", "") == "aiosqlite.core"
    )


def _collect_leaked_threads(
    existing_threads: set[threading.Thread],
) -> list[threading.Thread]:
    """Return still-alive threads that a test created."""
    return [
        thread
        for thread in threading.enumerate()
        if thread not in existing_threads
        and thread.is_alive()
        and not _is_anyio_worker_thread(thread)
    ]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):  # noqa: ARG001
    """Report threads that a test left alive after its fixtures tear down."""
    yield

    existing_threads = getattr(item, "_astrbot_test_threads", None)
    if existing_threads is None:
        return
    leaked_threads = _collect_leaked_threads(existing_threads)
    for thread in leaked_threads:
        if _is_aiosqlite_worker_thread(thread):
            thread.join(timeout=1.0)
    leaked_threads = _collect_leaked_threads(existing_threads)
    if leaked_threads:
        thread_names = ", ".join(thread.name for thread in leaked_threads)
        pytest.fail(f"Leaked threads: {thread_names}")


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_leaked_asyncio_tasks():
    """Fail tests that leave event-loop tasks behind after cancelling them.

    The fixture records the loop state after fixture setup, so pytest-asyncio's
    own runner tasks and tasks established by the test harness are ignored.
    Any task created by the test remains the test's responsibility.
    """
    existing_tasks = set(asyncio.all_tasks())

    yield

    current_task = asyncio.current_task()
    leaked_tasks = [
        task
        for task in asyncio.all_tasks() - existing_tasks
        if task is not current_task and not task.done()
    ]
    if not leaked_tasks:
        return

    for task in leaked_tasks:
        task.cancel()
    await asyncio.gather(*leaked_tasks, return_exceptions=True)

    task_names = ", ".join(task.get_name() for task in leaked_tasks)
    pytest.fail(f"Leaked asyncio tasks: {task_names}")


# ============================================================
# 临时目录和文件 Fixtures
# ============================================================


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """创建临时目录用于测试。"""
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
    """创建模拟的 data 目录结构。"""
    data_dir = temp_dir / "data"
    data_dir.mkdir()

    # 创建必要的子目录
    (data_dir / "config").mkdir()
    (data_dir / "plugins").mkdir()
    (data_dir / "temp").mkdir()
    (data_dir / "attachments").mkdir()

    return data_dir


@pytest.fixture
def temp_config_file(temp_data_dir: Path) -> Path:
    """创建临时配置文件。"""
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
    """创建临时数据库文件路径。"""
    return temp_data_dir / "test.db"


# ============================================================
# Mock Fixtures
# ============================================================


@pytest.fixture
def mock_provider():
    """创建模拟的 Provider。"""
    provider = MagicMock()
    provider.provider_config = {
        "id": "test-provider",
        "type": "openai_chat_completions",
        "model": "gpt-4o-mini",
    }
    provider.get_model = MagicMock(return_value="gpt-4o-mini")
    provider.text_chat = AsyncMock()
    provider.text_chat_stream = AsyncMock()
    provider.terminate = AsyncMock()
    return provider


@pytest.fixture
def mock_platform():
    """创建模拟的 Platform。"""
    platform = MagicMock()
    platform.platform_name = "test_platform"
    platform.platform_meta = MagicMock()
    platform.platform_meta.support_proactive_message = False
    platform.send_message = AsyncMock()
    platform.terminate = AsyncMock()
    return platform


@pytest.fixture
def mock_conversation():
    """创建模拟的 Conversation。"""
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
    """创建模拟的 AstrMessageEvent。"""
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
# 配置 Fixtures
# ============================================================


@pytest.fixture
def astrbot_config(temp_config_file: Path):
    """创建 AstrBotConfig 实例。"""
    from astrbot.core.config.astrbot_config import AstrBotConfig

    config = AstrBotConfig()
    config._config_path = str(temp_config_file)  # noqa: SLF001
    return config


@pytest.fixture
def main_agent_build_config():
    """创建 MainAgentBuildConfig 实例。"""
    from astrbot.core.astr_main_agent import MainAgentBuildConfig

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
# 数据库 Fixtures
# ============================================================


@pytest_asyncio.fixture
async def temp_db(temp_db_file: Path):
    """创建临时数据库实例。"""
    from astrbot.core.db.sqlite import SQLiteDatabase

    db = SQLiteDatabase(str(temp_db_file))
    try:
        yield db
    finally:
        await db.close()
        if temp_db_file.exists():
            temp_db_file.unlink()


# ============================================================
# Context Fixtures
# ============================================================


@pytest_asyncio.fixture
async def mock_context(
    astrbot_config,
    temp_db,
    tmp_path,
    mock_provider,
    mock_platform,
):
    """Create a mock core execution context."""
    from asyncio import Queue

    from astrbot.core.agent.tool_image_cache import ToolImageCache
    from astrbot.core.computer.computer_client import ComputerRuntime
    from astrbot.core.execution_context import CoreExecutionContext
    from astrbot.core.runtime_catalogs import RuntimeCatalogs

    event_queue = Queue()

    provider_manager = MagicMock()
    provider_manager.get_using_provider = MagicMock(return_value=mock_provider)
    provider_manager.get_provider_by_id = MagicMock(return_value=mock_provider)

    platform_manager = MagicMock()
    conversation_manager = MagicMock()
    message_history_manager = MagicMock()
    persona_manager = MagicMock()
    persona_manager.runtime_personas = []
    astrbot_config_mgr = MagicMock()
    knowledge_base_manager = MagicMock()
    cron_manager = MagicMock()
    subagent_orchestrator = None

    context = CoreExecutionContext(
        event_queue=event_queue,
        config=astrbot_config,
        db=temp_db,
        provider_manager=provider_manager,
        platform_manager=platform_manager,
        conversation_manager=conversation_manager,
        message_history_manager=message_history_manager,
        persona_manager=persona_manager,
        astrbot_config_mgr=astrbot_config_mgr,
        knowledge_base_manager=knowledge_base_manager,
        cron_manager=cron_manager,
        preferences=MagicMock(),
        html_renderer=MagicMock(),
        file_token_service=MagicMock(),
        catalogs=RuntimeCatalogs(),
        computer_runtime=ComputerRuntime(),
        tool_image_cache=ToolImageCache(tmp_path / "tool_images"),
        subagent_orchestrator=subagent_orchestrator,
        metrics=MagicMock(upload=AsyncMock()),
    )

    return context


# ============================================================
# Provider Request Fixtures
# ============================================================


@pytest.fixture
def provider_request():
    """创建 ProviderRequest 实例。"""
    from astrbot.core.agent.llm_types import ProviderRequest

    return ProviderRequest(
        prompt="Hello",
        session_id="test_session",
        image_urls=[],
        contexts=[],
        system_prompt="You are a helpful assistant.",
    )
