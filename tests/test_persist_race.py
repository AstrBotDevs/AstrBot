"""
回归测试: persist_agent_history 并发持久化竞态

背景: 多个后台任务/定时任务的结果几乎同时到达时, 各自触发一次
persist_agent_history, 并发执行 "读历史 → 追加 → 写回", 后写覆盖先写,
导致部分结果(以及先前对话上下文)从会话历史中丢失。

本测试期望: 并发持久化后, 所有结果都应保留在历史中。
修复前该测试失败(复现 bug), 修复后通过(验证修复)。
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from astrbot.core.utils.history_saver import persist_agent_history


class FakeConversationManager:
    """模拟 ConversationManager: 共享存储 (umo, cid) -> history JSON"""

    def __init__(self):
        self.store: dict[tuple, str] = {}
        self.update_count = 0

    async def update_conversation(self, umo, cid, history=None, **kwargs):
        await asyncio.sleep(0.05)  # 模拟 DB 写入耗时, 放大竞态窗口
        self.store[(umo, cid)] = json.dumps(history, ensure_ascii=False)
        self.update_count += 1


def make_req(history: str):
    conv = SimpleNamespace(cid="conv-1", history=history)
    return SimpleNamespace(conversation=conv)


def make_event(umo: str):
    return SimpleNamespace(unified_msg_origin=umo)


def test_persist_basic():
    """基础功能: 单次持久化正常写入"""
    cm = FakeConversationManager()
    umo = "test:session:1"

    async def _run():
        await persist_agent_history(
            cm, event=make_event(umo), req=make_req("[]"), summary_note="result-x"
        )

    asyncio.run(_run())
    final = json.loads(cm.store[(umo, "conv-1")])
    notes = [m["content"] for m in final if m["role"] == "assistant"]
    assert notes == ["result-x"]


@pytest.mark.asyncio
async def test_persist_concurrent_keeps_all_results():
    """
    并发场景: 4 个后台任务结果几乎同时持久化, 不应丢失任何一条。

    复现路径: 每个任务在创建请求时读到旧历史快照, 然后并发 persist。
    修复方案: 同一会话的处理流程(读历史+持久化)串行化(session lock)。
    """
    cm = FakeConversationManager()
    umo = "test:session:1"
    n = 4

    # 模拟并发任务: 各自持有创建时读到的历史快照(并发时互不知道对方)
    reqs = [make_req(cm.store.get((umo, "conv-1"), "[]")) for _ in range(n)]
    events = [make_event(umo)] * n

    await asyncio.gather(*[
        persist_agent_history(cm, event=events[i], req=reqs[i], summary_note=f"result-{i}")
        for i in range(n)
    ])

    final = json.loads(cm.store[(umo, "conv-1")])
    saved = [m["content"] for m in final if m["role"] == "assistant"]
    expected = [f"result-{i}" for i in range(n)]
    lost = [e for e in expected if e not in saved]
    assert not lost, f"并发持久化丢失 {len(lost)}/{n} 条结果: {lost}"
    assert cm.update_count == n
