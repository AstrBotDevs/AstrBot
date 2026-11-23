from astrbot.core.config.default import CONFIG_METADATA_2


def test_bf16_provider_template_registered() -> None:
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    assert "bf16.ai" in templates
    bf16 = templates["bf16.ai"]
    assert bf16["id"] == "bf16"
    assert bf16["provider"] == "bf16"
    assert bf16["type"] == "openai_chat_completion"
    assert bf16["provider_type"] == "chat_completion"
    assert bf16["api_base"] == "https://api.bf16.ai/v1"
