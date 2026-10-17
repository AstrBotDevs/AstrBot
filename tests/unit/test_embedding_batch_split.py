"""Embedding requests must survive a provider's per-request input limit.

Regression coverage for the knowledge-base upload failure where a provider
rejects a batch that carries too many inputs (DashScope text-embedding-v3/v4
return HTTP 400 "batch size is invalid, it should not be larger than 10.") and
the retry loop can never recover, aborting the whole upload.
"""

from pathlib import Path

import pytest

from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.provider.embedding_batch_limits import (
    combine_caps,
    dashscope_max_batch_items,
    is_dashscope_host,
)
from astrbot.core.provider.provider import (
    EmbeddingProvider,
    _extract_batch_limit,
    _is_retryable_error,
    _looks_like_batch_size_error,
)


class LimitedEmbeddingProvider(EmbeddingProvider):
    """Provider that refuses any request carrying more than ``limit`` inputs."""

    def __init__(self, limit: int, *, state_the_limit: bool = True) -> None:
        super().__init__({}, {})
        self.limit = limit
        self.state_the_limit = state_the_limit
        self.calls: list[list[str]] = []

    async def get_embedding(self, text: str) -> list[float]:
        return (await self.get_embeddings([text]))[0]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        self.calls.append(list(text))
        if len(text) > self.limit:
            hint = (
                f"batch size is invalid, it should not be larger than {self.limit}."
                if self.state_the_limit
                else "batch size is invalid."
            )
            raise Exception(
                f"DashScope Embedding API request failed (HTTP 400): "
                f"InvalidParameter - {hint}"
            )
        return [[float(item)] for item in text]

    def get_dim(self) -> int:
        return 1


def _texts(count: int) -> list[str]:
    return [str(i) for i in range(count)]


def _embedding_lengths(provider: LimitedEmbeddingProvider) -> list[int]:
    return [len(call) for call in provider.calls]


# ---------------------------------------------------------------------------
# Declared limits
# ---------------------------------------------------------------------------


class DeclaredCapProvider(LimitedEmbeddingProvider):
    def get_max_batch_size(self) -> int | None:
        return self.limit


@pytest.mark.asyncio
async def test_declared_limit_prevents_the_oversized_request() -> None:
    provider = DeclaredCapProvider(10)

    embeddings = await provider.get_embeddings_batch(
        _texts(25), batch_size=32, tasks_limit=2
    )

    assert embeddings == [[float(i)] for i in range(25)]
    # Clamped up front, so no request is ever refused.
    assert max(_embedding_lengths(provider)) == 10


@pytest.mark.asyncio
async def test_provider_config_can_declare_the_limit() -> None:
    provider = LimitedEmbeddingProvider(10)
    provider.provider_config = {"embedding_max_batch_items": 4}

    assert provider.get_max_batch_size() == 4

    embeddings = await provider.get_embeddings_batch(_texts(12), batch_size=32)
    assert len(embeddings) == 12
    assert max(_embedding_lengths(provider)) == 4


@pytest.mark.asyncio
async def test_invalid_declared_limit_falls_back_to_unknown() -> None:
    provider = LimitedEmbeddingProvider(10)
    provider.provider_config = {"embedding_max_batch_items": "many"}

    assert provider.get_max_batch_size() is None


# ---------------------------------------------------------------------------
# Adaptive splitting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejected_batch_is_split_and_results_stay_ordered() -> None:
    provider = LimitedEmbeddingProvider(10)

    embeddings = await provider.get_embeddings_batch(
        _texts(32), batch_size=32, tasks_limit=1
    )

    assert embeddings == [[float(i)] for i in range(32)]
    assert _embedding_lengths(provider)[0] == 32  # the doomed request
    assert max(_embedding_lengths(provider)) == 32


@pytest.mark.asyncio
async def test_stated_limit_is_honoured_exactly() -> None:
    provider = LimitedEmbeddingProvider(10)

    await provider.get_embeddings_batch(_texts(32), batch_size=32, tasks_limit=1)

    # The provider stated "not be larger than 10", so the retry uses 10/10/10/2
    # rather than halving down to 16/8.
    assert provider._learned_batch_size == 10
    assert _embedding_lengths(provider) == [32, 10, 10, 10, 2]


@pytest.mark.asyncio
async def test_unstated_limit_halves_until_it_fits() -> None:
    provider = LimitedEmbeddingProvider(3, state_the_limit=False)

    embeddings = await provider.get_embeddings_batch(
        _texts(8), batch_size=8, tasks_limit=1
    )

    assert embeddings == [[float(i)] for i in range(8)]
    # Nothing was stated, so the reduced size must not outlive this call.
    assert provider._learned_batch_size is None
    assert _embedding_lengths(provider)[0] == 8
    assert max(_embedding_lengths(provider)) == 8


@pytest.mark.asyncio
async def test_learned_limit_is_reused_by_later_calls() -> None:
    provider = LimitedEmbeddingProvider(10)

    await provider.get_embeddings_batch(_texts(32), batch_size=32, tasks_limit=1)
    provider.calls.clear()

    embeddings = await provider.get_embeddings_batch(
        _texts(20), batch_size=32, tasks_limit=1
    )

    assert len(embeddings) == 20
    assert _embedding_lengths(provider) == [10, 10]  # no second wasted attempt at 32


@pytest.mark.asyncio
async def test_progress_callback_reports_the_full_batch() -> None:
    provider = LimitedEmbeddingProvider(10)
    seen: list[tuple[int, int]] = []

    async def callback(current: int, total: int) -> None:
        seen.append((current, total))

    await provider.get_embeddings_batch(
        _texts(32), batch_size=32, tasks_limit=1, progress_callback=callback
    )

    assert seen == [(32, 32)]


@pytest.mark.asyncio
async def test_retryable_failures_are_still_retried() -> None:
    class FlakyProvider(LimitedEmbeddingProvider):
        def __init__(self) -> None:
            super().__init__(100)
            self.failures = 2

        async def get_embeddings(self, text: list[str]) -> list[list[float]]:
            self.calls.append(list(text))
            if self.failures:
                self.failures -= 1
                raise Exception("HTTP 429: rate limit exceeded, please retry")
            return [[float(item)] for item in text]

    provider = FlakyProvider()

    embeddings = await provider.get_embeddings_batch(_texts(2), batch_size=2)

    assert embeddings == [[0.0], [1.0]]
    assert len(provider.calls) == 1 + 2  # the two throttled attempts plus the success


@pytest.mark.asyncio
async def test_a_single_rejected_text_surfaces_the_provider_error() -> None:
    provider = LimitedEmbeddingProvider(0)

    with pytest.raises(Exception, match="有 1 个批次处理失败.*batch size is invalid"):
        await provider.get_embeddings_batch(["only"], batch_size=1, tasks_limit=1)


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "DashScope Embedding API request failed (HTTP 400): InvalidParameter - "
        "batch size is invalid, it should not be larger than 10.",
        "Error code: 400 - {'error': {'message': 'Too many inputs provided'}}",
        "HTTP 422: batch length exceeds the maximum of 25",
        "请求失败：单次最多 10 条",
    ],
)
def test_batch_size_rejections_are_recognised(message: str) -> None:
    assert _looks_like_batch_size_error(Exception(message))


@pytest.mark.parametrize(
    "message",
    [
        # Per-item content limits: splitting the request cannot help.
        "HTTP 400: context length must not be larger than 8192",
        "HTTP 400: max_tokens is invalid, batch size is fine otherwise",
        "HTTP 400: 文本过长，单次批量过大",
        # Not size related at all.
        "HTTP 401: Incorrect API key provided",
        "HTTP 404: model not found",
        "HTTP 429: too many requests, batch size limit reached",
        "HTTP 500: internal server error",
    ],
)
def test_unrelated_failures_are_not_mistaken_for_size_rejections(message: str) -> None:
    assert not _looks_like_batch_size_error(Exception(message))


def test_sdk_errors_carrying_a_status_code_are_recognised() -> None:
    """The OpenAI-compatible path raises ``openai.BadRequestError``."""
    import httpx
    from openai import BadRequestError

    def bad_request(message: str) -> BadRequestError:
        return BadRequestError(
            message,
            response=httpx.Response(
                400, request=httpx.Request("POST", "https://example.com/v1/embeddings")
            ),
            body=None,
        )

    error = bad_request(
        "Error code: 400 - {'error': {'message': 'batch size is invalid, "
        "it should not be larger than 10.'}}"
    )

    assert _looks_like_batch_size_error(error)
    assert _extract_batch_limit(error, attempted=32) == 10
    assert not _is_retryable_error(error)
    assert not _looks_like_batch_size_error(bad_request("Error code: 400 - bad key"))


def test_stated_limit_is_extracted_only_when_plausible() -> None:
    exc = Exception("HTTP 400: it should not be larger than 10.")

    assert _extract_batch_limit(exc, attempted=32) == 10
    # A limit that is not smaller than the request just refused cannot explain it.
    assert _extract_batch_limit(exc, attempted=10) is None
    assert (
        _extract_batch_limit(Exception("HTTP 400: bad request"), attempted=32) is None
    )


@pytest.mark.parametrize(
    ("message", "retryable"),
    [
        ("HTTP 429: rate limit", True),
        ("HTTP 503: service unavailable", True),
        ("connection reset by peer", True),
        ("HTTP 400: invalid request", False),
        ("HTTP 401: invalid api key", False),
    ],
)
def test_retryability(message: str, retryable: bool) -> None:
    assert _is_retryable_error(Exception(message)) is retryable


# ---------------------------------------------------------------------------
# Adapter-declared limits
# ---------------------------------------------------------------------------


def test_dashscope_limits_are_per_model() -> None:
    assert dashscope_max_batch_items("text-embedding-v4") == 10
    assert dashscope_max_batch_items("text-embedding-v3") == 10
    assert dashscope_max_batch_items("text-embedding-v2") == 25
    assert dashscope_max_batch_items("qwen3-vl-embedding") == 10
    assert dashscope_max_batch_items("text-embedding-3-small") is None
    assert dashscope_max_batch_items(None) is None


def test_dashscope_host_detection() -> None:
    assert is_dashscope_host("dashscope.aliyuncs.com")
    assert is_dashscope_host("dashscope-intl.aliyuncs.com")
    assert not is_dashscope_host("api.openai.com")
    assert not is_dashscope_host(None)


def test_combined_caps_only_ever_lower() -> None:
    assert combine_caps(None, 10) == 10
    assert combine_caps(25, 10) == 10
    assert combine_caps(None, None) is None


def test_dashscope_adapter_declares_the_native_limit() -> None:
    from astrbot.core.provider.sources.dashscope_embedding_source import (
        DashScopeEmbeddingProvider,
    )

    def make(model: str, **extra):
        provider = DashScopeEmbeddingProvider.__new__(DashScopeEmbeddingProvider)
        provider.model = model
        provider.provider_config = {"embedding_model": model, **extra}
        return provider

    assert make("text-embedding-v4").get_max_batch_size() == 10
    assert make("text-embedding-v2").get_max_batch_size() == 25
    # The multimodal models have no documented per-model limit: stay conservative.
    assert make("qwen3-vl-embedding").get_max_batch_size() == 10
    # A user-declared limit can only lower the result.
    assert (
        make("text-embedding-v2", embedding_max_batch_items=4).get_max_batch_size() == 4
    )


def test_openai_compatible_adapter_sniffs_dashscope_hosts() -> None:
    from astrbot.core.provider.sources.openai_embedding_source import (
        OpenAIEmbeddingProvider,
    )

    def make(api_base: str, model: str, **extra):
        provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
        provider.model = model
        provider.provider_config = {
            "embedding_api_base": api_base,
            "embedding_model": model,
            **extra,
        }
        return provider

    dashscope_openai_mode = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert make(dashscope_openai_mode, "text-embedding-v4").get_max_batch_size() == 10
    # Any other OpenAI-compatible gateway is unknown unless configured.
    assert (
        make("https://api.openai.com/v1", "text-embedding-3-small").get_max_batch_size()
        is None
    )
    assert (
        make(
            "https://api.openai.com/v1",
            "text-embedding-3-small",
            embedding_max_batch_items=8,
        ).get_max_batch_size()
        == 8
    )


@pytest.mark.asyncio
async def test_openai_compatible_dashscope_endpoint_is_clamped_end_to_end() -> None:
    """The second reported setup: DashScope through the OpenAI-compatible mode."""
    from unittest.mock import AsyncMock, MagicMock

    from astrbot.core.provider.sources.openai_embedding_source import (
        OpenAIEmbeddingProvider,
    )

    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.model = "text-embedding-v4"
    provider.provider_config = {
        "embedding_api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "embedding_model": "text-embedding-v4",
    }
    received: list[int] = []

    async def create(*, input, model):  # noqa: A002 - mirrors the SDK signature
        received.append(len(input))
        response = MagicMock()
        response.data = [MagicMock(embedding=[0.0]) for _ in input]
        return response

    provider.client = MagicMock()
    provider.client.embeddings.create = AsyncMock(side_effect=create)

    embeddings = await provider.get_embeddings_batch(
        _texts(25), batch_size=32, tasks_limit=3
    )

    assert len(embeddings) == 25
    assert received == [10, 10, 5]  # never 32, and no rejected request


# ---------------------------------------------------------------------------
# Persistence into a real vector store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insert_batch_succeeds_against_a_limited_provider(tmp_path: Path) -> None:
    """End-to-end: a knowledge-base insert must not fail because of the limit."""
    dim = 4

    class CappedProvider(LimitedEmbeddingProvider):
        async def get_embeddings(self, text: list[str]) -> list[list[float]]:
            if len(text) > self.limit:
                return await LimitedEmbeddingProvider.get_embeddings(self, text)
            return [[0.1, 0.2, 0.3, 0.4] for _ in text]

        def get_dim(self) -> int:
            return dim

    provider = CappedProvider(10)
    vec_db = FaissVecDB(
        doc_store_path=str(tmp_path / "doc.db"),
        index_store_path=str(tmp_path / "index.faiss"),
        embedding_provider=provider,
    )
    await vec_db.initialize()
    try:
        contents = _texts(40)
        await vec_db.insert_batch(
            contents=contents,
            metadatas=[{"kb_id": "kb-1"} for _ in contents],
            ids=[f"id-{i}" for i in range(len(contents))],
            batch_size=32,  # the dashboard default that triggered the bug
        )

        assert await vec_db.count_documents() == 40
        assert max(_embedding_lengths(provider)) == 32  # only the refused attempt
    finally:
        await vec_db.close()


@pytest.mark.asyncio
async def test_embedding_failure_is_reported_as_an_embedding_error(
    tmp_path: Path,
) -> None:
    """A provider failure must not be relabelled as a storage failure."""
    vec_db = _vec_db_whose_provider_raises("HTTP 401: invalid api key")

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1"],
            metadatas=[{}],
            ids=["doc-1"],
        )

    error = exc_info.value
    assert error.stage == "embedding"
    assert "向量化失败" in error.user_message
    assert "invalid api key" in error.user_message
    assert error.details["cause"] == "HTTP 401: invalid api key"


@pytest.mark.asyncio
async def test_provider_error_text_is_redacted() -> None:
    """Provider errors quote the request, so the API key must not be carried on.

    The message reaches the upload log and the dashboard's failure list.
    """
    key = "sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    vec_db = _vec_db_whose_provider_raises(
        f"HTTP 401: Incorrect API key provided: {key}. You can find your API key "
        f"at https://platform.openai.com/account/api-keys."
    )

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1"],
            metadatas=[{}],
            ids=["doc-1"],
        )

    error = exc_info.value
    assert key not in error.user_message
    assert key not in error.details["cause"]
    assert "[REDACTED]" in error.user_message
    # Everything that is not a secret is still reported.
    assert "Incorrect API key provided" in error.user_message


def _vec_db_whose_provider_raises(message: str) -> FaissVecDB:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = LimitedEmbeddingProvider(10)

    async def _call(*args, **kwargs):
        raise Exception(message)

    vec_db.embedding_provider.get_embeddings_batch = _call
    vec_db.document_storage = None
    vec_db.embedding_storage = None
    return vec_db
