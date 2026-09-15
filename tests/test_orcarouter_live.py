"""Live OrcaRouter checks through the implemented provider code path.

This is the only check that talks to the real service. It is skipped unless
``ORCAROUTER_API_KEY`` is present, and it never prints or asserts on the key
itself. Everything exercised here goes through ``ProviderOrcaRouter`` — the
same code the application uses — rather than a standalone HTTP call.

Run with::

    python3 -m pytest tests/test_orcarouter_live.py -q
"""

from __future__ import annotations

import asyncio
import os

import pytest

from astrbot.core.provider import orcarouter_auth as auth
from astrbot.core.provider.sources.orcarouter_source import ProviderOrcaRouter

API_KEY = os.environ.get("ORCAROUTER_API_KEY", "")

pytestmark = pytest.mark.skipif(
    not API_KEY, reason="ORCAROUTER_API_KEY is not set; live checks are skipped"
)


def _provider(**overrides) -> ProviderOrcaRouter:
    config = {
        "id": "orcarouter-live",
        "type": "orcarouter_chat_completion",
        "provider": "orcarouter",
        "provider_type": "chat_completion",
        "model": "deepseek/deepseek-v4-flash",
        "key": [API_KEY],
        "api_base": "https://api.orcarouter.ai/v1",
        "timeout": 120,
    }
    config.update(overrides)
    return ProviderOrcaRouter(config, {})


def test_live_origins_are_not_derived_from_one_another():
    # Inference goes to the relay; authorization goes to the auth origin.
    assert _provider().provider_config["api_base"] == "https://api.orcarouter.ai/v1"
    assert auth.resolve_auth_base_url() == "https://www.orcarouter.ai"


def test_live_catalog_is_fetched_through_the_provider():
    provider = _provider()

    model_ids = asyncio.run(provider.get_models())

    assert provider.catalog_source == "live"
    assert len(model_ids) > 0
    # IDs keep the vendor namespace exactly as the catalog reports them.
    assert all("/" in model_id for model_id in model_ids), model_ids[:5]


def test_live_text_list_contains_only_chat_compatible_models():
    from astrbot.core.provider import orcarouter_catalog as catalog

    provider = _provider()
    listed = set(asyncio.run(provider.get_models()))
    live = asyncio.run(
        catalog.fetch_live_catalog(provider.provider_config["api_base"], API_KEY)
    )

    expected = {model.id for model in catalog.filter_models(live, "chat")}
    assert listed == expected
    # Dedicated non-text models must not appear in the text list.
    for model in live:
        if model.id in listed:
            assert model.supports_text_chat(), model.id


def test_live_multimodal_list_only_contains_declared_image_models():
    provider = _provider(required_input_modalities=["image"])

    listed = asyncio.run(provider.get_models())

    for model_id in listed:
        assert (
            "image" in provider.catalog_metadata()[model_id]["modalities"]["input"]
        ), f"{model_id} does not declare image input"


def test_live_inference_through_the_provider_returns_text():
    provider = _provider()

    response = asyncio.run(provider.text_chat(prompt="Reply with exactly: PONG"))

    assert response.completion_text
    assert "PONG" in response.completion_text.upper()
