from astrbot.core.provider.sources.volcengine_tts import ProviderVolcengineTTS


def test_build_loggable_payload_redacts_api_key() -> None:
    provider = ProviderVolcengineTTS(
        {
            "api_key": "secret-token",
            "appid": "appid",
            "volcengine_cluster": "cluster",
            "volcengine_voice_type": "voice",
        },
        {},
    )
    payload = provider._build_request_payload("hello")

    loggable_payload = provider._build_loggable_payload(payload)

    assert payload["app"]["token"] == "secret-token"
    assert loggable_payload["app"]["token"] == "***"  # type: ignore[index]
    assert loggable_payload["request"]["text"] == "hello"  # type: ignore[index]
