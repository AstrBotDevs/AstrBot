from astrbot.core.config.default import CONFIG_METADATA_2


def test_magpie_provider_template_uses_local_openai_gateway_defaults():
    """Verify the Magpie provider preset targets its local OpenAI gateway."""
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    template = templates["Magpie"]

    assert template["id"] == "magpie"
    assert template["provider"] == "openai"
    assert template["type"] == "openai_chat_completion"
    assert template["provider_type"] == "chat_completion"
    assert template["key"] == ["magpie"]
    assert template["api_base"] == "http://127.0.0.1:3425/v1"
