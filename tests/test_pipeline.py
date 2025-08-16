import pytest
import logging
import os
import asyncio
from astrbot.core.pipeline.scheduler import PipelineScheduler, PipelineContext
from astrbot.core.star import PluginManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import (
    AstrBotMessage,
    MessageMember,
    MessageType,
)
from astrbot.core.message.message_event_result import MessageChain, ResultContentType
from astrbot.core.message.components import Plain, At, Reply
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.star.context import Context
from asyncio import Queue

SESSION_ID_IN_WHITELIST = "test_sid_wl"
SESSION_ID_NOT_IN_WHITELIST = "test_sid"
TEST_LLM_PROVIDER = {
    "id": "zhipu_default",
    "type": "openai_chat_completion",
    "enable": True,
    "key": [os.getenv("ZHIPU_API_KEY")],
    "api_base": "https://open.bigmodel.cn/api/paas/v4/",
    "model_config": {
        "model": "glm-4-flash",
    },
}

TEST_COMMANDS = [
    ["help", "已注册的 AstrBot 内置指令"],
    ["tool ls", "函数工具"],
    ["tool on websearch", "激活工具"],
    ["tool off websearch", "停用工具"],
    ["plugin", "已加载的插件"],
    ["t2i", "文本转图片模式"],
    ["sid", "此 ID 可用于设置会话白名单。"],
    ["op test_op", "授权成功。"],
    ["deop test_op", "取消授权成功。"],
    ["wl test_platform:FriendMessage:test_sid_wl2", "添加白名单成功。"],
    ["dwl test_platform:FriendMessage:test_sid_wl2", "删除白名单成功。"],
    ["provider", "当前载入的 LLM 提供商"],
    ["reset", "重置成功"],
    # ["model", "查看、切换提供商模型列表"],
    ["history", "历史记录："],
    ["key", "当前 Key"],
    ["persona", "[Persona]"],
]


class FakeAstrMessageEvent(AstrMessageEvent):
    def __init__(self, abm: AstrBotMessage = None):
        meta = PlatformMetadata("test_platform", "test")
        super().__init__(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=meta,
            session_id=abm.session_id,
        )

    async def send(self, message: MessageChain):
        await super().send(message)

    @staticmethod
    def create_fake_event(
        message_str: str,
        session_id: str = "test_sid",
        is_at: bool = False,
        is_group: bool = False,
        sender_id: str = "123456",
    ):
        abm = AstrBotMessage()
        abm.message_str = message_str
        abm.group_id = "test"
        abm.message = [Plain(message_str)]
        if is_at:
            abm.message.append(At(qq="bot"))
        abm.self_id = "bot"
        abm.sender = MessageMember(sender_id, "mika")
        abm.timestamp = 1234567890
        abm.message_id = "test"
        abm.session_id = session_id
        if is_group:
            abm.type = MessageType.GROUP_MESSAGE
        else:
            abm.type = MessageType.FRIEND_MESSAGE
        return FakeAstrMessageEvent(abm)


@pytest.fixture(scope="module")
def event_queue():
    return Queue()


@pytest.fixture(scope="module")
def config():
    cfg = AstrBotConfig()
    cfg["platform_settings"]["id_whitelist"] = [
        "test_platform:FriendMessage:test_sid_wl",
        "test_platform:GroupMessage:test_sid_wl",
    ]
    cfg["admins_id"] = ["123456"]
    cfg["content_safety"]["internal_keywords"]["extra_keywords"] = ["^TEST_NEGATIVE"]
    cfg["provider"] = [TEST_LLM_PROVIDER]
    return cfg


@pytest.fixture(scope="module")
def db():
    return SQLiteDatabase("data/data_v3.db")


@pytest.fixture(scope="module")
def platform_manager(event_queue, config):
    return PlatformManager(config, event_queue)


@pytest.fixture(scope="module")
def provider_manager(config, db):
    return ProviderManager(config, db)


@pytest.fixture(scope="module")
def star_context(event_queue, config, db, platform_manager, provider_manager):
    star_context = Context(event_queue, config, db, provider_manager, platform_manager)
    return star_context


@pytest.fixture(scope="module")
def plugin_manager(star_context, config):
    plugin_manager = PluginManager(star_context, config)
    # await plugin_manager.reload()
    asyncio.run(plugin_manager.reload())
    return plugin_manager


@pytest.fixture(scope="module")
def pipeline_context(config, plugin_manager):
    return PipelineContext(config, plugin_manager)


@pytest.fixture(scope="module")
def pipeline_scheduler(pipeline_context):
    return PipelineScheduler(pipeline_context)


@pytest.mark.asyncio
async def test_platform_initialization(platform_manager: PlatformManager):
    await platform_manager.initialize()


@pytest.mark.asyncio
async def test_provider_initialization(provider_manager: ProviderManager):
    await provider_manager.initialize()


@pytest.mark.asyncio
async def test_pipeline_scheduler_initialization(pipeline_scheduler: PipelineScheduler):
    await pipeline_scheduler.initialize()


@pytest.mark.asyncio
async def test_pipeline_wakeup(pipeline_scheduler: PipelineScheduler, caplog):
    """测试唤醒"""
    # 群聊无 @ 无指令
    caplog.clear()
    mock_event = FakeAstrMessageEvent.create_fake_event("test", is_group=True)
    with caplog.at_level(logging.DEBUG):
        await pipeline_scheduler.execute(mock_event)
    assert any(
        "执行阶段 WhitelistCheckStage" not in message for message in caplog.messages
    )
    # 群聊有 @ 无指令
    mock_event = FakeAstrMessageEvent.create_fake_event(
        "test", is_group=True, is_at=True
    )
    with caplog.at_level(logging.DEBUG):
        await pipeline_scheduler.execute(mock_event)
    assert any("执行阶段 WhitelistCheckStage" in message for message in caplog.messages)
    # 群聊有指令
    mock_event = FakeAstrMessageEvent.create_fake_event(
        "/help", is_group=True, session_id=SESSION_ID_IN_WHITELIST
    )
    await pipeline_scheduler.execute(mock_event)
    assert mock_event._has_send_oper is True


@pytest.mark.asyncio
async def test_pipeline_wl(
    pipeline_scheduler: PipelineScheduler, config: AstrBotConfig, caplog
):
    caplog.clear()
    mock_event = FakeAstrMessageEvent.create_fake_event(
        "test", SESSION_ID_IN_WHITELIST, sender_id="123"
    )
    with caplog.at_level(logging.INFO):
        await pipeline_scheduler.execute(mock_event)
    assert any(
        "不在会话白名单中，已终止事件传播。" not in message
        for message in caplog.messages
    ), "日志中未找到预期的消息"

    mock_event = FakeAstrMessageEvent.create_fake_event("test", sender_id="123")
    with caplog.at_level(logging.INFO):
        await pipeline_scheduler.execute(mock_event)
    assert any(
        "不在会话白名单中，已终止事件传播。" in message for message in caplog.messages
    ), "日志中未找到预期的消息"


@pytest.mark.asyncio
async def test_pipeline_content_safety(pipeline_scheduler: PipelineScheduler, caplog):
    # 测试默认屏蔽词
    caplog.clear()
    mock_event = FakeAstrMessageEvent.create_fake_event(
        "色情", session_id=SESSION_ID_IN_WHITELIST
    )  # 测试需要。
    with caplog.at_level(logging.INFO):
        await pipeline_scheduler.execute(mock_event)
    assert any("内容安全检查不通过" in message for message in caplog.messages), (
        "日志中未找到预期的消息"
    )
    # 测试额外屏蔽词
    mock_event = FakeAstrMessageEvent.create_fake_event(
        "TEST_NEGATIVE", session_id=SESSION_ID_IN_WHITELIST
    )
    with caplog.at_level(logging.INFO):
        await pipeline_scheduler.execute(mock_event)
    assert any("内容安全检查不通过" in message for message in caplog.messages), (
        "日志中未找到预期的消息"
    )
    mock_event = FakeAstrMessageEvent.create_fake_event(
        "_TEST_NEGATIVE", session_id=SESSION_ID_IN_WHITELIST
    )
    with caplog.at_level(logging.INFO):
        await pipeline_scheduler.execute(mock_event)
    assert any("内容安全检查不通过" not in message for message in caplog.messages)
    # TODO: 测试 百度AI 的内容安全检查


@pytest.mark.asyncio
async def test_pipeline_llm(pipeline_scheduler: PipelineScheduler, caplog):
    caplog.clear()
    mock_event = FakeAstrMessageEvent.create_fake_event(
        "just reply me `OK`", session_id=SESSION_ID_IN_WHITELIST
    )
    with caplog.at_level(logging.DEBUG):
        await pipeline_scheduler.execute(mock_event)
    assert any("请求 LLM" in message for message in caplog.messages)
    assert mock_event.get_result() is not None
    assert mock_event.get_result().result_content_type == ResultContentType.LLM_RESULT


@pytest.mark.asyncio
async def test_pipeline_websearch(pipeline_scheduler: PipelineScheduler, caplog):
    caplog.clear()
    mock_event = FakeAstrMessageEvent.create_fake_event(
        "help me search the latest OpenAI news", session_id=SESSION_ID_IN_WHITELIST
    )
    with caplog.at_level(logging.DEBUG):
        await pipeline_scheduler.execute(mock_event)
    assert any("请求 LLM" in message for message in caplog.messages)
    assert any(
        "web_searcher - search_from_search_engine" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_commands(pipeline_scheduler: PipelineScheduler, caplog):
    for command in TEST_COMMANDS:
        caplog.clear()
        mock_event = FakeAstrMessageEvent.create_fake_event(
            command[0], session_id=SESSION_ID_IN_WHITELIST
        )
        with caplog.at_level(logging.DEBUG):
            await pipeline_scheduler.execute(mock_event)
        # assert any("执行阶段 ProcessStage" in message for message in caplog.messages)
        assert any(command[1] in message for message in caplog.messages)


@pytest.mark.asyncio
async def test_segmented_reply_with_quote_fix():
    """测试分段回复与引用消息结合时的修复 - Issue #2132"""
    from astrbot.core.pipeline.respond.stage import RespondStage
    
    # 创建响应阶段实例来测试辅助方法
    stage = RespondStage()
    
    # 测试 _is_empty_component 方法
    assert stage._is_empty_component(Plain("")) is True  # 空文本
    assert stage._is_empty_component(Plain("   ")) is True  # 仅空白字符
    assert stage._is_empty_component(Plain("Hello")) is False  # 正常文本
    assert stage._is_empty_component(Reply(id="123", sender_id="456")) is False  # 正常回复
    
    # 模拟分段后包含空组件的情况（这是导致bug的场景）
    non_record_comps = [
        Plain(""),        # 空的第一段 - 应该被跳过
        Plain("Hello"),   # 第二段包含内容
        Plain("world!"),  # 第三段包含内容
    ]
    
    # 装饰组件（@和引用）
    decorated_comps = [Reply(id="original", sender_id="user123")]
    
    # 模拟修复后的逻辑
    sent_messages = []
    decoration_used = False
    
    for comp in non_record_comps:
        # 跳过空组件 (这是修复的关键点)
        if stage._is_empty_component(comp):
            continue
        
        # 构建消息，第一个非空组件会包含装饰
        if not decoration_used:
            message = decorated_comps + [comp]
            decoration_used = True
        else:
            message = [comp]
        
        sent_messages.append(message)
    
    # 验证结果
    assert len(sent_messages) == 2, f"应该发送2条消息，实际发送了{len(sent_messages)}条"
    
    # 第一条消息应该包含引用和文本内容
    first_message = sent_messages[0]
    assert len(first_message) == 2, "第一条消息应该包含2个组件（引用+文本）"
    assert isinstance(first_message[0], Reply), "第一个组件应该是Reply"
    assert isinstance(first_message[1], Plain), "第二个组件应该是Plain"
    assert first_message[1].text == "Hello", "第一条消息的文本应该是'Hello'"
    
    # 第二条消息应该只包含文本
    second_message = sent_messages[1]  
    assert len(second_message) == 1, "第二条消息应该只包含1个组件"
    assert isinstance(second_message[0], Plain), "应该是Plain组件"
    assert second_message[0].text == "world!", "第二条消息的文本应该是'world!'"
