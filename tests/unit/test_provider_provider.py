"""Tests for astrbot.core.provider.provider.

Covers AbstractProvider, Provider, STTProvider, TTSProvider,
EmbeddingProvider, and RerankProvider abstract/concrete methods.
"""

import asyncio
from unittest.mock import AsyncMock, call, patch

import pytest

from astrbot.core.agent.message import Message
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderMeta,
    ProviderMetaData,
    ProviderType,
)
from astrbot.core.provider.provider import (
    AbstractProvider,
    EmbeddingProvider,
    Provider,
    RerankProvider,
    STTProvider,
    TTSProvider,
)

# =========================================================================
# AbstractProvider
# =========================================================================


class _ConcreteAbstractProvider(AbstractProvider):
    async def test(self) -> None:
        pass


class TestAbstractProvider:
    def test_construction(self):
        ap = _ConcreteAbstractProvider(provider_config={"type": "test"})
        assert ap.model_name == ""
        assert ap.provider_config == {"type": "test"}

    def test_set_and_get_model(self):
        ap = _ConcreteAbstractProvider(provider_config={"type": "test"})
        assert ap.get_model() == ""
        ap.set_model("gpt-4")
        assert ap.get_model() == "gpt-4"

    def test_set_model_empty_string(self):
        ap = _ConcreteAbstractProvider(provider_config={"type": "test"})
        ap.set_model("gpt-4")
        ap.set_model("")
        assert ap.get_model() == ""

    def test_meta_returns_provider_meta(self):
        pmd = ProviderMetaData(
            id="default",
            model=None,
            type="test_type",
            provider_type=ProviderType.CHAT_COMPLETION,
        )
        with patch(
            "astrbot.core.provider.provider.provider_cls_map",
            {"test_type": pmd},
        ):
            ap = _ConcreteAbstractProvider(
                provider_config={"type": "test_type", "id": "myid"}
            )
            meta = ap.meta()
            assert isinstance(meta, ProviderMeta)
            assert meta.id == "myid"
            assert meta.type == "test_type"
            assert meta.provider_type == ProviderType.CHAT_COMPLETION

    def test_meta_raises_on_unregistered_type(self):
        ap = _ConcreteAbstractProvider(provider_config={"type": "nonexistent"})
        with pytest.raises(ValueError, match="not registered"):
            ap.meta()

    def test_meta_no_provider_config_id_falls_back_to_default(self):
        pmd = ProviderMetaData(
            id="default",
            model=None,
            type="test_type",
            provider_type=ProviderType.EMBEDDING,
        )
        with patch(
            "astrbot.core.provider.provider.provider_cls_map",
            {"test_type": pmd},
        ):
            ap = _ConcreteAbstractProvider(provider_config={"type": "test_type"})
            meta = ap.meta()
            assert meta.id == "default"

    def test_abstract_provider_requires_a_healthcheck(self):
        with pytest.raises(TypeError, match="abstract"):
            AbstractProvider(provider_config={"type": "test"})

    def test_constructor_sets_provider_config(self):
        config = {"type": "myprovider", "key": ["sk-abc"]}
        ap = _ConcreteAbstractProvider(provider_config=config)
        assert ap.provider_config is config


# =========================================================================
# Provider (Chat)
# =========================================================================


class _ConcreteProvider(Provider):
    """Minimal concrete subclass for testing Provider abstract methods."""

    def get_current_key(self) -> str:
        return "key_override"

    def set_key(self, key: str) -> None:
        self._key = key

    async def get_models(self) -> list[str]:
        return ["model-a", "model-b"]

    async def text_chat(self, **kwargs) -> LLMResponse:
        return LLMResponse(role="assistant", completion_text="mock reply")


class TestProvider:
    def test_construction(self):
        p = _ConcreteProvider(
            provider_config={"type": "test", "key": ["sk-abc"]},
            provider_settings={},
        )
        assert p.provider_config["type"] == "test"
        assert p.provider_settings == {}

    def test_get_current_key_abstract(self):
        p = _ConcreteProvider(provider_config={"type": "test"}, provider_settings={})
        assert p.get_current_key() == "key_override"

    def test_get_keys_default(self):
        p = _ConcreteProvider(provider_config={"type": "test"}, provider_settings={})
        assert p.get_keys() == [""]

    def test_get_keys_from_config(self):
        p = _ConcreteProvider(
            provider_config={"type": "test", "key": ["sk-1", "sk-2"]},
            provider_settings={},
        )
        assert p.get_keys() == ["sk-1", "sk-2"]

    def test_get_keys_none(self):
        p = _ConcreteProvider(
            provider_config={"type": "test", "key": None},
            provider_settings={},
        )
        assert p.get_keys() == [""]

    def test_set_key(self):
        p = _ConcreteProvider(provider_config={"type": "test"}, provider_settings={})
        p.set_key("new-key")
        assert p._key == "new-key"

    def test_get_models(self):
        p = _ConcreteProvider(provider_config={"type": "test"}, provider_settings={})
        import asyncio

        models = asyncio.run(p.get_models())
        assert models == ["model-a", "model-b"]

    def test_text_chat(self):
        p = _ConcreteProvider(provider_config={"type": "test"}, provider_settings={})
        import asyncio

        resp = asyncio.run(p.text_chat(prompt="hi"))
        assert isinstance(resp, LLMResponse)
        assert resp.role == "assistant"
        assert resp.completion_text == "mock reply"

    def test_text_chat_abstract_prevents_instantiation(self):
        """Provider subclasses must override text_chat; can't instantiate without it."""

        class IncompleteProvider(Provider):
            def get_current_key(self) -> str:
                return ""

            def set_key(self, key: str) -> None:
                pass

            async def get_models(self) -> list[str]:
                return []

        with pytest.raises(TypeError):
            IncompleteProvider(provider_config={}, provider_settings={})

    def test_text_chat_stream_raises_not_implemented(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        with pytest.raises(NotImplementedError):
            import asyncio

            async def consume():
                gen = p.text_chat_stream(prompt="hi")
                async for _ in gen:
                    pass

            asyncio.run(consume())

    def test_pop_record_removes_non_system(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        ctx = [
            {"role": "system", "content": "You are a bot"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "how are you"},
        ]
        import asyncio

        asyncio.run(p.pop_record(ctx))
        assert len(ctx) == 2
        assert ctx[0]["role"] == "system"
        assert ctx[1]["role"] == "user"
        assert ctx[1]["content"] == "how are you"

    def test_pop_record_with_no_system(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        ctx = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
        ]
        import asyncio

        asyncio.run(p.pop_record(ctx))
        # Both should be popped
        assert len(ctx) == 0

    def test_pop_record_capped_at_two(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        ctx = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
        ]
        import asyncio

        asyncio.run(p.pop_record(ctx))
        assert len(ctx) == 4
        # system kept + last 3 non-system (u2, a2, u3) → but pop_record removes first 2 non-system
        assert ctx[0] == {"role": "system", "content": "sys"}
        assert ctx[1] == {"role": "user", "content": "u2"}

    @pytest.mark.asyncio
    async def test_test(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        with patch.object(
            p, "text_chat", AsyncMock(return_value=LLMResponse(role="assistant"))
        ):
            await p.test(test_timeout=5.0)

    def test_ensure_message_to_dicts_none(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        result = p._ensure_message_to_dicts(None)
        assert result == []

    def test_ensure_message_to_dicts_empty(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        result = p._ensure_message_to_dicts([])
        assert result == []

    def test_ensure_message_to_dicts_preserves_mixed_message_order(self):
        provider = _ConcreteProvider(provider_config={}, provider_settings={})
        user = {"role": "user", "content": "request"}
        assistant = Message(role="assistant", content="reply")

        result = provider._ensure_message_to_dicts([user, assistant])

        assert result[0] is user
        assert result[0] == {"role": "user", "content": "request"}
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "reply"
        assert assistant.content == "reply"

    def test_ensure_message_to_dicts_converts_message_objects(self):
        provider = _ConcreteProvider(provider_config={}, provider_settings={})
        message = Message(role="user", content="from pydantic")

        result = provider._ensure_message_to_dicts([message])

        assert result == [{"role": "user", "content": "from pydantic"}]
        assert isinstance(message, Message)

    def test_ensure_message_to_dicts_passes_through_dicts(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        d = {"role": "user", "content": "plain dict"}
        result = p._ensure_message_to_dicts([d])
        assert result == [d]


# =========================================================================
# STTProvider
# =========================================================================


class _ConcreteSTTProvider(STTProvider):
    async def get_text(self, audio_url: str) -> str:
        return "transcribed text"


class TestSTTProvider:
    def test_construction(self):
        p = _ConcreteSTTProvider(
            provider_config={"type": "stt_test"},
            provider_settings={},
        )
        assert p.provider_config["type"] == "stt_test"

    def test_get_text(self):
        p = _ConcreteSTTProvider(provider_config={}, provider_settings={})
        import asyncio

        text = asyncio.run(p.get_text("/path/to/audio.wav"))
        assert text == "transcribed text"

    def test_get_text_abstract(self):
        class IncompleteSTT(STTProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteSTT(provider_config={}, provider_settings={})


# =========================================================================
# TTSProvider
# =========================================================================


class _ConcreteTTSProvider(TTSProvider):
    async def get_audio(self, text: str) -> str:
        return "/tmp/test_output.wav"


class TestTTSProvider:
    def test_construction(self):
        p = _ConcreteTTSProvider(
            provider_config={"type": "tts_test"}, provider_settings={}
        )
        assert p.provider_config["type"] == "tts_test"

    def test_get_audio(self):
        p = _ConcreteTTSProvider(provider_config={}, provider_settings={})
        import asyncio

        path = asyncio.run(p.get_audio("hello"))
        assert path == "/tmp/test_output.wav"

    def test_support_stream_default(self):
        p = _ConcreteTTSProvider(provider_config={}, provider_settings={})
        assert p.support_stream() is False

    @pytest.mark.asyncio
    async def test_get_audio_stream_default_implementation(self, tmp_path):
        provider = _ConcreteTTSProvider(provider_config={}, provider_settings={})
        output = tmp_path / "generated.wav"
        output.write_bytes(b"RIFF-local-audio")
        provider.get_audio = AsyncMock(return_value=str(output))
        text_queue = asyncio.Queue()
        audio_queue = asyncio.Queue()
        for part in ["hello ", "world", None]:
            text_queue.put_nowait(part)

        await provider.get_audio_stream(text_queue, audio_queue)

        provider.get_audio.assert_awaited_once_with("hello world")
        assert audio_queue.qsize() == 2
        assert audio_queue.get_nowait() == ("hello world", b"RIFF-local-audio")
        assert audio_queue.get_nowait() is None
        assert text_queue.empty()


# =========================================================================
# EmbeddingProvider
# =========================================================================


class _ConcreteEmbeddingProvider(EmbeddingProvider):
    async def get_embedding(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in text]

    def get_dim(self) -> int:
        return 3


class TestEmbeddingProvider:
    def test_construction(self):
        p = _ConcreteEmbeddingProvider(
            provider_config={"type": "emb_test"},
            provider_settings={},
        )
        assert p.provider_config["type"] == "emb_test"

    def test_get_embedding(self):
        p = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
        import asyncio

        emb = asyncio.run(p.get_embedding("hello"))
        assert emb == [0.1, 0.2, 0.3]

    def test_get_embeddings(self):
        p = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
        import asyncio

        embs = asyncio.run(p.get_embeddings(["a", "b"]))
        assert len(embs) == 2

    def test_get_dim(self):
        p = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
        assert p.get_dim() == 3

    def test_get_embeddings_batch_single_batch(self):
        p = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
        import asyncio

        embs = asyncio.run(p.get_embeddings_batch(["hello", "world"], batch_size=10))
        assert len(embs) == 2

    @pytest.mark.asyncio
    async def test_get_embeddings_batch_multiple_batches(self):
        provider = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
        release_first = asyncio.Event()
        later_completed = asyncio.Event()

        async def embed(texts):
            if texts[0] == "text_0":
                await release_first.wait()
            else:
                later_completed.set()
            return [[float(text.rsplit("_", 1)[1])] for text in texts]

        provider.get_embeddings = AsyncMock(side_effect=embed)
        texts = [f"text_{index}" for index in range(5)]
        task = asyncio.create_task(
            provider.get_embeddings_batch(texts, batch_size=2, tasks_limit=2)
        )
        try:
            await asyncio.wait_for(later_completed.wait(), 3)
            release_first.set()
            result = await asyncio.wait_for(task, 3)
        finally:
            release_first.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert result == [[0.0], [1.0], [2.0], [3.0], [4.0]]
        assert provider.get_embeddings.await_count == 3

    @pytest.mark.asyncio
    async def test_get_embeddings_batch_with_progress_callback(self):
        provider = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
        progress = AsyncMock()

        result = await provider.get_embeddings_batch(
            ["first", "second", "third"],
            batch_size=2,
            tasks_limit=1,
            progress_callback=progress,
        )

        assert result == [[0.1, 0.2, 0.3]] * 3
        assert progress.await_args_list == [call(2, 3), call(3, 3)]


# =========================================================================
# RerankProvider
# =========================================================================


class _ConcreteRerankProvider(RerankProvider):
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ):
        from astrbot.core.provider.entities import RerankResult

        return [
            RerankResult(index=0, relevance_score=0.95),
            RerankResult(index=1, relevance_score=0.80),
        ][:top_n]


class TestRerankProvider:
    def test_construction(self):
        p = _ConcreteRerankProvider(
            provider_config={"type": "rerank_test"},
            provider_settings={},
        )
        assert p.provider_config["type"] == "rerank_test"

    def test_rerank(self):
        p = _ConcreteRerankProvider(provider_config={}, provider_settings={})
        import asyncio

        results = asyncio.run(p.rerank("test query", ["doc1", "doc2"]))
        assert len(results) == 2
        assert results[0].index == 0
        assert results[0].relevance_score == 0.95

    def test_rerank_with_top_n(self):
        p = _ConcreteRerankProvider(provider_config={}, provider_settings={})
        import asyncio

        results = asyncio.run(p.rerank("test query", ["doc1", "doc2", "doc3"], top_n=1))
        assert len(results) == 1


@pytest.mark.asyncio
async def test_embedding_batch_retry_budget_propagates_terminal_failure(monkeypatch):
    provider = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
    provider.get_embeddings = AsyncMock(
        side_effect=RuntimeError("embedding unavailable")
    )
    wait = AsyncMock()
    monkeypatch.setattr("astrbot.core.provider.provider.asyncio.sleep", wait)

    with pytest.raises(Exception, match="embedding unavailable"):
        await provider.get_embeddings_batch(["first"], max_retries=3)

    assert provider.get_embeddings.await_count == 3
    assert wait.await_args_list == [call(1), call(2)]


@pytest.mark.asyncio
async def test_embedding_batch_cancellation_drains_in_flight_requests():
    provider = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
    started = 0
    stopped = 0
    both_started = asyncio.Event()

    async def embed(texts):
        nonlocal started, stopped
        started += 1
        if started == 2:
            both_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped += 1

    provider.get_embeddings = AsyncMock(side_effect=embed)
    task = asyncio.create_task(
        provider.get_embeddings_batch(
            ["one", "two", "three"], batch_size=1, tasks_limit=2
        )
    )
    try:
        await asyncio.wait_for(both_started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert started == stopped == 2
    assert provider.get_embeddings.await_count == 2
