import pytest

from astrbot.core.provider.sources.azure_tts_source import AzureTTSProvider


@pytest.mark.parametrize("key_length", [32, 84])
def test_azure_tts_accepts_subscription_keys_with_supported_lengths(key_length: int):
    config = {
        "azure_tts_subscription_key": "A" * key_length,
        "azure_tts_region": "eastus",
        "azure_tts_voice": "zh-CN-XiaoxiaoNeural",
    }

    provider = AzureTTSProvider(config, {})
    assert provider.provider is not None


@pytest.mark.parametrize(
    "invalid_key",
    [
        "",
        "A" * 31,
        "A" * 33,
        "A" * 83,
        "A" * 85,
        ("A" * 31) + "-",
        ("A" * 31) + "_",
        ("A" * 31) + "~",
    ],
)
def test_azure_tts_rejects_invalid_subscription_keys(invalid_key: str):
    config = {
        "azure_tts_subscription_key": invalid_key,
        "azure_tts_region": "eastus",
        "azure_tts_voice": "zh-CN-XiaoxiaoNeural",
    }

    with pytest.raises(ValueError):
        AzureTTSProvider(config, {})
