# ruff: noqa: E402
from __future__ import annotations

import base64
import sys
import types
from types import SimpleNamespace

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})


_install_optional_dependency_stubs()

from astrbot.core.provider.entities import LLMResponse as CoreLLMResponse
from astrbot.core.provider.entities import TokenUsage
from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge
from astrbot_sdk.clients.llm import ChatMessage, LLMClient
from astrbot_sdk.errors import AstrBotError


class _RecordingProxy:
    def __init__(
        self,
        *,
        call_output: dict | None = None,
        stream_output: list[dict] | None = None,
    ) -> None:
        self.call_output = call_output or {"text": "ok"}
        self.stream_output = stream_output or []
        self.calls: list[tuple[str, dict]] = []
        self.stream_calls: list[tuple[str, dict]] = []

    async def call(self, capability: str, payload: dict) -> dict:
        self.calls.append((capability, dict(payload)))
        return dict(self.call_output)

    async def stream(self, capability: str, payload: dict):
        self.stream_calls.append((capability, dict(payload)))
        for item in self.stream_output:
            yield dict(item)


class _FakeToken:
    def raise_if_cancelled(self) -> None:
        return None


class _FakeProvider:
    def __init__(
        self,
        *,
        text_response: CoreLLMResponse | None = None,
        stream_responses: list[CoreLLMResponse] | None = None,
        stream_exception: Exception | None = None,
    ) -> None:
        self.text_response = text_response or CoreLLMResponse(
            role="assistant",
            completion_text="ok",
        )
        self.stream_responses = stream_responses or []
        self.stream_exception = stream_exception
        self.text_chat_calls: list[dict] = []
        self.text_chat_stream_calls: list[dict] = []

    async def text_chat(self, **kwargs) -> CoreLLMResponse:
        self.text_chat_calls.append(dict(kwargs))
        return self.text_response

    async def text_chat_stream(self, **kwargs):
        self.text_chat_stream_calls.append(dict(kwargs))
        if self.stream_exception is not None:
            raise self.stream_exception
        for response in self.stream_responses:
            yield response


class _FakeStarContext:
    def __init__(
        self,
        *,
        provider_by_id: _FakeProvider | None = None,
        using_provider: _FakeProvider | None = None,
        rerank_providers: list[object] | None = None,
    ) -> None:
        self._provider_by_id = provider_by_id
        self._using_provider = using_provider
        self._rerank_providers = rerank_providers or []
        self.provider_by_id_calls: list[str] = []
        self.using_provider_calls: list[str | None] = []

    def get_provider_by_id(self, provider_id: str):
        self.provider_by_id_calls.append(provider_id)
        return self._provider_by_id

    def get_using_provider(self, umo: str | None = None):
        self.using_provider_calls.append(umo)
        return self._using_provider

    def get_all_rerank_providers(self):
        return list(self._rerank_providers)


class _FakePluginBridge:
    def __init__(self, umo: str = "umo:test") -> None:
        self._request_context = SimpleNamespace(
            event=SimpleNamespace(unified_msg_origin=umo),
        )

    def resolve_request_session(self, _request_id: str):
        return self._request_context


class _FakeSTTProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_text(self, audio_url: str) -> str:
        self.calls.append(audio_url)
        return f"text:{audio_url}"


class _FakeTTSProvider:
    def __init__(self, *, support_stream: bool = True) -> None:
        self.support_stream_value = support_stream
        self.get_audio_calls: list[str] = []
        self.stream_inputs: list[str] = []

    def support_stream(self) -> bool:
        return self.support_stream_value

    async def get_audio(self, text: str) -> str:
        self.get_audio_calls.append(text)
        return f"/tmp/{text}.wav"

    async def get_audio_stream(self, text_queue, audio_queue) -> None:
        while True:
            item = await text_queue.get()
            if item is None:
                break
            self.stream_inputs.append(item)
            await audio_queue.put((item, f"audio:{item}".encode()))
        await audio_queue.put(None)


class _FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.single_calls: list[str] = []
        self.batch_calls: list[list[str]] = []

    async def get_embedding(self, text: str) -> list[float]:
        self.single_calls.append(text)
        return [0.1, 0.2]

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [[float(index), float(index + 1)] for index, _ in enumerate(texts)]

    def get_dim(self) -> int:
        return 2


class _FakeRerankItem:
    def __init__(self, index: int, relevance_score: float) -> None:
        self.index = index
        self.relevance_score = relevance_score


class _FakeRerankProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], int | None]] = []

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[_FakeRerankItem]:
        self.calls.append((query, list(documents), top_n))
        return [
            _FakeRerankItem(index=1, relevance_score=0.9),
            _FakeRerankItem(index=0, relevance_score=0.3),
        ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_client_prefers_contexts_and_omits_history_from_payload() -> None:
    proxy = _RecordingProxy()
    client = LLMClient(proxy)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup_weather",
                "description": "Look up weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]

    await client.chat(
        "hello",
        history=[ChatMessage(role="user", content="from-history")],
        contexts=[{"role": "assistant", "content": "from-contexts"}],
        provider_id="provider-1",
        tool_calls_result=[{"role": "tool", "content": "done"}],
        image_urls=["https://example.com/a.png"],
        tools=tools,
    )

    capability, payload = proxy.calls[0]
    assert capability == "llm.chat"
    assert payload["contexts"] == [{"role": "assistant", "content": "from-contexts"}]
    assert "history" not in payload
    assert payload["provider_id"] == "provider-1"
    assert payload["tool_calls_result"] == [{"role": "tool", "content": "done"}]
    assert payload["image_urls"] == ["https://example.com/a.png"]
    assert payload["tools"] == tools


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_client_chat_raw_keeps_old_fields_and_accepts_optional_extensions() -> (
    None
):
    proxy = _RecordingProxy(
        call_output={
            "text": "done",
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            "finish_reason": "stop",
            "tool_calls": [],
            "role": "assistant",
            "reasoning_content": "thinking",
            "reasoning_signature": "sig-1",
        }
    )
    client = LLMClient(proxy)

    response = await client.chat_raw(
        "hello",
        history=[ChatMessage(role="user", content="old")],
        contexts=[{"role": "assistant", "content": "new"}],
    )

    assert response.text == "done"
    assert response.usage == {
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
    }
    assert response.finish_reason == "stop"
    assert response.tool_calls == []
    assert response.role == "assistant"
    assert response.reasoning_content == "thinking"
    assert response.reasoning_signature == "sig-1"

    capability, payload = proxy.calls[0]
    assert capability == "llm.chat_raw"
    assert payload["contexts"] == [{"role": "assistant", "content": "new"}]
    assert "history" not in payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_llm_bridge_uses_explicit_provider_id() -> None:
    provider = _FakeProvider(
        text_response=CoreLLMResponse(role="assistant", completion_text="explicit")
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(provider_by_id=provider),
        plugin_bridge=_FakePluginBridge(),
    )

    result = await bridge._llm_chat(
        "req-1",
        {"prompt": "hello", "provider_id": "provider-explicit"},
        None,
    )

    assert result == {"text": "explicit"}
    assert provider.text_chat_calls[0]["prompt"] == "hello"
    assert provider.text_chat_calls[0]["contexts"] is None
    assert bridge._star_context.provider_by_id_calls == ["provider-explicit"]
    assert bridge._star_context.using_provider_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_llm_bridge_prefers_contexts_over_history_without_mixing() -> None:
    provider = _FakeProvider(
        text_response=CoreLLMResponse(role="assistant", completion_text="session")
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(using_provider=provider),
        plugin_bridge=_FakePluginBridge(umo="umo:session"),
    )

    await bridge._llm_chat(
        "req-2",
        {
            "prompt": "hello",
            "history": [{"role": "user", "content": "from-history"}],
            "contexts": [{"role": "assistant", "content": "from-contexts"}],
            "tool_calls_result": [{"role": "tool", "content": "done"}],
            "image_urls": ["https://example.com/a.png"],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup_weather",
                        "description": "Look up weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }
            ],
        },
        None,
    )

    kwargs = provider.text_chat_calls[0]
    assert kwargs["contexts"] == [{"role": "assistant", "content": "from-contexts"}]
    assert kwargs["tool_calls_result"] == [{"role": "tool", "content": "done"}]
    assert kwargs["image_urls"] == ["https://example.com/a.png"]
    assert "history" not in kwargs
    assert kwargs["func_tool"] is not None
    assert kwargs["func_tool"].names() == ["lookup_weather"]
    tool = kwargs["func_tool"].get_tool("lookup_weather")
    assert tool is not None
    assert tool.description == "Look up weather"
    assert tool.parameters == {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }
    assert bridge._star_context.using_provider_calls == ["umo:session"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_llm_bridge_raises_when_no_provider_available() -> None:
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(),
        plugin_bridge=_FakePluginBridge(),
    )

    with pytest.raises(AstrBotError, match="No active chat provider is available"):
        await bridge._llm_chat("req-3", {"prompt": "hello"}, None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_llm_bridge_chat_raw_keeps_old_fields_and_returns_optional_extensions() -> (
    None
):
    provider = _FakeProvider(
        text_response=CoreLLMResponse(
            role="assistant",
            completion_text="raw-text",
            reasoning_content="reasoning",
            reasoning_signature="sig-raw",
            usage=TokenUsage(input_other=2, input_cached=1, output=4),
        )
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(using_provider=provider),
        plugin_bridge=_FakePluginBridge(),
    )

    result = await bridge._llm_chat_raw("req-4", {"prompt": "hello"}, None)

    assert result["text"] == "raw-text"
    assert result["usage"] == {
        "input_tokens": 3,
        "output_tokens": 4,
        "total_tokens": 7,
    }
    assert result["finish_reason"] == "stop"
    assert result["tool_calls"] == []
    assert result["role"] == "assistant"
    assert result["reasoning_content"] == "reasoning"
    assert result["reasoning_signature"] == "sig-raw"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_llm_stream_chat_uses_real_stream_without_duplicate_final_text() -> (
    None
):
    provider = _FakeProvider(
        stream_responses=[
            CoreLLMResponse(role="assistant", completion_text="he", is_chunk=True),
            CoreLLMResponse(role="assistant", completion_text="llo", is_chunk=True),
            CoreLLMResponse(role="assistant", completion_text="hello", is_chunk=False),
        ]
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(using_provider=provider),
        plugin_bridge=_FakePluginBridge(),
    )

    execution = await bridge._llm_stream_chat(
        "req-5", {"prompt": "hello"}, _FakeToken()
    )
    chunks: list[dict] = []
    async for item in execution.iterator:
        chunks.append(item)

    assert [item["text"] for item in chunks if "text" in item] == ["he", "llo"]
    assert execution.finalize(chunks) == {"text": "hello"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_llm_stream_chat_falls_back_only_on_not_implemented_error() -> None:
    provider = _FakeProvider(
        text_response=CoreLLMResponse(role="assistant", completion_text="fallback"),
        stream_exception=NotImplementedError(),
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(using_provider=provider),
        plugin_bridge=_FakePluginBridge(),
    )

    execution = await bridge._llm_stream_chat(
        "req-6", {"prompt": "hello"}, _FakeToken()
    )
    chunks: list[dict] = []
    async for item in execution.iterator:
        chunks.append(item)

    assert "".join(item.get("text", "") for item in chunks) == "fallback"
    assert execution.finalize(chunks) == {"text": "fallback"}
    assert len(provider.text_chat_stream_calls) == 1
    assert len(provider.text_chat_calls) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_llm_stream_chat_does_not_swallow_non_not_implemented_errors() -> (
    None
):
    provider = _FakeProvider(stream_exception=RuntimeError("stream failed"))
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(using_provider=provider),
        plugin_bridge=_FakePluginBridge(),
    )

    execution = await bridge._llm_stream_chat(
        "req-7", {"prompt": "hello"}, _FakeToken()
    )

    with pytest.raises(RuntimeError, match="stream failed"):
        async for _item in execution.iterator:
            pass

    assert len(provider.text_chat_stream_calls) == 1
    assert provider.text_chat_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_provider_bridge_specialized_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stt_provider = _FakeSTTProvider()
    tts_provider = _FakeTTSProvider()
    embedding_provider = _FakeEmbeddingProvider()
    rerank_provider = _FakeRerankProvider()
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capability_bridge._get_runtime_provider_types",
        lambda: (
            _FakeSTTProvider,
            _FakeTTSProvider,
            _FakeEmbeddingProvider,
            _FakeRerankProvider,
        ),
    )

    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(provider_by_id=stt_provider),
        plugin_bridge=_FakePluginBridge(),
    )
    assert await bridge._provider_stt_get_text(
        "req-stt",
        {"provider_id": "stt-provider", "audio_url": "audio.wav"},
        None,
    ) == {"text": "text:audio.wav"}

    bridge._star_context._provider_by_id = tts_provider
    assert await bridge._provider_tts_get_audio(
        "req-tts",
        {"provider_id": "tts-provider", "text": "hello"},
        None,
    ) == {"audio_path": "/tmp/hello.wav"}
    assert await bridge._provider_tts_support_stream(
        "req-tts-support",
        {"provider_id": "tts-provider"},
        None,
    ) == {"supported": True}

    execution = await bridge._provider_tts_get_audio_stream(
        "req-tts-stream",
        {"provider_id": "tts-provider", "text_chunks": ["hello", "sdk"]},
        _FakeToken(),
    )
    streamed = [item async for item in execution.iterator]
    assert [item["text"] for item in streamed] == ["hello", "sdk"]
    assert [
        base64.b64decode(item["audio_base64"]) for item in streamed
    ] == [b"audio:hello", b"audio:sdk"]
    assert tts_provider.stream_inputs == ["hello", "sdk"]

    bridge._star_context._provider_by_id = embedding_provider
    assert await bridge._provider_embedding_get_embedding(
        "req-embedding",
        {"provider_id": "embedding-provider", "text": "hello"},
        None,
    ) == {"embedding": [0.1, 0.2]}
    assert await bridge._provider_embedding_get_embeddings(
        "req-embedding-many",
        {"provider_id": "embedding-provider", "texts": ["a", "b"]},
        None,
    ) == {"embeddings": [[0.0, 1.0], [1.0, 2.0]]}
    assert await bridge._provider_embedding_get_dim(
        "req-embedding-dim",
        {"provider_id": "embedding-provider"},
        None,
    ) == {"dim": 2}

    bridge._star_context._provider_by_id = rerank_provider
    assert await bridge._provider_rerank_rerank(
        "req-rerank",
        {
            "provider_id": "rerank-provider",
            "query": "hello",
            "documents": ["doc-0", "doc-1"],
            "top_n": 2,
        },
        None,
    ) == {
        "results": [
            {"index": 1, "score": 0.9, "document": "doc-1"},
            {"index": 0, "score": 0.3, "document": "doc-0"},
        ]
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_provider_bridge_rejects_provider_type_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capability_bridge._get_runtime_provider_types",
        lambda: (
            _FakeSTTProvider,
            _FakeTTSProvider,
            _FakeEmbeddingProvider,
            _FakeRerankProvider,
        ),
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(provider_by_id=_FakeSTTProvider()),
        plugin_bridge=_FakePluginBridge(),
    )

    with pytest.raises(AstrBotError, match="text_to_speech provider"):
        await bridge._provider_tts_get_audio(
            "req-mismatch",
            {"provider_id": "wrong-provider", "text": "hello"},
            None,
        )
