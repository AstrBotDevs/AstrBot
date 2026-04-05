from unittest.mock import Mock

import pytest

from astrbot.core.provider.sources.whisper_selfhosted_source import (
    ProviderOpenAIWhisperSelfHost,
)


def _make_provider(device: str) -> ProviderOpenAIWhisperSelfHost:
    return ProviderOpenAIWhisperSelfHost(
        provider_config={
            "id": "test-whisper-selfhost",
            "type": "openai_whisper_selfhost",
            "model": "tiny",
            "whisper_device": device,
        },
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_initialize_uses_configured_mps_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _make_provider("mps")
    load_model = Mock(return_value=object())

    monkeypatch.setattr(
        "astrbot.core.provider.sources.whisper_selfhosted_source.whisper.load_model",
        load_model,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.whisper_selfhosted_source.torch.backends.mps.is_available",
        lambda: True,
    )

    await provider.initialize()

    load_model.assert_called_once_with("tiny", device="mps")


@pytest.mark.asyncio
async def test_initialize_falls_back_to_cpu_when_mps_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _make_provider("mps")
    load_model = Mock(return_value=object())

    monkeypatch.setattr(
        "astrbot.core.provider.sources.whisper_selfhosted_source.whisper.load_model",
        load_model,
    )
    monkeypatch.setattr(
        "astrbot.core.provider.sources.whisper_selfhosted_source.torch.backends.mps.is_available",
        lambda: False,
    )

    await provider.initialize()

    load_model.assert_called_once_with("tiny", device="cpu")
