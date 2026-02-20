"""
AstrBot 集成测试配置

提供集成测试专用的 fixtures 和配置。
"""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 设置测试环境
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("ASTRBOT_TEST_MODE", "true")


# ============================================================
# 集成测试专用 Fixtures
# ============================================================


@pytest_asyncio.fixture
async def integration_context(tmp_path: Path):
    """创建用于集成测试的完整 Context。"""
    from asyncio import Queue

    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.db.sqlite import SQLiteDatabase
    from astrbot.core.star.context import Context

    # 创建临时目录
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config").mkdir()
    (data_dir / "plugins").mkdir()
    (data_dir / "temp").mkdir()

    # 创建临时数据库
    db_path = data_dir / "test.db"
    db = SQLiteDatabase(str(db_path))

    # 创建配置
    config = AstrBotConfig()

    # 创建模拟的管理器
    provider_manager = MagicMock()
    platform_manager = MagicMock()
    conversation_manager = MagicMock()
    message_history_manager = MagicMock()
    persona_manager = MagicMock()
    persona_manager.personas_v3 = []
    astrbot_config_mgr = MagicMock()
    knowledge_base_manager = MagicMock()
    cron_manager = MagicMock()

    context = Context(
        Queue(),
        config,
        db,
        provider_manager,
        platform_manager,
        conversation_manager,
        message_history_manager,
        persona_manager,
        astrbot_config_mgr,
        knowledge_base_manager,
        cron_manager,
        None,
    )

    yield context

    # 清理
    await db.engine.dispose()


@pytest.fixture
def mock_llm_provider_for_integration():
    """创建用于集成测试的模拟 LLM Provider。"""
    from astrbot.core.provider.entities import LLMResponse, TokenUsage

    provider = MagicMock()
    provider.provider_config = {
        "id": "integration-test-provider",
        "type": "mock",
        "model": "mock-model",
        "modalities": ["text", "image", "tool_use"],
    }

    # 默认响应
    default_response = LLMResponse(
        role="assistant",
        completion_text="This is a mock response for integration testing.",
        usage=TokenUsage(input_other=10, output=5),
    )

    async def mock_text_chat(**kwargs):
        return default_response

    async def mock_text_chat_stream(**kwargs):
        response = LLMResponse(
            role="assistant",
            completion_text="This is a mock streaming response.",
            is_chunk=True,
            usage=TokenUsage(input_other=5, output=2),
        )
        yield response
        response.is_chunk = False
        yield response

    provider.text_chat = AsyncMock(side_effect=mock_text_chat)
    provider.text_chat_stream = AsyncMock(side_effect=mock_text_chat_stream)
    provider.get_model = MagicMock(return_value="mock-model")
    provider.terminate = AsyncMock()
    provider.meta = MagicMock(
        return_value=MagicMock(id="integration-test-provider", type="mock")
    )

    return provider


@pytest.fixture
def mock_platform_for_integration():
    """创建用于集成测试的模拟 Platform。"""
    platform = MagicMock()
    platform.platform_name = "integration_test_platform"
    platform.platform_meta = MagicMock()
    platform.platform_meta.support_proactive_message = True

    sent_messages = []

    async def mock_send_message(event, message_chain):
        sent_messages.append(message_chain)
        return True

    platform.send_message = AsyncMock(side_effect=mock_send_message)
    platform.terminate = AsyncMock()
    platform._sent_messages = sent_messages  # 用于测试验证

    return platform


# ============================================================
# Pipeline 测试 Fixtures
# ============================================================


@pytest.fixture
def mock_pipeline_context():
    """创建模拟的 Pipeline 上下文。"""
    from astrbot.core.pipeline.context import PipelineContext

    context = MagicMock(spec=PipelineContext)
    context.event = MagicMock()
    context.event.unified_msg_origin = "test_umo"
    context.event.message_str = "test message"
    context.abort = False
    context.skip_remaining = False
    context.data = {}

    return context


# ============================================================
# 数据库测试 Fixtures
# ============================================================


@pytest_asyncio.fixture
async def populated_test_db(tmp_path: Path):
    """创建包含测试数据的数据库。"""
    from astrbot.core.db.sqlite import SQLiteDatabase

    db_path = tmp_path / "populated_test.db"
    db = SQLiteDatabase(str(db_path))

    # 创建测试会话
    from astrbot.core.db.po import ConversationV2

    async with db.get_db() as session:
        conv = ConversationV2(
            conversation_id="test-conv-1",
            platform_id="test_platform",
            user_id="test_umo_1",
            content=[{"role": "user", "content": "Hello"}],
            persona_id=None,
        )
        session.add(conv)
        await session.commit()

    yield db

    # 清理
    await db.engine.dispose()
    if db_path.exists():
        db_path.unlink()
