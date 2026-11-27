"""Regression tests for rerank provider resolution during retrieval (#10262).

Vector stores keep the rerank provider instance they were built with, so a
provider reload used to leave retrieval reranking through the terminated
instance and its pre-reload endpoint, key and model. Retrieval resolves the
provider by ID on every call instead, and must skip rerank when the configured
provider is no longer available.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

# Importing the core lifecycle first resolves the import cycle between
# astrbot.core.provider.manager and astrbot.core.knowledge_base.
import astrbot.core.core_lifecycle  # noqa: F401
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
from astrbot.core.knowledge_base.retrieval.rank_fusion import FusedResult
from astrbot.core.provider.entities import RerankResult
from astrbot.core.provider.sources.vllm_rerank_source import VLLMRerankProvider


class RecordingRerankProvider:
    """Rerank provider double that records the calls it receives."""

    def __init__(self, scores_by_index: dict[int, float]) -> None:
        self.scores_by_index = scores_by_index
        self.calls: list[tuple[str, list[str]]] = []

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        self.calls.append((query, list(documents)))
        return [
            RerankResult(index=index, relevance_score=score)
            for index, score in self.scores_by_index.items()
        ]


class TerminatedRerankProvider:
    """Provider instance that was terminated by a reload and must stay unused."""

    def __init__(self) -> None:
        self.rerank = AsyncMock(
            side_effect=AssertionError("rerank session is terminated")
        )


def make_fused_results(count: int, kb_id: str = "kb-1") -> list[FusedResult]:
    return [
        FusedResult(
            chunk_id=f"chunk-{index}",
            chunk_index=index,
            doc_id=f"doc-{index}",
            kb_id=kb_id,
            content=f"content-{index}",
            score=0.5,
        )
        for index in range(count)
    ]


def make_kb_helper(
    rerank_provider,
    vec_db_rerank_provider=None,
    kb_id: str = "kb-1",
    rerank_provider_id: str | None = "rerank-1",
):
    """Build a KBHelper double holding a vector store with a cached provider."""
    vec_db = MagicMock()
    vec_db.retrieve = AsyncMock(return_value=[])
    vec_db.rerank_provider = vec_db_rerank_provider

    helper = MagicMock()
    helper.vec_db = vec_db
    helper.kb = SimpleNamespace(
        kb_id=kb_id,
        kb_name=kb_id,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
        rerank_provider_id=rerank_provider_id,
    )
    helper.get_rp = AsyncMock(return_value=rerank_provider)
    return helper


def make_manager(fused_results: list[FusedResult]) -> RetrievalManager:
    kb_db = MagicMock()
    kb_db.get_documents_with_metadata_batch = AsyncMock(
        return_value={
            fused.doc_id: {
                "document": SimpleNamespace(doc_name=fused.doc_id),
                "knowledge_base": SimpleNamespace(kb_name=fused.kb_id),
            }
            for fused in fused_results
        }
    )

    sparse_retriever = MagicMock()
    sparse_retriever.retrieve = AsyncMock(return_value=[])

    rank_fusion = MagicMock()
    rank_fusion.fuse = AsyncMock(return_value=fused_results)

    return RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=rank_fusion,
        kb_db=kb_db,
    )


@pytest.mark.asyncio
async def test_retrieve_resolves_rerank_provider_by_id_not_cached_instance():
    """The provider cached by the vector store must never be used again."""
    terminated = TerminatedRerankProvider()
    current = RecordingRerankProvider({0: 0.2, 1: 0.9})
    helper = make_kb_helper(current, vec_db_rerank_provider=terminated)
    manager = make_manager(make_fused_results(2))

    results = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
        top_m_final=2,
    )

    helper.get_rp.assert_awaited_once()
    terminated.rerank.assert_not_awaited()
    assert current.calls == [("query", ["content-0", "content-1"])]
    # Rerank scores decide the final order: chunk-1 (0.9) before chunk-0 (0.2).
    assert [result.chunk_id for result in results] == ["chunk-1", "chunk-0"]


@pytest.mark.asyncio
async def test_retrieve_uses_reloaded_provider_without_rebuilding_kb():
    """A reload between two retrievals must be picked up on the next call."""
    terminated = TerminatedRerankProvider()
    before = RecordingRerankProvider({0: 0.9})
    after = RecordingRerankProvider({0: 0.4})
    helper = make_kb_helper(before, vec_db_rerank_provider=terminated)
    helper.get_rp = AsyncMock(side_effect=[before, after])
    manager = make_manager(make_fused_results(1))

    first = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )
    second = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    assert len(before.calls) == 1
    assert len(after.calls) == 1
    assert terminated.rerank.await_count == 0
    assert [result.score for result in first] == [0.9]
    assert [result.score for result in second] == [0.4]


@pytest.mark.asyncio
async def test_retrieve_skips_rerank_when_provider_is_unavailable():
    """A disabled or deleted provider must skip rerank, not revive a session."""
    terminated = TerminatedRerankProvider()
    helper = make_kb_helper(None, vec_db_rerank_provider=terminated)
    manager = make_manager(make_fused_results(2))

    results = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
        top_m_final=2,
    )

    terminated.rerank.assert_not_awaited()
    assert [result.chunk_id for result in results] == ["chunk-0", "chunk-1"]


@pytest.mark.asyncio
async def test_retrieve_keeps_first_available_provider_selection_order():
    """Multiple knowledge bases keep using the first resolvable provider."""
    first_provider = RecordingRerankProvider({0: 0.7})
    second_provider = RecordingRerankProvider({0: 0.3})
    first_helper = make_kb_helper(first_provider, kb_id="kb-1")
    second_helper = make_kb_helper(second_provider, kb_id="kb-2")
    fused = make_fused_results(1, kb_id="kb-1") + [
        FusedResult(
            chunk_id="chunk-other",
            chunk_index=0,
            doc_id="doc-other",
            kb_id="kb-2",
            content="content-other",
            score=0.5,
        )
    ]
    manager = make_manager(fused)

    await manager.retrieve(
        query="query",
        kb_ids=["kb-1", "kb-2"],
        kb_id_helper_map={"kb-1": first_helper, "kb-2": second_helper},
    )

    first_helper.get_rp.assert_awaited_once()
    second_helper.get_rp.assert_not_awaited()
    assert len(first_provider.calls) == 1
    assert second_provider.calls == []


@pytest.mark.asyncio
async def test_retrieve_survives_provider_resolution_failure():
    """A resolution error must degrade to unreranked results."""
    terminated = TerminatedRerankProvider()
    helper = make_kb_helper(None, vec_db_rerank_provider=terminated)
    helper.get_rp = AsyncMock(side_effect=ValueError("provider lookup failed"))
    manager = make_manager(make_fused_results(2))

    results = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
        top_m_final=2,
    )

    terminated.rerank.assert_not_awaited()
    assert [result.chunk_id for result in results] == ["chunk-0", "chunk-1"]


class FakeProviderManager:
    """Provider manager double exposing the live ``inst_map`` lookup."""

    def __init__(self, providers: dict) -> None:
        self.inst_map = dict(providers)

    async def get_provider_by_id(self, provider_id: str):
        return self.inst_map.get(provider_id)


def make_real_kb_helper(
    providers: dict,
    vec_db_rerank_provider,
    kb_id: str = "kb-1",
    rerank_provider_id: str | None = "rerank-1",
):
    """Build a real KBHelper so ``get_rp()`` runs its production code path."""
    helper = KBHelper.__new__(KBHelper)
    helper.kb = SimpleNamespace(
        kb_id=kb_id,
        kb_name=kb_id,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
        rerank_provider_id=rerank_provider_id,
    )
    helper.prov_mgr = FakeProviderManager(providers)

    vec_db = MagicMock()
    vec_db.retrieve = AsyncMock(return_value=[])
    vec_db.rerank_provider = vec_db_rerank_provider
    helper.vec_db = vec_db
    return helper


@pytest.mark.asyncio
async def test_retrieve_picks_up_reload_through_real_get_rp():
    """A provider reload must reach the next retrieval without rebuilding the KB."""
    terminated = TerminatedRerankProvider()
    before = RecordingRerankProvider({0: 0.9})
    after = RecordingRerankProvider({0: 0.4})
    helper = make_real_kb_helper({"rerank-1": before}, terminated)
    manager = make_manager(make_fused_results(1))

    first = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    # Save the provider config in the WebUI: inst_map is replaced, vec_db is not.
    helper.prov_mgr.inst_map["rerank-1"] = after

    second = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    assert len(before.calls) == 1
    assert len(after.calls) == 1
    assert terminated.rerank.await_count == 0
    assert [result.score for result in first] == [0.9]
    assert [result.score for result in second] == [0.4]


@pytest.mark.asyncio
async def test_retrieve_skips_rerank_when_real_get_rp_finds_no_provider():
    """Disabling the provider makes the next retrieval skip rerank."""
    terminated = TerminatedRerankProvider()
    helper = make_real_kb_helper({}, terminated)
    manager = make_manager(make_fused_results(2))

    results = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
        top_m_final=2,
    )

    terminated.rerank.assert_not_awaited()
    assert [result.chunk_id for result in results] == ["chunk-0", "chunk-1"]


@pytest.mark.asyncio
async def test_retrieve_falls_through_to_the_next_knowledge_base_provider():
    """When the first KB has no usable provider, the next one must be used."""
    terminated_first = TerminatedRerankProvider()
    usable_second = RecordingRerankProvider({0: 0.9, 1: 0.5})
    first_helper = make_kb_helper(None, vec_db_rerank_provider=terminated_first)
    second_helper = make_kb_helper(usable_second, kb_id="kb-2")
    fused = make_fused_results(1, kb_id="kb-1") + [
        FusedResult(
            chunk_id="chunk-other",
            chunk_index=0,
            doc_id="doc-other",
            kb_id="kb-2",
            content="content-other",
            score=0.5,
        )
    ]
    manager = make_manager(fused)

    results = await manager.retrieve(
        query="query",
        kb_ids=["kb-1", "kb-2"],
        kb_id_helper_map={"kb-1": first_helper, "kb-2": second_helper},
        top_m_final=2,
    )

    first_helper.get_rp.assert_awaited_once()
    second_helper.get_rp.assert_awaited_once()
    terminated_first.rerank.assert_not_awaited()
    assert len(usable_second.calls) == 1
    assert [result.score for result in results] == [0.9, 0.5]


@pytest.mark.asyncio
async def test_retrieve_logs_rerank_failure_with_type_and_traceback(caplog):
    """A failing rerank stays diagnosable, including empty-message errors."""
    failing = MagicMock()
    failing.rerank = AsyncMock(side_effect=AssertionError())
    helper = make_kb_helper(failing)
    manager = make_manager(make_fused_results(1))

    with caplog.at_level(logging.WARNING, logger="astrbot"):
        results = await manager.retrieve(
            query="query",
            kb_ids=["kb-1"],
            kb_id_helper_map={"kb-1": helper},
        )

    assert "Rerank 执行失败" in caplog.text
    assert "AssertionError" in caplog.text
    assert "Traceback" in caplog.text
    assert [result.chunk_id for result in results] == ["chunk-0"]


@pytest.mark.asyncio
async def test_retrieve_switches_provider_shared_by_multiple_knowledge_bases():
    """Knowledge bases sharing one provider ID all leave the terminated instance."""
    terminated_first = TerminatedRerankProvider()
    terminated_second = TerminatedRerankProvider()
    reloaded = RecordingRerankProvider({0: 0.6})
    helpers = {
        "kb-1": make_real_kb_helper({"rerank-1": reloaded}, terminated_first, "kb-1"),
        "kb-2": make_real_kb_helper({"rerank-1": reloaded}, terminated_second, "kb-2"),
    }
    fused = make_fused_results(1, kb_id="kb-1") + [
        FusedResult(
            chunk_id="chunk-other",
            chunk_index=0,
            doc_id="doc-other",
            kb_id="kb-2",
            content="content-other",
            score=0.5,
        )
    ]
    manager = make_manager(fused)

    await manager.retrieve(
        query="query",
        kb_ids=["kb-1", "kb-2"],
        kb_id_helper_map=helpers,
    )

    assert len(reloaded.calls) == 1
    assert terminated_first.rerank.await_count == 0
    assert terminated_second.rerank.await_count == 0


class RecordingSession:
    """Minimal aiohttp session double that records the requests it sends."""

    def __init__(self, response_data) -> None:
        self.response_data = response_data
        self.closed = False
        self.requests: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict):
        if self.closed:
            raise RuntimeError("Session is closed")
        self.requests.append((url, json))
        return _SessionResponse(self.response_data)

    async def close(self) -> None:
        self.closed = True


class _SessionResponse:
    def __init__(self, response_data) -> None:
        self.response_data = response_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self) -> None:
        return None

    async def json(self):
        return self.response_data


def make_vllm_provider(base_url: str, api_key: str, model: str, score: float):
    """Build a real VLLMRerankProvider holding its own recording session."""
    provider = VLLMRerankProvider.__new__(VLLMRerankProvider)
    provider.base_url = base_url
    provider.api_suffix = "/v1/rerank"
    provider.model = model
    provider.auth_key = api_key
    provider.timeout = 20
    provider.client = RecordingSession(
        {"results": [{"index": 0, "relevance_score": score}]}
    )
    return provider


@pytest.mark.asyncio
async def test_retrieve_uses_new_endpoint_and_key_after_config_change(monkeypatch):
    """Saving new endpoint/key/model must reach the next retrieval (config A -> B).

    This is the end-to-end shape of the reported bug: the vector store keeps the
    provider it was built with, and reranking must not fall back to it.
    """
    provider_a = make_vllm_provider(
        "https://rerank-a.example.test", "key-a", "model-a", 0.9
    )
    helper = make_real_kb_helper({"rerank-1": provider_a}, provider_a)
    manager = make_manager(make_fused_results(1))

    created_sessions = []

    def fail_if_session_created(*args, **kwargs):
        created_sessions.append((args, kwargs))
        raise AssertionError("retrieval must not create an HTTP session")

    monkeypatch.setattr(aiohttp, "ClientSession", fail_if_session_created)

    first = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    assert provider_a.client.requests == [
        (
            "https://rerank-a.example.test/v1/rerank",
            {"query": "query", "documents": ["content-0"], "model": "model-a"},
        )
    ]
    assert [result.score for result in first] == [0.9]

    # The WebUI saves the provider config: the old instance is terminated and a
    # new one is installed under the same ID.
    await provider_a.terminate()
    assert provider_a.client is None
    provider_b = make_vllm_provider(
        "https://rerank-b.example.test", "key-b", "model-b", 0.4
    )
    helper.prov_mgr.inst_map["rerank-1"] = provider_b

    second = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    assert provider_b.client.requests == [
        (
            "https://rerank-b.example.test/v1/rerank",
            {"query": "query", "documents": ["content-0"], "model": "model-b"},
        )
    ]
    assert [result.score for result in second] == [0.4]
    # The terminated instance stayed terminated and was not rebuilt.
    assert provider_a.client is None
    assert created_sessions == []


class ReloadingProviderManager:
    """Provider manager double that mirrors ``reload()``'s terminate-then-load order."""

    def __init__(self, provider) -> None:
        self.inst_map = {"rerank-1": provider}

    async def get_provider_by_id(self, provider_id: str):
        return self.inst_map.get(provider_id)

    async def reload_with(self, new_provider) -> None:
        """terminate_provider() then load_provider(), as ProviderManager does."""
        old = self.inst_map.pop("rerank-1", None)
        if old is not None:
            await old.terminate()
        self.inst_map["rerank-1"] = new_provider


@pytest.mark.asyncio
async def test_retrieve_degrades_in_reload_window_then_recovers():
    """A retrieval landing between terminate and load skips rerank, then recovers.

    ``ProviderManager.reload()`` awaits terminate before load, so the ID is
    briefly absent from ``inst_map``. A retrieval in that window must return the
    fused results rather than calling the terminated instance, and the very next
    retrieval must use the reloaded instance.
    """
    provider_a = make_vllm_provider(
        "https://rerank-a.example.test", "key-a", "model-a", 0.9
    )
    prov_mgr = ReloadingProviderManager(provider_a)

    helper = KBHelper.__new__(KBHelper)
    helper.kb = SimpleNamespace(
        kb_id="kb-1",
        kb_name="kb-1",
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
        rerank_provider_id="rerank-1",
    )
    helper.prov_mgr = prov_mgr
    vec_db = MagicMock()
    vec_db.retrieve = AsyncMock(return_value=[])
    vec_db.rerank_provider = provider_a
    helper.vec_db = vec_db

    manager = make_manager(make_fused_results(1))

    # Window: the ID is gone while the new instance is still being constructed.
    prov_mgr.inst_map.pop("rerank-1")
    await provider_a.terminate()

    during = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    assert [result.chunk_id for result in during] == ["chunk-0"]
    assert provider_a.client is None

    # load_provider() finishes: the next retrieval uses the new instance.
    provider_b = make_vllm_provider(
        "https://rerank-b.example.test", "key-b", "model-b", 0.4
    )
    prov_mgr.inst_map["rerank-1"] = provider_b

    after = await manager.retrieve(
        query="query",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": helper},
    )

    assert [result.score for result in after] == [0.4]
    assert provider_b.client.requests[0][0] == (
        "https://rerank-b.example.test/v1/rerank"
    )
