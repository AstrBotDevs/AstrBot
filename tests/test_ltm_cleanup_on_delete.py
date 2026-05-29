"""测试 Web UI 删除对话后 LTM session_chats 是否被正确清理 (Issue #8386 Bug 1)"""

import pytest
import pytest_asyncio
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.platform.message_type import MessageType
from astrbot.builtin_stars.astrbot.long_term_memory import LongTermMemory


@pytest_asyncio.fixture
async def conversation_manager():
    db = AsyncMock()
    db.delete_conversation = AsyncMock()
    db.get_conversation_by_id = AsyncMock(return_value=None)
    mgr = ConversationManager(db)
    return mgr


@pytest.fixture
def ltm():
    acm = MagicMock()
    context = MagicMock()
    context.get_config = MagicMock(return_value={
        "provider_ltm_settings": {
            "group_message_max_cnt": 300,
            "image_caption": False,
            "image_caption_provider_id": "",
            "active_reply": {"enable": False, "method": "possibility_reply", "possibility_reply": 0.1},
        },
        "provider_settings": {"image_caption_prompt": ""},
    })
    return LongTermMemory(acm, context)


@pytest.mark.asyncio
async def test_delete_conversation_triggers_session_deleted_callback(conversation_manager):
    """验证 delete_conversation 会触发 _on_session_deleted_callbacks"""
    callback = AsyncMock()
    conversation_manager.register_on_session_deleted(callback)

    umo = "feishu:group:test_group_123"
    conversation_manager.session_conversations[umo] = "conv-id-1"

    await conversation_manager.delete_conversation(
        unified_msg_origin=umo,
        conversation_id="conv-id-1",
    )

    callback.assert_called_once_with(umo)


@pytest.mark.asyncio
async def test_delete_conversation_clears_ltm_session_chats(conversation_manager, ltm):
    """模拟完整流程：LTM 注册回调后，Web UI 删除对话应清理 session_chats"""
    umo = "feishu:group:test_group_456"

    # 模拟群聊中已有 LTM 记录
    ltm.session_chats[umo] = [
        "[Alice/10:00:00]: 你好",
        "[Bob/10:01:00]: 你好啊",
        "[You/10:01:30]: 大家好！",
    ]

    # 注册回调（和 main.py 中的逻辑一致）
    async def _clear_ltm_session(origin: str) -> None:
        ltm.session_chats.pop(origin, None)

    conversation_manager.register_on_session_deleted(_clear_ltm_session)

    # 模拟当前会话指向该对话
    conversation_manager.session_conversations[umo] = "conv-id-2"

    # 执行删除（Web UI 路径）
    await conversation_manager.delete_conversation(
        unified_msg_origin=umo,
        conversation_id="conv-id-2",
    )

    # 验证 LTM 内存已清理
    assert umo not in ltm.session_chats


@pytest.mark.asyncio
async def test_ltm_on_req_llm_skips_after_session_cleared(conversation_manager, ltm):
    """删除对话后，on_req_llm 不应再注入已删除的历史到 system_prompt"""
    umo = "lark:GroupMessage:test_group_789"

    # 模拟已有 LTM 记录（存储在 group-level key 下）
    ltm.session_chats[umo] = [
        "[User1/09:00:00]: 之前的秘密对话",
    ]

    async def _clear_ltm_session(origin: str) -> None:
        ltm.session_chats.pop(origin, None)
        parts = origin.split(":")
        if len(parts) >= 3 and parts[1] == "GroupMessage":
            group_id = parts[2].split("%")[-1]
            group_key = f"{parts[0]}:GroupMessage:{group_id}"
            ltm.session_chats.pop(group_key, None)

    conversation_manager.register_on_session_deleted(_clear_ltm_session)
    conversation_manager.session_conversations[umo] = "conv-id-3"

    # 删除对话
    await conversation_manager.delete_conversation(
        unified_msg_origin=umo,
        conversation_id="conv-id-3",
    )

    # 模拟后续 LLM 请求
    event = MagicMock()
    event.unified_msg_origin = umo
    event.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event.get_group_id.return_value = "test_group_789"
    event.get_platform_id.return_value = "lark"

    req = MagicMock()
    req.system_prompt = "You are a helpful assistant."
    req.prompt = "你好"
    req.contexts = []

    await ltm.on_req_llm(event, req)

    # system_prompt 不应包含已删除的历史
    assert "秘密对话" not in req.system_prompt


@pytest.mark.asyncio
async def test_delete_other_conversation_does_not_affect_unrelated_session(conversation_manager, ltm):
    """删除某个 session 的对话不应影响其他 session 的 LTM 记录"""
    umo_a = "feishu:group:group_a"
    umo_b = "feishu:group:group_b"

    ltm.session_chats[umo_a] = ["[A/10:00:00]: hello"]
    ltm.session_chats[umo_b] = ["[B/10:00:00]: world"]

    async def _clear_ltm_session(origin: str) -> None:
        ltm.session_chats.pop(origin, None)

    conversation_manager.register_on_session_deleted(_clear_ltm_session)
    conversation_manager.session_conversations[umo_a] = "conv-a"

    # 只删除 group_a
    await conversation_manager.delete_conversation(
        unified_msg_origin=umo_a,
        conversation_id="conv-a",
    )

    assert umo_a not in ltm.session_chats
    assert ltm.session_chats[umo_b] == ["[B/10:00:00]: world"]


@pytest.mark.asyncio
async def test_group_key_ignores_unique_session(ltm):
    """Bug 3: unique_session 开启时，不同用户的 group_key 应相同（都指向群级别）"""
    # 用户 A 的 event（unique_session 改写了 unified_msg_origin）
    event_a = MagicMock()
    event_a.unified_msg_origin = "lark:GroupMessage:userA%group123"
    event_a.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event_a.get_group_id.return_value = "group123"
    event_a.get_platform_id.return_value = "lark"

    # 用户 B 的 event
    event_b = MagicMock()
    event_b.unified_msg_origin = "lark:GroupMessage:userB%group123"
    event_b.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event_b.get_group_id.return_value = "group123"
    event_b.get_platform_id.return_value = "lark"

    # 两者的 group_key 应该相同
    assert ltm._group_key(event_a) == ltm._group_key(event_b)
    assert ltm._group_key(event_a) == "lark:GroupMessage:group123"
