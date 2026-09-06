"""Smoke tests for ProviderVolcengineTTS."""
import pytest

from astrbot.core.provider.sources.volcengine_tts import ProviderVolcengineTTS


def test_volcengine_tts_import():
    assert ProviderVolcengineTTS is not None


def test_volcengine_tts_construction():
    provider = ProviderVolcengineTTS(
        provider_config={
            "api_key": "test-key",
            "appid": "test-app",
            "volcengine_cluster": "volc_tts",
            "volcengine_voice_type": "zh_female_01",
        },
        provider_settings={},
    )
    assert provider.api_key == "test-key"
    assert provider.appid == "test-app"
    assert provider.cluster == "volc_tts"
    assert provider.voice_type == "zh_female_01"
    assert provider.speed_ratio == 1.0


def test_volcengine_tts_defaults():
    provider = ProviderVolcengineTTS(
        provider_config={},
        provider_settings={},
    )
    assert provider.api_key == ""
    assert provider.appid == ""
    assert provider.speed_ratio == 1.0
    assert provider.api_base == "https://openspeech.bytedance.com/api/v1/tts"
    assert provider.timeout == 20


def test_build_request_payload():
    provider = ProviderVolcengineTTS(
        provider_config={
            "api_key": "test-key",
            "appid": "test-app",
            "volcengine_cluster": "volc_tts",
            "volcengine_voice_type": "zh_female_01",
        },
        provider_settings={},
    )
    payload = provider._build_request_payload("Hello world")
    assert payload["app"]["appid"] == "test-app"
    assert payload["app"]["token"] == "test-key"
    assert payload["app"]["cluster"] == "volc_tts"
    assert payload["audio"]["voice_type"] == "zh_female_01"
    assert payload["request"]["text"] == "Hello world"
    assert payload["request"]["operation"] == "query"


def test_build_loggable_payload_masks_token():
    provider = ProviderVolcengineTTS(
        provider_config={"api_key": "secret-key"},
        provider_settings={},
    )
    payload = provider._build_request_payload("test")
    loggable = provider._build_loggable_payload(payload)
    assert loggable["app"]["token"] == "***"
    assert "text" in loggable["request"]


def test_build_loggable_payload_with_none():
    loggable = ProviderVolcengineTTS._build_loggable_payload({})
    assert loggable == {"app": {}, "user": {}, "audio": {}, "request": {}}
