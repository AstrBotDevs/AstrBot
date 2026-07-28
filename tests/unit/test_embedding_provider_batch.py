import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.genai.errors import APIError

from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.provider.provider import EmbeddingProvider, EmbeddingProviderError
from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)
from astrbot.core.provider.sources.nvidia_embedding_source import (
    NvidiaEmbeddingProvider,
)
from astrbot.core.provider.sources.ollama_embedding_source import (
    OllamaEmbeddingProvider,
)


class RecordingEmbeddingProvider(EmbeddingProvider):
    """Embedding provider used to assert batch ordering and concurrency."""

    def __init__(self, provider_config: dict | None = None) -> None:
        super().__init__(provider_config or {}, {})
        self.calls: list[list[str]] = []
        self._fail_counts: dict[str, int] = {}

    def set_fail_count(self, first_text: str, count: int) -> None:
        """Fail the batch that starts with first_text a fixed number of times.

        Args:
            first_text: First text in the batch used as the batch key.
            count: Number of transient failures before success.
        """
        self._fail_counts[first_text] = count

    async def get_embedding(self, text: str) -> list[float]:
        return [float(text.removeprefix("chunk-"))]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        self.calls.append(list(text))
        first = text[0]
        remaining = self._fail_counts.get(first, 0)
        if remaining > 0:
            self._fail_counts[first] = remaining - 1
            raise EmbeddingProviderError(
                "transient rate limit",
                status_code=429,
            )
        return [[float(item.removeprefix("chunk-"))] for item in text]

    def get_dim(self) -> int:
        return 1


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch):
    """Disable asyncio.sleep waits used by batch staggering and retries."""

    async def _instant_sleep(_delay: float = 0, *_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)
    # Keep random jitter deterministic for retry-delay code paths.
    monkeypatch.setattr(
        "astrbot.core.provider.provider.random.uniform",
        lambda _a, _b: 0.0,
    )


@pytest.mark.asyncio
async def test_get_embeddings_batch_retries_transient_failure(no_sleep) -> None:
    provider = RecordingEmbeddingProvider()
    provider.set_fail_count("chunk-0", 1)

    embeddings = await provider.get_embeddings_batch(
        ["chunk-0", "chunk-1"],
        batch_size=2,
        tasks_limit=1,
        max_retries=3,
    )

    assert embeddings == [[0.0], [1.0]]
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_get_embedding_with_retry_uses_batch_retry_path(no_sleep) -> None:
    provider = RecordingEmbeddingProvider()
    provider.set_fail_count("chunk-0", 1)

    embedding = await provider.get_embedding_with_retry("chunk-0")

    assert embedding == [0.0]
    assert provider.calls == [["chunk-0"], ["chunk-0"]]


@pytest.mark.asyncio
async def test_get_embeddings_batch_respects_retry_after_cooldown_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingEmbeddingProvider(
        {"embedding_rate_limit_cooldown": 120},
    )
    now = 100.0
    sleep_delays: list[float] = []

    def _monotonic() -> float:
        return now

    async def _advance_sleep(delay: float = 0, *_args, **_kwargs) -> None:
        nonlocal now
        sleep_delays.append(delay)
        now += delay

    async def fail_once(text: list[str]) -> list[list[float]]:
        provider.calls.append(list(text))
        if len(provider.calls) == 1:
            raise EmbeddingProviderError(
                "rate limited",
                status_code=429,
                response=SimpleNamespace(headers={"Retry-After": "60"}),
            )
        return [[0.0]]

    monkeypatch.setattr("astrbot.core.provider.provider.time.monotonic", _monotonic)
    monkeypatch.setattr(asyncio, "sleep", _advance_sleep)
    provider.get_embeddings = fail_once  # type: ignore[method-assign]

    embeddings = await provider.get_embeddings_batch(
        ["chunk-0"],
        batch_size=1,
        tasks_limit=1,
        max_retries=2,
    )

    assert embeddings == [[0.0]]
    assert sleep_delays == [60.0]
    assert provider._embedding_next_request_at == 160.0


@pytest.mark.asyncio
async def test_get_embeddings_batch_uses_provider_level_request_pacing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingEmbeddingProvider(
        {"embedding_max_requests_per_minute": 60},
    )
    now = 100.0
    sleep_delays: list[float] = []

    def _monotonic() -> float:
        return now

    async def _advance_sleep(delay: float = 0, *_args, **_kwargs) -> None:
        nonlocal now
        sleep_delays.append(delay)
        now += delay

    monkeypatch.setattr("astrbot.core.provider.provider.time.monotonic", _monotonic)
    monkeypatch.setattr(asyncio, "sleep", _advance_sleep)

    await asyncio.gather(
        provider.get_embeddings_batch(
            ["chunk-0"],
            batch_size=1,
            tasks_limit=1,
        ),
        provider.get_embeddings_batch(
            ["chunk-1"],
            batch_size=1,
            tasks_limit=1,
        ),
    )

    assert sleep_delays == [1.0]
    assert provider.calls == [["chunk-0"], ["chunk-1"]]


@pytest.mark.asyncio
async def test_concurrent_batches_honor_cooldown_without_rpm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingEmbeddingProvider(
        {"embedding_max_requests_per_minute": 0},
    )
    now = 100.0
    sleep_delays: list[float] = []

    def _monotonic() -> float:
        return now

    async def _advance_sleep(delay: float = 0, *_args, **_kwargs) -> None:
        nonlocal now
        sleep_delays.append(delay)
        now += delay

    monkeypatch.setattr("astrbot.core.provider.provider.time.monotonic", _monotonic)
    monkeypatch.setattr(asyncio, "sleep", _advance_sleep)
    provider._delay_embedding_requests(10.0)

    await asyncio.gather(
        provider.get_embeddings_batch(["chunk-0"], batch_size=1, tasks_limit=1),
        provider.get_embeddings_batch(["chunk-1"], batch_size=1, tasks_limit=1),
    )

    assert sleep_delays == [10.0]
    assert provider.calls == [["chunk-0"], ["chunk-1"]]


@pytest.mark.asyncio
async def test_provider_level_pacing_keeps_later_rate_limit_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingEmbeddingProvider(
        {
            "embedding_max_requests_per_minute": 60,
            "embedding_rate_limit_cooldown": 120,
        },
    )
    now = 100.0
    sleep_delays: list[float] = []
    inject_cooldown = True

    def _monotonic() -> float:
        return now

    async def _advance_sleep(delay: float = 0, *_args, **_kwargs) -> None:
        nonlocal inject_cooldown, now
        sleep_delays.append(delay)
        if inject_cooldown:
            provider._delay_embedding_requests(10.0)
            inject_cooldown = False
        now += delay

    monkeypatch.setattr("astrbot.core.provider.provider.time.monotonic", _monotonic)
    monkeypatch.setattr(asyncio, "sleep", _advance_sleep)
    provider._embedding_next_request_at = 101.0

    await provider._wait_for_embedding_request_slot()

    assert sleep_delays == [1.0, 9.0]


@pytest.mark.asyncio
async def test_get_embeddings_batch_global_cooldown_for_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingEmbeddingProvider(
        {"embedding_max_requests_per_minute": 60},
    )
    now = 100.0

    def _monotonic() -> float:
        return now

    async def _advance_sleep(delay: float = 0, *_args, **_kwargs) -> None:
        nonlocal now
        now += delay

    async def fail_once(text: list[str]) -> list[list[float]]:
        if not provider.calls:
            provider.calls.append(list(text))
            raise EmbeddingProviderError(
                "service unavailable",
                status_code=503,
            )
        provider.calls.append(list(text))
        return [[float(item.removeprefix("chunk-"))] for item in text]

    monkeypatch.setattr("astrbot.core.provider.provider.time.monotonic", _monotonic)
    monkeypatch.setattr(asyncio, "sleep", _advance_sleep)
    monkeypatch.setattr(
        "astrbot.core.provider.provider.random.uniform",
        lambda _a, _b: 0.0,
    )
    provider.get_embeddings = fail_once  # type: ignore[method-assign]

    embeddings = await provider.get_embeddings_batch(
        ["chunk-0"],
        batch_size=1,
        tasks_limit=1,
        max_retries=2,
    )

    assert embeddings == [[0.0]]
    assert provider._embedding_next_request_at >= 101.0


@pytest.mark.asyncio
async def test_faiss_insert_batch_classifies_provider_failure_as_embedding() -> None:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.embedding_provider.get_embeddings_batch.side_effect = RuntimeError(
        "rate limited",
    )
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = AsyncMock()

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["hello world"],
            metadatas=[{}],
            ids=["doc-1"],
        )

    error = exc_info.value
    assert error.stage == "embedding"
    assert "向量化失败" in error.user_message
    assert "Embedding API" in error.user_message
    vec_db.document_storage.insert_documents_batch.assert_not_awaited()
    vec_db.embedding_storage.insert_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_embeddings_batch_does_not_retry_permanent_4xx(no_sleep) -> None:
    provider = RecordingEmbeddingProvider()

    async def unauthorized(text: list[str]) -> list[list[float]]:
        provider.calls.append(list(text))
        raise EmbeddingProviderError("unauthorized", status_code=401)

    provider.get_embeddings = unauthorized  # type: ignore[method-assign]

    with pytest.raises(Exception, match="共尝试 1 次"):
        await provider.get_embeddings_batch(
            ["chunk-0"],
            batch_size=1,
            tasks_limit=1,
            max_retries=3,
        )

    assert provider.calls == [["chunk-0"]]


@pytest.mark.asyncio
async def test_gemini_embedding_preserves_api_status() -> None:
    provider = GeminiEmbeddingProvider.__new__(GeminiEmbeddingProvider)
    provider.client = SimpleNamespace(
        models=SimpleNamespace(
            embed_content=AsyncMock(
                side_effect=APIError(429, {"message": "rate limited"}),
            ),
        ),
    )
    provider.model = "embedding-model"
    provider.provider_config = {"embedding_dimensions": 768}

    with pytest.raises(EmbeddingProviderError) as exc_info:
        await provider.get_embeddings(["chunk-0"])

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_class",
    [NvidiaEmbeddingProvider, OllamaEmbeddingProvider],
)
async def test_aiohttp_embedding_providers_preserve_api_status(
    provider_class: type[EmbeddingProvider],
) -> None:
    class RateLimitedResponse:
        status = 429
        headers = {"Retry-After": "10"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
            return None

        async def text(self) -> str:
            return "rate limited"

    response = RateLimitedResponse()
    provider = provider_class.__new__(provider_class)
    provider.client = SimpleNamespace(
        closed=False,
        post=lambda *_args, **_kwargs: response,
    )
    provider.base_url = "https://embedding.example.com"
    provider.model = "embedding-model"
    provider.proxy = ""
    provider.provider_config = {}
    if isinstance(provider, NvidiaEmbeddingProvider):
        provider.input_type = "passage"

    with pytest.raises(EmbeddingProviderError) as exc_info:
        await provider.get_embeddings(["chunk-0"])

    assert exc_info.value.status_code == 429
    assert exc_info.value.response is response
