from unittest.mock import patch

import pytest

from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI


def _build_provider(provider_settings: dict) -> ProviderGoogleGenAI:
    with patch.object(ProviderGoogleGenAI, "_init_client", lambda self: None):
        return ProviderGoogleGenAI(
            {
                "key": ["test-key"],
                "model": "gemini-3-pro-image-preview",
                "timeout": 30,
                "gm_safety_settings": {},
            },
            provider_settings,
        )


@pytest.mark.asyncio
async def test_prepare_query_config_keeps_image_modalities_for_non_stream_requests():
    provider = _build_provider({"streaming_response": True})

    config = await provider._prepare_query_config(
        payloads={"messages": [], "model": "gemini-3-pro-image-preview"},
        modalities=["TEXT", "IMAGE"],
        streaming=False,
    )

    assert config.response_modalities == ["TEXT", "IMAGE"]


@pytest.mark.asyncio
async def test_prepare_query_config_downgrades_image_modalities_for_stream_requests():
    provider = _build_provider({"streaming_response": False})

    config = await provider._prepare_query_config(
        payloads={"messages": [], "model": "gemini-3-pro-image-preview"},
        modalities=["TEXT", "IMAGE"],
        streaming=True,
    )

    assert config.response_modalities == ["TEXT"]
