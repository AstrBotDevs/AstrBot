import asyncio
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from astrbot.core.provider.oauth.openai_oauth_shared_state import (
    OpenAIOAuthSharedState,
)
from astrbot.core.provider.oauth.openai_oauth_transcription import (
    OPENAI_TRANSCRIPTIONS_URL,
    OpenAIOAuthTranscriptionClient,
)


class FakeOAuthProvider:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.provider_config = {"proxy": "http://proxy.invalid"}
        self.timeout = 12
        self._responses = responses
        self._version = 3
        self.refresh_calls = 0
        self.requests: list[dict] = []

    async def _ensure_fresh_oauth_token(self) -> None:
        return None

    def _build_backend_headers_with_version(self) -> tuple[dict[str, str], int]:
        return (
            {
                "Authorization": f"Bearer token-{self._version}",
                "chatgpt-account-id": "account-id",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "version": "0.153.4",
            },
            self._version,
        )

    async def _refresh_after_auth_failure(self, attempted_version: int) -> bool:
        self.refresh_calls += 1
        assert attempted_version == self._version
        self._version += 1
        return True


@pytest.mark.asyncio
async def test_close_cancels_active_transcription_and_rejects_new_work(monkeypatch):
    client = OpenAIOAuthTranscriptionClient(FakeOAuthProvider([]))
    entered = asyncio.Event()
    stopped = asyncio.Event()

    async def blocking(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(client, "_transcribe_audio", blocking)
    call = asyncio.create_task(client.transcribe_audio("voice.wav"))
    await entered.wait()
    await client.close()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert stopped.is_set()
    with pytest.raises(RuntimeError, match="closed"):
        await client.transcribe_audio("voice.wav")


class FakeAsyncClient:
    instances: list["FakeAsyncClient"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.provider: FakeOAuthProvider = kwargs.pop("_provider")
        FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url: str, **kwargs) -> httpx.Response:
        self.provider.requests.append({"url": url, **kwargs})
        return self.provider._responses.pop(0)


def _write_wav(path: Path, frames: int = 1) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x00\x00" * frames)


def _install_http_client(monkeypatch, provider: FakeOAuthProvider) -> None:
    FakeAsyncClient.instances.clear()

    def factory(**kwargs):
        kwargs["_provider"] = provider
        return FakeAsyncClient(**kwargs)

    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_transcription.httpx.AsyncClient",
        factory,
    )


@pytest.mark.asyncio
async def test_transcribe_audio_posts_multipart_to_fixed_official_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    audio = tmp_path / "voice.wav"
    _write_wav(audio)
    provider = FakeOAuthProvider([httpx.Response(200, json={"text": "hello"})])
    _install_http_client(monkeypatch, provider)
    client = OpenAIOAuthTranscriptionClient(provider)

    result = await client.transcribe_audio(str(audio), language="zh", prompt="names")

    assert result == "hello"
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request["url"] == OPENAI_TRANSCRIPTIONS_URL
    assert request["data"] == {
        "model": "gpt-4o-transcribe",
        "language": "zh",
        "prompt": "names",
    }
    assert request["files"]["file"][0] == "voice.wav"
    headers = request["headers"]
    assert headers["Authorization"] == "Bearer token-3"
    assert headers["Accept"] == "application/json"
    assert not any(key.lower() == "content-type" for key in headers)
    assert FakeAsyncClient.instances[0].kwargs == {
        "proxy": "http://proxy.invalid",
        "timeout": 12.0,
        "follow_redirects": False,
    }


@pytest.mark.asyncio
async def test_transcribe_audio_refreshes_shared_oauth_once_after_401(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    audio = tmp_path / "voice.wav"
    _write_wav(audio)
    provider = FakeOAuthProvider(
        [
            httpx.Response(401, json={"error": {"message": "expired"}}),
            httpx.Response(200, json={"text": "refreshed"}),
        ]
    )
    _install_http_client(monkeypatch, provider)

    result = await OpenAIOAuthTranscriptionClient(provider).transcribe_audio(str(audio))

    assert result == "refreshed"
    assert provider.refresh_calls == 1
    assert [request["headers"]["Authorization"] for request in provider.requests] == [
        "Bearer token-3",
        "Bearer token-4",
    ]


@pytest.mark.asyncio
async def test_transcribe_audio_does_not_refresh_or_leak_403_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    audio = tmp_path / "voice.wav"
    _write_wav(audio)
    secret = "sensitive-token-value"
    provider = FakeOAuthProvider(
        [httpx.Response(403, json={"error": {"message": secret}})]
    )
    _install_http_client(monkeypatch, provider)

    with pytest.raises(PermissionError) as exc_info:
        await OpenAIOAuthTranscriptionClient(provider).transcribe_audio(str(audio))

    assert "无权使用" in str(exc_info.value)
    assert secret not in str(exc_info.value)
    assert provider.refresh_calls == 0


@pytest.mark.asyncio
async def test_transcribe_audio_reports_quota_without_leaking_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    audio = tmp_path / "voice.wav"
    _write_wav(audio)
    secret = "quota for tenant-sensitive-id"
    provider = FakeOAuthProvider(
        [httpx.Response(429, json={"error": {"message": secret}})]
    )
    _install_http_client(monkeypatch, provider)

    with pytest.raises(RuntimeError) as exc_info:
        await OpenAIOAuthTranscriptionClient(provider).transcribe_audio(str(audio))

    assert "配额" in str(exc_info.value)
    assert secret not in str(exc_info.value)


@pytest.mark.asyncio
async def test_transcribe_audio_rejects_oversized_resolved_file_before_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    audio = tmp_path / "voice.wav"
    _write_wav(audio)
    provider = FakeOAuthProvider([])
    _install_http_client(monkeypatch, provider)
    client = OpenAIOAuthTranscriptionClient(provider, max_audio_bytes=4)

    with pytest.raises(ValueError, match="大小上限"):
        await client.transcribe_audio(str(audio))

    assert provider.requests == []


@pytest.mark.asyncio
async def test_transcribe_audio_timeout_cancels_request_and_cleans_resolved_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resolved = tmp_path / "resolved.wav"
    resolved.write_bytes(b"audio")
    cleaned = False
    request_cancelled = asyncio.Event()

    class FakeResolver:
        def __init__(self, *args, **kwargs) -> None:
            pass

        @asynccontextmanager
        async def as_wav_path(self, **kwargs):
            nonlocal cleaned
            try:
                yield SimpleNamespace(
                    path=resolved, mime_type="audio/wav", format="wav"
                )
            finally:
                cleaned = True

    class BlockingClient(FakeAsyncClient):
        async def post(self, url: str, **kwargs) -> httpx.Response:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                request_cancelled.set()
                raise

    provider = FakeOAuthProvider([])
    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_transcription.BoundedOAuthAudioResolver",
        FakeResolver,
    )

    def factory(**kwargs):
        kwargs["_provider"] = provider
        return BlockingClient(**kwargs)

    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_transcription.httpx.AsyncClient",
        factory,
    )
    client = OpenAIOAuthTranscriptionClient(provider, timeout=0.01)

    with pytest.raises(TimeoutError, match="超时"):
        await client.transcribe_audio("input")

    assert request_cancelled.is_set()
    assert cleaned is True


def test_stt_adapter_injects_the_same_oauth_shared_state(monkeypatch):
    from astrbot.core.provider.sources import openai_oauth_stt_source as source

    shared_state = OpenAIOAuthSharedState(
        "source",
        {
            "oauth_access_token": "token",
            "oauth_account_id": "account",
        },
    )
    captured: dict = {}

    class FakeChatProvider:
        def __init__(self, provider_config: dict, provider_settings: dict) -> None:
            captured.update(provider_config)
            self.provider_config = provider_config
            self.timeout = 10

        async def terminate(self) -> None:
            return None

    monkeypatch.setattr(source, "ProviderOpenAIOAuth", FakeChatProvider)
    provider = source.ProviderOpenAIOAuthSTT(
        {
            "id": "stt",
            "type": "openai_oauth_stt",
            "model": "gpt-4o-transcribe",
            "oauth_shared_state": shared_state,
        },
        {},
    )

    assert captured["oauth_shared_state"] is shared_state
    assert captured["type"] == "openai_oauth_chat_completion"
    assert provider.get_model() == "gpt-4o-transcribe"


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_and_cleans_resolved_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resolved = tmp_path / "resolved.wav"
    resolved.write_bytes(b"audio")
    cleaned = False
    request_started = asyncio.Event()

    class FakeResolver:
        def __init__(self, *args, **kwargs) -> None:
            pass

        @asynccontextmanager
        async def as_wav_path(self, **kwargs):
            nonlocal cleaned
            try:
                yield SimpleNamespace(
                    path=resolved, mime_type="audio/wav", format="wav"
                )
            finally:
                cleaned = True

    class BlockingClient(FakeAsyncClient):
        async def post(self, url: str, **kwargs) -> httpx.Response:
            request_started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    provider = FakeOAuthProvider([])
    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_transcription.BoundedOAuthAudioResolver",
        FakeResolver,
    )

    def factory(**kwargs):
        kwargs["_provider"] = provider
        return BlockingClient(**kwargs)

    monkeypatch.setattr(
        "astrbot.core.provider.oauth.openai_oauth_transcription.httpx.AsyncClient",
        factory,
    )
    client = OpenAIOAuthTranscriptionClient(provider, timeout=10)

    task = asyncio.create_task(client.transcribe_audio("input"))
    await request_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cleaned is True
