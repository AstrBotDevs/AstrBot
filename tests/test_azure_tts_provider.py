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
