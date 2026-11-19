from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial


def test_runcrate_template_uses_openai_compatible_endpoint():
    """Verify the Runcrate preset builds an OpenAI-compatible client."""
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["Runcrate"]

    assert template["provider"] == "runcrate"
    assert template["type"] == "openai_chat_completion"
    assert template["api_base"] == "https://api.runcrate.ai/v1"

    provider = ProviderOpenAIOfficial(
        {
            **template,
            "id": "runcrate-test",
            "model": "deepseek-ai/DeepSeek-V4.1-Flash",
            "key": ["test-key"],
        },
        {},
    )

    assert str(provider.client.base_url) == "https://api.runcrate.ai/v1/"
