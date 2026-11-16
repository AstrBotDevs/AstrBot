import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.datastructures import Headers, UploadFile

from astrbot.dashboard.services import chat_service
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError


@pytest.fixture
def transcription_service(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_service, "get_astrbot_temp_path", lambda: str(tmp_path))
    providers = [
        SimpleNamespace(
            meta=lambda: SimpleNamespace(id="first"),
            get_text=AsyncMock(return_value=" first text "),
        ),
        SimpleNamespace(
            meta=lambda: SimpleNamespace(id="second"),
            get_text=AsyncMock(return_value="second text"),
        ),
    ]
    service = object.__new__(ChatService)
    service.core_lifecycle = SimpleNamespace(
        provider_manager=SimpleNamespace(stt_provider_insts=providers)
    )

    async def convert(source, destination, **kwargs):
        assert Path(source).read_bytes() == b"recording"
        assert kwargs == {"sample_rate": 16000, "channels": 1}
        Path(destination).write_bytes(b"wav")
        return destination

    monkeypatch.setattr(chat_service, "convert_audio_to_wav", convert)
    return service, providers, tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_id,expected", [("", "first"), ("second", "second")])
async def test_transcription_selects_provider_and_cleans_temporary_audio(
    transcription_service, provider_id, expected
):
    service, providers, directory = transcription_service
    upload = UploadFile(
        BytesIO(b"recording"),
        filename="../../recording.webm",
        headers=Headers({"content-type": "audio/webm"}),
    )
    result = await service.transcribe_audio(upload, provider_id)
    assert result == {"provider_id": expected, "text": f"{expected} text"}
    provider = providers[expected == "second"]
    assert provider.get_text.await_count == 1
    assert Path(provider.get_text.await_args.args[0]).parent == directory
    assert list(directory.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["provider", "empty", "timeout", "cancelled", "conversion"]
)
async def test_transcription_failure_cleans_all_files(
    transcription_service, monkeypatch, failure
):
    service, providers, directory = transcription_service
    if failure == "conversion":

        async def failed_convert(source, destination, **kwargs):
            Path(destination).write_bytes(b"partial")
            raise RuntimeError("invalid media")

        monkeypatch.setattr(chat_service, "convert_audio_to_wav", failed_convert)
    elif failure == "empty":
        providers[0].get_text.return_value = " "
    else:
        providers[0].get_text.side_effect = {
            "provider": RuntimeError("provider error"),
            "timeout": asyncio.TimeoutError(),
            "cancelled": asyncio.CancelledError(),
        }[failure]
    upload = UploadFile(
        BytesIO(b"recording"), headers=Headers({"content-type": "audio/ogg"})
    )
    with pytest.raises(
        asyncio.CancelledError if failure == "cancelled" else ChatServiceError
    ):
        await service.transcribe_audio(upload)
    assert list(directory.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["unknown-provider", "no-providers", "empty", "not-audio", "oversized"]
)
async def test_transcription_rejects_invalid_input(transcription_service, case):
    service, providers, directory = transcription_service
    if case == "no-providers":
        service.core_lifecycle.provider_manager.stt_provider_insts = []
    body = b"" if case == "empty" else b"recording"
    if case == "oversized":
        body = b"a" * (25 * 1024 * 1024 + 1)
    upload = UploadFile(
        BytesIO(body),
        headers=Headers(
            {"content-type": "text/plain" if case == "not-audio" else "audio/webm"}
        ),
    )
    with pytest.raises(ChatServiceError):
        await service.transcribe_audio(
            upload, "unknown" if case == "unknown-provider" else ""
        )
    for provider in providers:
        provider.get_text.assert_not_awaited()
    assert list(directory.iterdir()) == []
