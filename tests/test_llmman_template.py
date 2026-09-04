from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.ollama_embedding_source import (
    OllamaEmbeddingProvider,
)

TEMPLATES = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
    "config_template"
]


def test_llmman_chat_template_uses_openai_route_on_17434():
    template = TEMPLATES["llmman"]

    assert template["provider"] == "llmman"
    assert template["type"] == "openai_chat_completion"
    assert template["api_base"] == "http://127.0.0.1:17434/v1"
    assert template["key"] == ["llmman"]


def test_llmman_embedding_template_uses_ollama_route_on_17434():
    template = TEMPLATES["llmman Embedding"]

    assert template["provider"] == "llmman"
    assert template["type"] == "ollama_embedding"

    provider = OllamaEmbeddingProvider({**template, "id": "llmman-test"}, {})

    assert provider.base_url == "http://localhost:17434"
    assert provider.model == "nomic-embed-text"
