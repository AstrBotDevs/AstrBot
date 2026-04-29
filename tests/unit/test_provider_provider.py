"""Tests for astrbot.core.provider.provider.

Covers AbstractProvider, Provider, STTProvider, TTSProvider,
EmbeddingProvider, and RerankProvider abstract/concrete methods.
"""

from unittest.mock import AsyncMock, MagicMock, patch

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


class TestAbstractProvider:
    def test_construction(self):
        ap = AbstractProvider(provider_config={"type": "test"})
        assert ap.model_name == ""
        assert ap.provider_config == {"type": "test"}

    def test_set_and_get_model(self):
        ap = AbstractProvider(provider_config={"type": "test"})
        assert ap.get_model() == ""
        ap.set_model("gpt-4")
        assert ap.get_model() == "gpt-4"

    def test_set_model_empty_string(self):
        ap = AbstractProvider(provider_config={"type": "test"})
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
            ap = AbstractProvider(provider_config={"type": "test_type", "id": "myid"})
            meta = ap.meta()
            assert isinstance(meta, ProviderMeta)
            assert meta.id == "myid"
            assert meta.type == "test_type"
            assert meta.provider_type == ProviderType.CHAT_COMPLETION

    def test_meta_raises_on_unregistered_type(self):
        ap = AbstractProvider(provider_config={"type": "nonexistent"})
        with pytest.raises(ValueError, match="not registered"):
            ap.meta()

    def test_meta_no_provider_config_id_falls_back_to_default(self):
        pmd = ProviderMetaData(
            id="default", model=None, type="test_type", provider_type=ProviderType.EMBEDDING
        )
        with patch(
            "astrbot.core.provider.provider.provider_cls_map",
            {"test_type": pmd},
        ):
            ap = AbstractProvider(provider_config={"type": "test_type"})
            meta = ap.meta()
            assert meta.id == "default"

    def test_test_does_not_raise(self):
        ap = AbstractProvider(provider_config={"type": "test"})
        # test() is a no-op on AbstractProvider
        ap.test()  # should not raise

    def test_constructor_sets_provider_config(self):
        config = {"type": "myprovider", "key": ["sk-abc"]}
        ap = AbstractProvider(provider_config=config)
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
        models = p.get_models()
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
        p.pop_record(ctx)
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
        p.pop_record(ctx)
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
        p.pop_record(ctx)
        assert len(ctx) == 4
        # system kept + last 3 non-system (u2, a2, u3) → but pop_record removes first 2 non-system
        assert ctx[0] == {"role": "system", "content": "sys"}
        assert ctx[1] == {"role": "user", "content": "u2"}

    @pytest.mark.asyncio
    async def test_test(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        with patch.object(p, "text_chat", AsyncMock(return_value=LLMResponse(role="assistant"))):
            await p.test(test_timeout=5.0)

    def test_ensure_message_to_dicts_none(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        result = p._ensure_message_to_dicts(None)
        assert result == []

    def test_ensure_message_to_dicts_empty(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        result = p._ensure_message_to_dicts([])
        assert result == []

    def test_ensure_message_to_dicts_skips_checkpoint(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        checkpoint = {"role": "user", "content": "check", "checkpoint": True}
        normal = {"role": "user", "content": "normal"}
        with patch(
            "astrbot.core.provider.provider.is_checkpoint_message",
            side_effect=lambda m: m.get("checkpoint", False),
        ):
            result = p._ensure_message_to_dicts([checkpoint, normal])
            assert len(result) == 1
            assert result[0] == {"role": "user", "content": "normal"}

    def test_ensure_message_to_dicts_converts_message_objects(self):
        p = _ConcreteProvider(provider_config={}, provider_settings={})
        msg = MagicMock(spec=Message)
        msg.model_dump.return_value = {"role": "user", "content": "from pydantic"}
        result = p._ensure_message_to_dicts([msg])
        assert result == [{"role": "user", "content": "from pydantic"}]

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
        p = _ConcreteTTSProvider(provider_config={"type": "tts_test"}, provider_settings={})
        assert p.provider_config["type"] == "tts_test"

    def test_get_audio(self):
        p = _ConcreteTTSProvider(provider_config={}, provider_settings={})
        import asyncio

        path = asyncio.run(p.get_audio("hello"))
        assert path == "/tmp/test_output.wav"

    def test_support_stream_default(self):
        p = _ConcreteTTSProvider(provider_config={}, provider_settings={})
        assert p.support_stream() is False

    def test_get_audio_stream_default_implementation(self):
        p = _ConcreteTTSProvider(provider_config={}, provider_settings={})
        import asyncio

        text_queue: asyncio.Queue[str | None] = asyncio.Queue()
        audio_queue: asyncio.Queue = asyncio.Queue()

        async def run_stream():
            # Send some text, then None to signal end
            await text_queue.put("hello ")
            await text_queue.put("world")
            await text_queue.put(None)
            await p.get_audio_stream(text_queue, audio_queue)

        asyncio.run(run_stream())
        result = asyncio.run(audio_queue.get())
        assert result is not None
        text_part, audio_data = result
        assert text_part == "hello world"
        assert isinstance(audio_data, bytes)
        # The None sentinel should follow
        end = asyncio.run(audio_queue.get())
        assert end is None


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

    def test_get_embeddings_batch_multiple_batches(self):
        p = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
        import asyncio

        texts = [f"text_{i}" for i in range(5)]
        embs = asyncio.run(p.get_embeddings_batch(texts, batch_size=2, tasks_limit=5))
        assert len(embs) == 5

    def test_get_embeddings_batch_with_progress_callback(self):
        p = _ConcreteEmbeddingProvider(provider_config={}, provider_settings={})
        import asyncio

        progress = AsyncMock()
        texts = [f"t{i}" for i in range(3)]
        embs = asyncio.run(
            p.get_embeddings_batch(texts, batch_size=2, tasks_limit=5, progress_callback=progress)
        )
        assert len(embs) == 3
        assert progress.await_count >= 1


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
