from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.tools import knowledge_base_tools
from astrbot.core.tools.knowledge_base_tools import retrieve_knowledge_base
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService


class FakeConf(dict):
    """Minimal stand-in for AstrBotConfig that records persistence calls."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.save_config_async = AsyncMock(return_value=True)


def make_kb(kb_id: str, kb_name: str):
    return SimpleNamespace(
        kb_id=kb_id,
        kb_name=kb_name,
        description="description",
        emoji="book",
        embedding_provider_id="embedding-1",
        rerank_provider_id=None,
        chunk_size=512,
        chunk_overlap=50,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
        doc_count=1,
        chunk_count=2,
        model_dump=lambda: {"kb_id": kb_id, "kb_name": kb_name},
    )


def make_service(kb_manager, config_mgr=None) -> KnowledgeBaseService:
    service = KnowledgeBaseService.__new__(KnowledgeBaseService)
    lifecycle = SimpleNamespace(kb_manager=kb_manager)
    if config_mgr is not None:
        lifecycle.astrbot_config_mgr = config_mgr
    service.core_lifecycle = lifecycle
    service.upload_progress = {}
    service.upload_tasks = {}
    return service


@pytest.mark.asyncio
async def test_update_kb_propagates_rename_to_all_config_profiles():
    kb = make_kb("kb-1", "Docs")
    renamed = make_kb("kb-1", "Docs 2")
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    kb_manager.update_kb = AsyncMock(return_value=SimpleNamespace(kb=renamed))

    default_conf = FakeConf(kb_names=["Docs", "kb-uuid"])
    profile_conf = FakeConf(kb_names=["Docs"])
    untouched_conf = FakeConf(kb_names=["Other"])
    config_mgr = SimpleNamespace(
        confs={
            "default": default_conf,
            "profile-1": profile_conf,
            "profile-2": untouched_conf,
        }
    )

    service = make_service(kb_manager, config_mgr)
    await service.update_kb({"kb_id": "kb-1", "kb_name": "Docs 2"})

    # The renamed knowledge base must stay selected, IDs must be left alone.
    assert default_conf["kb_names"] == ["Docs 2", "kb-uuid"]
    assert profile_conf["kb_names"] == ["Docs 2"]
    assert untouched_conf["kb_names"] == ["Other"]

    default_conf.save_config_async.assert_awaited_once()
    profile_conf.save_config_async.assert_awaited_once()
    untouched_conf.save_config_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_kb_deduplicates_when_new_name_already_present():
    kb = make_kb("kb-1", "Docs")
    renamed = make_kb("kb-1", "Docs 2")
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    kb_manager.update_kb = AsyncMock(return_value=SimpleNamespace(kb=renamed))

    conf = FakeConf(kb_names=["Docs", "Docs 2"])
    service = make_service(kb_manager, SimpleNamespace(confs={"default": conf}))

    await service.update_kb({"kb_id": "kb-1", "kb_name": "Docs 2"})

    assert conf["kb_names"] == ["Docs 2"]


@pytest.mark.asyncio
async def test_update_kb_without_rename_keeps_config_untouched():
    kb = make_kb("kb-1", "Docs")
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    kb_manager.update_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))

    conf = FakeConf(kb_names=["Docs"])
    service = make_service(kb_manager, SimpleNamespace(confs={"default": conf}))

    await service.update_kb({"kb_id": "kb-1", "chunk_size": 1024})

    assert conf["kb_names"] == ["Docs"]
    conf.save_config_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_kb_rename_without_config_manager_still_succeeds():
    kb = make_kb("kb-1", "Docs")
    renamed = make_kb("kb-1", "Docs 2")
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=SimpleNamespace(kb=kb))
    kb_manager.update_kb = AsyncMock(return_value=SimpleNamespace(kb=renamed))

    service = make_service(kb_manager)

    result, message = await service.update_kb({"kb_id": "kb-1", "kb_name": "Docs 2"})

    assert result == {"kb_id": "kb-1", "kb_name": "Docs 2"}
    assert message == "更新知识库成功"


class FakeKBManager:
    """KB manager stub that resolves knowledge bases by name, like production."""

    def __init__(self, helpers):
        self.helpers = {helper.kb.kb_id: helper for helper in helpers}

    async def get_kb(self, kb_id):
        return self.helpers.get(kb_id)

    async def get_kb_by_name(self, kb_name):
        for helper in self.helpers.values():
            if helper.kb.kb_name == kb_name:
                return helper
        return self.helpers.get(kb_name)

    async def update_kb(self, kb_id, kb_name, **_kwargs):
        helper = self.helpers[kb_id]
        helper.kb.kb_name = kb_name
        return helper

    async def retrieve(self, query, kb_names, top_k_fusion=20, top_m_final=5):
        return {"context_text": "hit", "results": [{"kb_name": kb_names[0]}]}


class FakeContext:
    def __init__(self, kb_manager, config):
        self.kb_manager = kb_manager
        self._config = config

    def get_config(self, umo=None):
        return self._config


class FakeSP:
    async def session_get(self, umo, key, default=None):
        return default


@pytest.mark.asyncio
async def test_rename_keeps_global_kb_retrieval_working(monkeypatch):
    """Renaming a selected knowledge base must not break retrieval."""
    monkeypatch.setattr(knowledge_base_tools, "sp", FakeSP())

    helper = SimpleNamespace(kb=make_kb("kb-1", "Docs"), init_error=None)
    kb_manager = FakeKBManager([helper])
    conf = FakeConf(kb_names=["Docs"])
    service = make_service(kb_manager, SimpleNamespace(confs={"default": conf}))
    context = FakeContext(kb_manager, conf)

    assert await retrieve_knowledge_base("q", "umo", context) == "hit"

    await service.update_kb({"kb_id": "kb-1", "kb_name": "Docs 2"})

    assert conf["kb_names"] == ["Docs 2"]
    assert await retrieve_knowledge_base("q", "umo", context) == "hit"

