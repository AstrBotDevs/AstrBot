from astrbot.core.config.default import CONFIG_METADATA_2


def test_worldrouter_template_uses_openai_compatible_endpoint():
    """Verify the WorldRouter preset targets its OpenAI-compatible endpoint."""
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["WorldRouter"]

    assert template["id"] == "worldrouter"
    assert template["provider"] == "worldrouter"
    assert template["type"] == "openai_chat_completion"
    assert template["provider_type"] == "chat_completion"
    assert template["api_base"] == "https://inference-api.worldrouter.ai/v1"
