from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.nvidia_embedding_source import (
    NvidiaEmbeddingProvider,
)

NEW_MODEL = "nvidia/nemotron-3-embed-1b"
OLD_MODEL = "nvidia/llama-nemotron-embed-1b-v2"


def test_nvidia_embedding_config_template_uses_new_model_and_dimension():
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    assert templates["NVIDIA Embedding"]["embedding_model"] == NEW_MODEL
    assert templates["NVIDIA Embedding"]["embedding_dimensions"] == 2048


def test_nvidia_embedding_provider_uses_new_fallback_model():
    provider = NvidiaEmbeddingProvider({}, {})

    assert provider.model == NEW_MODEL
    assert provider.get_model() == NEW_MODEL


def test_nvidia_embedding_provider_preserves_explicit_old_model():
    provider = NvidiaEmbeddingProvider(
        {
            "embedding_model": OLD_MODEL,
            "embedding_dimensions": 1024,
        },
        {},
    )

    assert provider.model == OLD_MODEL
    assert provider.get_dim() == 1024


def test_nvidia_embedding_new_model_uses_existing_api_contract():
    provider = NvidiaEmbeddingProvider(
        {
            "embedding_model": NEW_MODEL,
            "input_type": "passage",
        },
        {},
    )

    assert provider._build_payload(["first", "second"]) == {
        "input": ["first", "second"],
        "model": NEW_MODEL,
        "input_type": "passage",
        "encoding_format": "float",
    }
    assert provider._parse_response(
        {
            "data": [
                {"index": 0, "embedding": [0.1, 0.2]},
                {"index": 1, "embedding": [0.3, 0.4]},
            ]
        }
    ) == [[0.1, 0.2], [0.3, 0.4]]
