"""
AstrBot 测试配置

提供共享的 pytest fixtures 和测试工具。
"""

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# 将项目根目录添加到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 设置测试环境变量
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("ASTRBOT_TEST_MODE", "true")


# ============================================================
# 测试收集和排序
# ============================================================


def pytest_collection_modifyitems(session, config, items):  # noqa: ARG001
    """重新排序测试：单元测试优先，集成测试在后。"""
    unit_tests = []
    integration_tests = []

    for item in items:
        item_path = Path(str(item.path))
        is_integration = "integration" in item_path.parts

        if is_integration:
            if item.get_closest_marker("integration") is None:
                item.add_marker(pytest.mark.integration)
            integration_tests.append(item)
        else:
            if item.get_closest_marker("unit") is None:
                item.add_marker(pytest.mark.unit)
            unit_tests.append(item)

    # 单元测试 -> 集成测试
    items[:] = unit_tests + integration_tests


def pytest_configure(config):
    """注册自定义标记。"""
    config.addinivalue_line("markers", "unit: 单元测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "slow: 慢速测试")
    config.addinivalue_line("markers", "platform: 平台适配器测试")
    config.addinivalue_line("markers", "provider: LLM Provider 测试")
    config.addinivalue_line("markers", "db: 数据库相关测试")


# ============================================================
# 临时目录和文件 Fixtures
# ============================================================


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """创建临时目录用于测试。"""
    return tmp_path


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
    """创建模拟的插件上下文。"""
    from asyncio import Queue

    from astrbot.core.star.context import Context

    event_queue = Queue()

    provider_manager = MagicMock()
    provider_manager.get_using_provider = MagicMock(return_value=mock_provider)
    provider_manager.get_provider_by_id = MagicMock(return_value=mock_provider)

    platform_manager = MagicMock()
    conversation_manager = MagicMock()
    message_history_manager = MagicMock()
    persona_manager = MagicMock()
    persona_manager.personas_v3 = []
    astrbot_config_mgr = MagicMock()
    knowledge_base_manager = MagicMock()
    cron_manager = MagicMock()
    subagent_orchestrator = None

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
        subagent_orchestrator,
    )

    return context


# ============================================================
# Provider Request Fixtures
# ============================================================


@pytest.fixture
def provider_request():
    """创建 ProviderRequest 实例。"""
    from astrbot.core.provider.entities import ProviderRequest

    return ProviderRequest(
        prompt="Hello",
        session_id="test_session",
        image_urls=[],
        contexts=[],
        system_prompt="You are a helpful assistant.",
    )


# ============================================================
# 工具函数
# ============================================================


def create_mock_llm_response(
    completion_text: str = "Hello! How can I help you?",
    role: str = "assistant",
    tools_call_name: list[str] | None = None,
    tools_call_args: list[dict] | None = None,
    tools_call_ids: list[str] | None = None,
):
    """创建模拟的 LLM 响应。"""
    from astrbot.core.provider.entities import LLMResponse, TokenUsage

    return LLMResponse(
        role=role,
        completion_text=completion_text,
        tools_call_name=tools_call_name or [],
        tools_call_args=tools_call_args or [],
        tools_call_ids=tools_call_ids or [],
        usage=TokenUsage(input_other=10, output=5),
    )


def create_mock_message_component(
    component_type: str,
    **kwargs: Any,
) -> MagicMock:
    """创建模拟的消息组件。"""
    from astrbot.core.message import components as Comp

    component_map = {
        "plain": Comp.Plain,
        "image": Comp.Image,
        "at": Comp.At,
        "reply": Comp.Reply,
        "file": Comp.File,
    }

    component_class = component_map.get(component_type.lower())
    if not component_class:
        raise ValueError(f"Unknown component type: {component_type}")

    return component_class(**kwargs)


# ============================================================
# 跳过条件
# ============================================================


def pytest_runtest_setup(item):
    """在测试运行前检查跳过条件。"""
    # 跳过需要 API Key 但未设置的 Provider 测试
    if "provider" in [m.name for m in item.iter_markers()]:
        if not os.environ.get("TEST_PROVIDER_API_KEY"):
            pytest.skip("TEST_PROVIDER_API_KEY not set")

    # 跳过需要特定平台的测试
    if "platform" in [m.name for m in item.iter_markers()]:
        required_platform = None
        for marker in item.iter_markers(name="platform"):
            if marker.args:
                required_platform = marker.args[0]
                break

        if required_platform and not os.environ.get(
            f"TEST_{required_platform.upper()}_ENABLED"
        ):
            pytest.skip(f"TEST_{required_platform.upper()}_ENABLED not set")
