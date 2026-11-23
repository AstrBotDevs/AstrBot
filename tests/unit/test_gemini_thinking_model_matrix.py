"""Valid thinking levels follow the current Gemini model-family contract."""

import pytest
from google.genai import types

from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI

GEMINI_4_MODEL_LEVELS = (
    ("gemini-4.0-flash", ("LOW", "MEDIUM", "HIGH", "XHIGH")),
    ("gemini-4.1-flash-preview", ("LOW", "MEDIUM", "HIGH", "XHIGH")),
    ("gemini-4-other", ("LOW", "MEDIUM", "HIGH", "XHIGH")),
    ("gemini-4-carbon", ("LOW", "MEDIUM", "HIGH")),
    ("gemini-4-argon-preview", ("LOW", "MEDIUM", "HIGH")),
    ("gemini-4-neon", ("LOW", "MEDIUM", "HIGH", "XHIGH")),
    ("gemini-4-hydrogen-preview", ("LOW", "MEDIUM", "HIGH", "XHIGH")),
)


@pytest.fixture
def thinking_matrix_provider() -> ProviderGoogleGenAI:
    """Build a real config adapter without initializing an API client."""
    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {}
    provider.provider_settings = {}
    provider.model_name = "gemini-2.5-flash"
    provider.safety_settings = []
    return provider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "level"),
    [
        pytest.param(model, level, id=f"{model}-{level.lower()}")
        for model, levels in GEMINI_4_MODEL_LEVELS
        for level in levels
    ],
)
async def test_gemini_4_valid_reasoning_effort_is_serialized(
    thinking_matrix_provider: ProviderGoogleGenAI, model: str, level: str
) -> None:
    """Honor the request model and reasoning_effort over a stale legacy level."""
    provider = thinking_matrix_provider
    provider.provider_config = {
        "gm_thinking_config": {"level": "MINIMAL"},
        "custom_extra_body": {"reasoning_effort": level.lower()},
    }

    config = await provider._prepare_query_config({"model": model})

    assert config.thinking_config is not None
    assert config.thinking_config.model_dump(exclude_none=True) == {
        "thinking_level": types.ThinkingLevel(level),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["LOW", "MEDIUM", "HIGH"])
async def test_gemini_38_valid_legacy_thinking_level_is_serialized(
    thinking_matrix_provider: ProviderGoogleGenAI, level: str
) -> None:
    """Keep valid Gemini 3.8 levels on the legacy configuration field."""
    provider = thinking_matrix_provider
    provider.provider_config = {"gm_thinking_config": {"level": level.lower()}}

    config = await provider._prepare_query_config({"model": "gemini-3.8-flash"})

    assert config.thinking_config is not None
    assert config.thinking_config.model_dump(exclude_none=True) == {
        "thinking_level": types.ThinkingLevel(level),
    }
