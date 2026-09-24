import copy

import pytest
import pytest_asyncio
from aiohttp import web

from astrbot import __version__
from astrbot.core.provider.headers import DEFAULT_USER_AGENT, build_provider_headers
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.bailian_rerank_source import BailianRerankProvider
from astrbot.core.provider.sources.dashscope_embedding_source import (
    DashScopeEmbeddingProvider,
)
from astrbot.core.provider.sources.gemini_embedding_source import (
    GeminiEmbeddingProvider,
)
from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI
from astrbot.core.provider.sources.gemini_tts_source import ProviderGeminiTTSAPI
from astrbot.core.provider.sources.kimi_code_source import ProviderKimiCode
from astrbot.core.provider.sources.nvidia_embedding_source import (
    NvidiaEmbeddingProvider,
)
from astrbot.core.provider.sources.nvidia_rerank_source import NvidiaRerankProvider
from astrbot.core.provider.sources.ollama_embedding_source import (
    OllamaEmbeddingProvider,
)
from astrbot.core.provider.sources.openai_embedding_source import (
    OpenAIEmbeddingProvider,
)
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.provider.sources.openai_tts_api_source import ProviderOpenAITTSAPI
from astrbot.core.provider.sources.tei_rerank_source import TEIRerankProvider
from astrbot.core.provider.sources.vllm_rerank_source import VLLMRerankProvider
from astrbot.core.provider.sources.whisper_api_source import ProviderOpenAIWhisperAPI


@pytest.mark.parametrize(
    "custom_headers", [None, {}, [], "invalid", {"User-Agent": " "}]
)
def test_provider_headers_default_to_current_version(custom_headers):
    assert build_provider_headers(custom_headers) == {
        "User-Agent": f"astrbot/{__version__}"
    }


@pytest.mark.parametrize("name", ["User-Agent", "user-agent", "USER-AGENT"])
def test_provider_headers_preserve_custom_values_without_mutation(name):
    custom = {name: "custom/1.0", "X-Trace-Id": 123}
    original = copy.deepcopy(custom)
    assert build_provider_headers(custom) == {
        "User-Agent": "custom/1.0",
        "X-Trace-Id": "123",
    }
    assert custom == original


@pytest_asyncio.fixture
async def provider_http_server(unused_tcp_port, monkeypatch):
    """Capture actual SDK requests without contacting external providers."""
    requests = []
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")

    async def handle(request):
        requests.append(request.headers)
        return web.json_response(
            {
                "object": "list",
                "data": [],
                "models": [],
                "output": {"embeddings": [{"embedding": [0.1], "text_index": 0}]},
            }
        )

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        yield f"http://127.0.0.1:{unused_tcp_port}", requests
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls",
    [
        ProviderOpenAIOfficial,
        ProviderOpenAIResponses,
        OpenAIEmbeddingProvider,
        ProviderOpenAITTSAPI,
        ProviderOpenAIWhisperAPI,
        ProviderAnthropic,
        ProviderKimiCode,
        ProviderGoogleGenAI,
        GeminiEmbeddingProvider,
        ProviderGeminiTTSAPI,
    ],
)
@pytest.mark.parametrize("custom_headers", [{}, {"user-agent": "custom/1.0"}])
async def test_provider_sdk_sends_exactly_one_user_agent(
    provider_cls, custom_headers, provider_http_server
):
    base_url, requests = provider_http_server
    config = {
        "id": "test-provider",
        "model": "test-model",
        "key": ["test-key"],
        "api_key": "test-key",
        "api_base": base_url,
        "embedding_api_key": "test-key",
        "embedding_api_base": base_url,
        "gemini_tts_api_key": "test-key",
        "gemini_tts_api_base": base_url,
        "custom_headers": custom_headers,
    }
    original = copy.deepcopy(config)
    provider = provider_cls(config, {})
    try:
        await provider.client.models.list()
        assert len(requests) == 1
        assert requests[0].getall("User-Agent") == [
            custom_headers.get("user-agent", DEFAULT_USER_AGENT)
        ]
        assert config == original
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls",
    [
        BailianRerankProvider,
        TEIRerankProvider,
        VLLMRerankProvider,
        NvidiaEmbeddingProvider,
        NvidiaRerankProvider,
        OllamaEmbeddingProvider,
    ],
)
@pytest.mark.parametrize("custom_headers", [{}, {"USER-AGENT": "custom/1.0"}])
async def test_aiohttp_provider_sends_user_agent(
    provider_cls, custom_headers, provider_http_server
):
    base_url, requests = provider_http_server
    provider = provider_cls(
        {
            "embedding_api_key": "test-key",
            "embedding_api_base": base_url,
            "rerank_api_key": "test-key",
            "rerank_api_base": base_url,
            "custom_headers": custom_headers,
        },
        {},
    )
    try:
        client = provider.client or await provider._get_client()
        async with client.get(base_url) as response:
            assert response.status == 200
        assert requests[0].getall("User-Agent") == [
            custom_headers.get("USER-AGENT", DEFAULT_USER_AGENT)
        ]
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["text-embedding-v4", "qwen3-vl-embedding"])
@pytest.mark.parametrize("custom_headers", [{}, {"User-Agent": "custom/1.0"}])
async def test_dashscope_sends_user_agent(model, custom_headers, provider_http_server):
    base_url, requests = provider_http_server
    provider = DashScopeEmbeddingProvider(
        {
            "embedding_api_key": "test-key",
            "embedding_api_base": base_url,
            "embedding_model": model,
            "custom_headers": custom_headers,
        },
        {},
    )
    assert await provider.get_embeddings(["hello"]) == [[0.1]]
    assert requests[0].getall("User-Agent") == [
        custom_headers.get("User-Agent", DEFAULT_USER_AGENT)
    ]


@pytest.mark.asyncio
async def test_edge_tts_synthesis_uses_astrbot_user_agent(monkeypatch, unused_tcp_port):
    edge_tts = pytest.importorskip("edge_tts")
    from astrbot.core.provider.sources import edge_tts_source  # noqa: F401

    requests = []

    async def handle(request):
        requests.append(request.headers)
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        await websocket.receive()
        await websocket.receive()
        await websocket.close()
        return websocket

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    monkeypatch.setattr(
        edge_tts.communicate, "WSS_URL", f"ws://127.0.0.1:{unused_tcp_port}/?test=1"
    )
    try:
        await web.TCPSite(runner, "127.0.0.1", unused_tcp_port).start()
        with pytest.raises(edge_tts.exceptions.NoAudioReceived):
            async for _ in edge_tts.Communicate("hello", "en-US-AriaNeural").stream():
                pass
        assert requests[0].getall("User-Agent") == [DEFAULT_USER_AGENT]
    finally:
        await runner.cleanup()
