import asyncio
import base64

import httpx
import pytest

from astrbot.core.provider.sources import stepfun_asr_source


def test_parse_sse_transcription_handles_crlf_and_non_object_payloads():
    content = (
        'data: ["unexpected"]\r\n\r\n'
        'data: {"type":"transcription.delta","text":"ignored"}\r\n\r\n'
        'data: {"type":"transcription.done","text":"final text"}\r\n\r\n'
        "data: [DONE]\r\n\r\n"
    )

    assert stepfun_asr_source.parse_sse_transcription(content) == "final text"


@pytest.mark.asyncio
async def test_prepare_audio_input_reads_local_wav_without_cleanup(tmp_path):
    audio_path = tmp_path / "sample.wav"
    audio_bytes = b"RIFF\x00\x00\x00\x00WAVEpayload"
    audio_path.write_bytes(audio_bytes)

    encoded, audio_format, cleanup_paths = await stepfun_asr_source.prepare_audio_input(
        str(audio_path)
    )

    assert base64.b64decode(encoded) == audio_bytes
    assert audio_format == {"type": "wav"}
    assert cleanup_paths == []
    assert audio_path.exists()


@pytest.mark.asyncio
async def test_prepare_audio_input_cleans_partial_download_after_failure(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(stepfun_asr_source, "get_temp_dir", lambda: tmp_path)

    async def failing_download(url, destination):
        assert url == "https://example.test/audio.wav"
        with open(destination, "wb") as file:
            file.write(b"partial")
        raise RuntimeError("download failed")

    monkeypatch.setattr(stepfun_asr_source, "download_file", failing_download)

    with pytest.raises(RuntimeError, match="download failed"):
        await stepfun_asr_source.prepare_audio_input(
            "https://example.test/audio.wav"
        )

    assert list(tmp_path.glob("stepfun_asr_*")) == []


@pytest.mark.asyncio
async def test_prepare_audio_input_cleans_partial_download_after_cancellation(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(stepfun_asr_source, "get_temp_dir", lambda: tmp_path)

    async def cancelled_download(url, destination):
        assert url == "https://example.test/audio.wav"
        with open(destination, "wb") as file:
            file.write(b"partial")
        raise asyncio.CancelledError

    monkeypatch.setattr(stepfun_asr_source, "download_file", cancelled_download)

    with pytest.raises(asyncio.CancelledError):
        await stepfun_asr_source.prepare_audio_input(
            "https://example.test/audio.wav"
        )

    assert list(tmp_path.glob("stepfun_asr_*")) == []


@pytest.mark.asyncio
async def test_get_text_cleans_temporary_files_after_http_error(
    monkeypatch,
    tmp_path,
):
    cleanup_path = tmp_path / "downloaded.wav"
    cleanup_path.write_bytes(b"temporary")

    class FakeClient:
        async def post(self, *args, **kwargs):
            return httpx.Response(
                500,
                text="upstream failed",
                request=httpx.Request("POST", "https://api.stepfun.com"),
            )

        async def aclose(self):
            return None

    fake_client = FakeClient()
    monkeypatch.setattr(
        stepfun_asr_source,
        "create_http_client",
        lambda timeout, proxy: fake_client,
    )
    provider = stepfun_asr_source.ProviderStepFunASR(
        {
            "id": "stepfun-test",
            "type": "stepfun_asr",
            "api_key": "test-key",
        },
        {},
    )

    async def fake_prepare_audio_input(audio_source):
        assert audio_source == "https://example.test/audio.wav"
        return "encoded", {"type": "wav"}, [cleanup_path]

    monkeypatch.setattr(provider, "prepare_audio_input", fake_prepare_audio_input)

    with pytest.raises(stepfun_asr_source.StepFunASRError, match="HTTP 500"):
        await provider.get_text("https://example.test/audio.wav")

    assert not cleanup_path.exists()
