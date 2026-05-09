from astrbot.core.provider.sources.minimax_tts_api_source import ProviderMiniMaxTTSAPI


def _provider_config(**overrides):
    config = {
        "api_key": "test-key",
        "model": "speech-02-hd",
        "minimax-group-id": "group-id",
    }
    config.update(overrides)
    return config


def test_minimax_tts_empty_timber_weight_uses_default():
    provider = ProviderMiniMaxTTSAPI(
        _provider_config(**{"minimax-timber-weight": ""}),
        {},
    )

    assert provider.timber_weight == [
        {"voice_id": "Chinese (Mandarin)_Warm_Girl", "weight": 1},
    ]


def test_minimax_tts_whitespace_timber_weight_uses_default():
    provider = ProviderMiniMaxTTSAPI(
        _provider_config(**{"minimax-timber-weight": "  \n  "}),
        {},
    )

    assert provider.timber_weight == [
        {"voice_id": "Chinese (Mandarin)_Warm_Girl", "weight": 1},
    ]


def test_minimax_tts_keeps_custom_timber_weight():
    provider = ProviderMiniMaxTTSAPI(
        _provider_config(
            **{
                "minimax-timber-weight": (
                    '[{"voice_id": "Chinese (Mandarin)_BashfulGirl", "weight": 3}]'
                ),
            },
        ),
        {},
    )

    assert provider.timber_weight == [
        {"voice_id": "Chinese (Mandarin)_BashfulGirl", "weight": 3},
    ]
