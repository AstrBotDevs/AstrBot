from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.mirarouter_source import ProviderMiraRouter


def test_mirarouter_template_and_attribution_header():
    """Verify the MiraRouter preset and AstrBot attribution header."""
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    template = templates["MiraRouter"]

    assert template["provider"] == "mirarouter"
    assert template["type"] == "mirarouter_chat_completion"
    assert template["api_base"] == "https://api.mirarouter.com/v1"
    assert template["proxy_mode"] == "inherit"
    assert template["proxy_url"] == ""

    provider = ProviderMiraRouter(
        {
            **template,
            "id": "mirarouter-test",
            "model": "test-model",
            "key": ["test-key"],
        },
        {},
    )

    assert str(provider.client.base_url) == "https://api.mirarouter.com/v1/"
    assert provider.client._custom_headers["X-APP-CODE"] == "astrbot"
