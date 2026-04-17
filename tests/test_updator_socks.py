from pathlib import Path
from types import SimpleNamespace

import certifi
import pytest

from astrbot.core.zip_updator import RepoZipUpdator


class _FakeJSONResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self, chunk_size: int = 8192):
        for start in range(0, len(self._payload), chunk_size):
            yield self._payload[start : start + chunk_size]


class _FakeAsyncClient:
    init_kwargs: dict | None = None
    requested_urls: list[str] = []
    stream_urls: list[str] = []
    json_payload = []
    stream_payload = b""

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str):
        type(self).requested_urls.append(url)
        return _FakeJSONResponse(type(self).json_payload)

    def stream(self, method: str, url: str):
        assert method == "GET"
        type(self).stream_urls.append(url)
        return _FakeStreamResponse(type(self).stream_payload)


def _reset_fake_client() -> None:
    _FakeAsyncClient.init_kwargs = None
    _FakeAsyncClient.requested_urls = []
    _FakeAsyncClient.stream_urls = []
    _FakeAsyncClient.json_payload = []
    _FakeAsyncClient.stream_payload = b""


@pytest.mark.asyncio
async def test_fetch_release_info_uses_httpx_client_with_env_proxy_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    _reset_fake_client()
    _FakeAsyncClient.json_payload = [
        {
            "name": "AstrBot v4.23.2",
            "published_at": "2026-04-16T00:00:00Z",
            "body": "fix updater socks proxy support",
            "tag_name": "v4.23.2",
            "zipball_url": "https://example.com/astrbot.zip",
        }
    ]

    monkeypatch.setattr(
        zip_updator_module,
        "aiohttp",
        SimpleNamespace(
            ClientSession=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError(
                    "fetch_release_info should not use aiohttp.ClientSession"
                )
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        zip_updator_module,
        "httpx",
        SimpleNamespace(AsyncClient=_FakeAsyncClient),
        raising=False,
    )

    release_info = await RepoZipUpdator().fetch_release_info(
        "https://api.soulter.top/releases"
    )

    assert release_info == [
        {
            "version": "AstrBot v4.23.2",
            "published_at": "2026-04-16T00:00:00Z",
            "body": "fix updater socks proxy support",
            "tag_name": "v4.23.2",
            "zipball_url": "https://example.com/astrbot.zip",
        }
    ]
    assert _FakeAsyncClient.requested_urls == ["https://api.soulter.top/releases"]
    assert _FakeAsyncClient.init_kwargs is not None
    assert _FakeAsyncClient.init_kwargs["trust_env"] is True
    assert _FakeAsyncClient.init_kwargs["verify"] == certifi.where()


@pytest.mark.asyncio
async def test_download_from_repo_url_uses_httpx_stream_for_zip_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    _reset_fake_client()
    _FakeAsyncClient.stream_payload = b"zip-data"

    async def fake_fetch_release_info(self, url: str, latest: bool = True):  # noqa: ARG001
        return [
            {
                "version": "AstrBot v4.23.2",
                "published_at": "2026-04-16T00:00:00Z",
                "body": "fix updater socks proxy support",
                "tag_name": "v4.23.2",
                "zipball_url": "https://example.com/archive.zip",
            }
        ]

    monkeypatch.setattr(RepoZipUpdator, "fetch_release_info", fake_fetch_release_info)
    monkeypatch.setattr(
        zip_updator_module,
        "download_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("download_from_repo_url should not use aiohttp download_file")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        zip_updator_module,
        "httpx",
        SimpleNamespace(AsyncClient=_FakeAsyncClient),
        raising=False,
    )

    target_path = tmp_path / "AstrBot"
    await RepoZipUpdator().download_from_repo_url(
        str(target_path),
        "https://github.com/AstrBotDevs/AstrBot",
    )

    assert (tmp_path / "AstrBot.zip").read_bytes() == b"zip-data"
    assert _FakeAsyncClient.stream_urls == ["https://example.com/archive.zip"]
    assert _FakeAsyncClient.init_kwargs is not None
    assert _FakeAsyncClient.init_kwargs["trust_env"] is True
    assert _FakeAsyncClient.init_kwargs["verify"] == certifi.where()
