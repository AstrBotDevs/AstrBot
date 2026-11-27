"""Unit tests for RetrievalManager rerank HTTP 401/402/403 cooldown circuit breaker."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest

from astrbot.core.knowledge_base.retrieval import manager as manager_module
from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
from astrbot.core.provider.entities import RerankResult


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class _FakeRerankProvider:
    def __init__(self, provider_id: str, outcomes: list) -> None:
        self._id = provider_id
        self.provider_config = {"id": provider_id}
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, list[str]]] = []

    def meta(self):
        return SimpleNamespace(id=self._id)

    async def rerank(self, query: str, documents: list[str], top_n: int | None = None):
        self.calls.append((query, list(documents)))
        outcome = self._outcomes.pop(0) if self._outcomes else []
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _make_manager_and_helpers(rerank_provider, provider_id: str = "siliconflow_rerank"):
    fused = [
        SimpleNamespace(
            chunk_id="c1",
            doc_id="d1",
            kb_id="kb1",
            content="first doc",
            score=0.8,
            chunk_index=0,
        ),
        SimpleNamespace(
            chunk_id="c2",
            doc_id="d2",
            kb_id="kb1",
            content="second doc",
            score=0.6,
            chunk_index=1,
        ),
    ]
    sparse_retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    rank_fusion = SimpleNamespace(fuse=AsyncMock(return_value=fused))
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                "d1": {
                    "document": SimpleNamespace(doc_name="doc1.md"),
                    "knowledge_base": SimpleNamespace(kb_name="KB1"),
                },
                "d2": {
                    "document": SimpleNamespace(doc_name="doc2.md"),
                    "knowledge_base": SimpleNamespace(kb_name="KB1"),
                },
            }
        )
    )
    vec_db = SimpleNamespace(
        retrieve=AsyncMock(return_value=[]),
        rerank_provider=rerank_provider,
    )
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=10,
            top_k_sparse=10,
            top_m_final=5,
            rerank_provider_id=provider_id,
        ),
        vec_db=vec_db,
    )
    mgr = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=rank_fusion,
        kb_db=kb_db,
        rerank_auth_cooldown_seconds=300.0,
        rerank_auth_max_cooldown_seconds=1200.0,
    )
    return mgr, {"kb1": kb_helper}


def _http_error(status: int, message: str = "Payment Required", url: str = "https://api.example.com/v1/rerank?api_key=sk-secret"):
    req_info = Mock()
    req_info.real_url = url
    return aiohttp.ClientResponseError(
        request_info=req_info,
        history=(),
        status=status,
        message=message,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 402, 403])
async def test_rerank_auth_billing_errors_trip_cooldown_and_recover(
    monkeypatch, caplog, status_code
):
    clock = _FakeClock(1000.0)
    monkeypatch.setattr(manager_module.time, "monotonic", clock)

    provider = _FakeRerankProvider(
        "siliconflow_rerank",
        [
            _http_error(status_code),
            _http_error(status_code),
            [
                RerankResult(index=1, relevance_score=0.95),
                RerankResult(index=0, relevance_score=0.40),
            ],
        ],
    )
    mgr, helpers = _make_manager_and_helpers(provider, "siliconflow_rerank")

    with caplog.at_level(logging.WARNING):
        # 1) First 401/402/403 opens 300s cooldown, logs single-line sanitized warning, returns fused order.
        res1 = await mgr.retrieve("hello", ["kb1"], helpers)
        assert [r.chunk_id for r in res1] == ["c1", "c2"]
        assert len(provider.calls) == 1
        assert len(caplog.records) == 1
        assert f"HTTP {status_code}" in caplog.records[0].message
        assert "sk-secret" not in caplog.records[0].message
        assert "\n" not in caplog.records[0].message

        # 2) Calls during cooldown skip provider completely and emit zero additional warnings.
        clock.now += 120.0
        res2 = await mgr.retrieve("hello", ["kb1"], helpers)
        assert [r.chunk_id for r in res2] == ["c1", "c2"]
        assert len(provider.calls) == 1
        assert len(caplog.records) == 1

        # 3) After 300s, half-open probe fails again -> escalates cooldown to 600s.
        clock.now += 181.0
        res3 = await mgr.retrieve("hello", ["kb1"], helpers)
        assert [r.chunk_id for r in res3] == ["c1", "c2"]
        assert len(provider.calls) == 2
        assert len(caplog.records) == 2
        assert "600s" in caplog.records[1].message

        # Still skipped at +400s (< 600s).
        clock.now += 400.0
        await mgr.retrieve("hello", ["kb1"], helpers)
        assert len(provider.calls) == 2

        # 4) After 600s, probe succeeds -> circuit closes and reranked order is returned!
        clock.now += 201.0
        res4 = await mgr.retrieve("hello", ["kb1"], helpers)
        assert [r.chunk_id for r in res4] == ["c2", "c1"]
        assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_rerank_wrapped_exception_and_provider_reload_reset(monkeypatch):
    clock = _FakeClock(2000.0)
    monkeypatch.setattr(manager_module.time, "monotonic", clock)

    # Simulate BailianNetworkError wrapping ClientResponseError(402) via __cause__.
    wrapped = RuntimeError("网络请求失败: Bearer super-secret-token")
    wrapped.__cause__ = _http_error(402)

    bad_provider = _FakeRerankProvider("bailian_rerank", [wrapped])
    mgr, helpers = _make_manager_and_helpers(bad_provider, "bailian_rerank")

    await mgr.retrieve("q1", ["kb1"], helpers)
    assert len(bad_provider.calls) == 1

    # Same instance is still in cooldown.
    clock.now += 10.0
    await mgr.retrieve("q2", ["kb1"], helpers)
    assert len(bad_provider.calls) == 1

    # Replacing the provider instance (e.g., user updated API key in WebUI) resets cooldown immediately.
    fresh_provider = _FakeRerankProvider(
        "bailian_rerank",
        [[RerankResult(index=1, relevance_score=0.9), RerankResult(index=0, relevance_score=0.1)]],
    )
    helpers["kb1"].vec_db.rerank_provider = fresh_provider
    res = await mgr.retrieve("q3", ["kb1"], helpers)
    assert [r.chunk_id for r in res] == ["c2", "c1"]
    assert len(fresh_provider.calls) == 1


@pytest.mark.asyncio
async def test_rerank_transient_500_does_not_open_auth_cooldown(monkeypatch):
    clock = _FakeClock(3000.0)
    monkeypatch.setattr(manager_module.time, "monotonic", clock)

    provider = _FakeRerankProvider(
        "vllm_rerank",
        [
            _http_error(500, "Internal Server Error"),
            [RerankResult(index=1, relevance_score=0.9), RerankResult(index=0, relevance_score=0.2)],
        ],
    )
    mgr, helpers = _make_manager_and_helpers(provider, "vllm_rerank")

    res1 = await mgr.retrieve("q1", ["kb1"], helpers)
    assert [r.chunk_id for r in res1] == ["c1", "c2"]

    # Immediate next request still calls rerank (no auth/billing circuit opened for HTTP 500).
    res2 = await mgr.retrieve("q2", ["kb1"], helpers)
    assert [r.chunk_id for r in res2] == ["c2", "c1"]
    assert len(provider.calls) == 2
