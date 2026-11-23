"""Name and UUID lookup exercise the real manager, including collisions."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.astr_agent_runtime.tools import knowledge_base_tools
from astrbot.core.knowledge_base import kb_mgr
from astrbot.core.knowledge_base.models import KnowledgeBase


@pytest.fixture
def manager(monkeypatch, tmp_path):
    monkeypatch.setattr(kb_mgr, "DB_PATH", tmp_path / "knowledge" / "kb.db")
    instance = kb_mgr.KnowledgeBaseManager(SimpleNamespace())
    record = KnowledgeBase(
        kb_id="bb47bf6f-3315-49bd-9c9a-7cc4aa9abbac",
        kb_name="测试",
        doc_count=1,
        chunk_count=2,
    )
    instance.kb_insts = {record.kb_id: SimpleNamespace(kb=record)}
    return instance


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["测试", "bb47bf6f-3315-49bd-9c9a-7cc4aa9abbac"])
async def test_lookup_resolves_name_and_legacy_uuid(manager, key):
    helper = next(iter(manager.kb_insts.values()))
    assert await manager.get_kb_by_name(key) is helper
    assert (helper.kb.kb_name, helper.kb.doc_count) == ("测试", 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["missing", "", "测试 "])
async def test_unknown_or_inexact_name_does_not_match(manager, key):
    assert await manager.get_kb_by_name(key) is None


@pytest.mark.asyncio
async def test_exact_name_takes_precedence_over_uuid_collision(manager):
    original = next(iter(manager.kb_insts.values()))
    colliding = SimpleNamespace(
        kb=KnowledgeBase(
            kb_name=original.kb.kb_id, kb_id="second-id", doc_count=1, chunk_count=1
        )
    )
    manager.kb_insts[colliding.kb.kb_id] = colliding

    assert await manager.get_kb_by_name(original.kb.kb_id) is colliding
    assert await manager.get_kb_by_name(original.kb.kb_name) is original
    assert await manager.get_kb(original.kb.kb_id) is original


@pytest.mark.parametrize(
    ("counts", "expected", "missing_count"),
    [
        ([(1, 2)], False, 0),
        ([(0, 0)], True, 0),
        ([None], True, 1),
        ([None, (0, 0), (1, 2)], False, 1),
        ([None, None, None], True, 3),
    ],
)
def test_empty_base_check_reports_missing_bases(
    monkeypatch, counts, expected, missing_count
):
    logger = Mock()
    monkeypatch.setattr(knowledge_base_tools, "logger", logger)
    helpers = [
        None
        if count is None
        else SimpleNamespace(
            kb=KnowledgeBase(
                kb_name=f"base-{index}", doc_count=count[0], chunk_count=count[1]
            )
        )
        for index, count in enumerate(counts)
    ]

    assert knowledge_base_tools.check_all_kb(helpers) is expected
    if missing_count:
        logger.warning.assert_called_once()
        warning = logger.warning.call_args.args[0]
        assert f"{missing_count}/{len(counts)}" in warning
        assert "未找到或未加载" in warning
    else:
        logger.warning.assert_not_called()
