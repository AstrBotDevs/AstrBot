from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import certifi
import httpx
import pytest

from astrbot.core.star.updator import PluginUpdator
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


class _FakeFailingStreamResponse:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self, chunk_size: int = 8192):  # noqa: ARG002
        yield b"partial"
        raise RuntimeError("stream interrupted")


class _FakeStatusErrorResponse:
    def __init__(self, status_code: int, body: str, url: str):
        self._status_code = status_code
        self._body = body
        self._url = url

    def raise_for_status(self) -> None:
        request = httpx.Request("GET", self._url)
        response = httpx.Response(
            self._status_code,
            text=self._body,
            request=request,
        )
        raise httpx.HTTPStatusError(
            "status error",
            request=request,
            response=response,
        )


@dataclass
class _FakeAsyncClientState:
    json_payload: list[dict] = field(default_factory=list)
    stream_payload: bytes = b""
    init_kwargs: dict | None = None
    requested_urls: list[str] = field(default_factory=list)
    stream_urls: list[str] = field(default_factory=list)


class _FakeStatusErrorAsyncClient:
    def __init__(self, response: _FakeStatusErrorResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str):
        return self._response


class _FakeFailingStreamAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def stream(self, method: str, url: str):  # noqa: ARG002
        return _FakeFailingStreamResponse()


def _build_fake_httpx_module(state: _FakeAsyncClientState) -> SimpleNamespace:
    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            state.init_kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str):
            state.requested_urls.append(url)
            return _FakeJSONResponse(state.json_payload)

        def stream(self, method: str, url: str):
            assert method == "GET"
            state.stream_urls.append(url)
            return _FakeStreamResponse(state.stream_payload)

    return SimpleNamespace(
        AsyncClient=_FakeAsyncClient,
        HTTPStatusError=httpx.HTTPStatusError,
    )


@pytest.fixture
def fake_async_client_state() -> _FakeAsyncClientState:
    return _FakeAsyncClientState()


@pytest.mark.asyncio
async def test_plugin_updator_install_prefers_download_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = {}
    updator = PluginUpdator()
    updator.plugin_store_path = str(tmp_path)

    async def fake_download_file(url: str, path: str, timeout: float = 1800.0):  # noqa: ARG001
        calls["download"] = (url, path)
        Path(path).write_bytes(b"zip-data")

    async def fail_download_from_repo_url(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("install should use download_url instead of GitHub")

    def fake_unzip_file(zip_path: str, target_dir: str):
        calls["unzip"] = (zip_path, target_dir)

    monkeypatch.setattr(updator, "_download_file", fake_download_file)
    monkeypatch.setattr(updator, "download_from_repo_url", fail_download_from_repo_url)
    monkeypatch.setattr(updator, "unzip_file", fake_unzip_file)

    plugin_path = await updator.install(
        "https://github.com/Owner/plugin-name",
        proxy="https://gh-proxy.example",
        download_url="https://cdn.example/plugin.zip",
    )

    expected_path = tmp_path / "plugin_name"
    assert plugin_path == str(expected_path)
    assert calls["download"] == (
        "https://cdn.example/plugin.zip",
        str(expected_path) + ".zip",
    )
    assert calls["unzip"] == (str(expected_path) + ".zip", str(expected_path))


@pytest.mark.asyncio
async def test_fetch_release_info_uses_httpx_client_with_env_proxy_support(
    monkeypatch: pytest.MonkeyPatch,
    fake_async_client_state: _FakeAsyncClientState,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    fake_async_client_state.json_payload = [
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
        _build_fake_httpx_module(fake_async_client_state),
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
    assert fake_async_client_state.requested_urls == [
        "https://api.soulter.top/releases"
    ]
    assert fake_async_client_state.init_kwargs is not None
    assert fake_async_client_state.init_kwargs["follow_redirects"] is True
    assert fake_async_client_state.init_kwargs["timeout"] == 30.0
    assert fake_async_client_state.init_kwargs["trust_env"] is True
    assert fake_async_client_state.init_kwargs["verify"] == certifi.where()


@pytest.mark.asyncio
async def test_download_from_repo_url_uses_httpx_stream_for_zip_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_async_client_state: _FakeAsyncClientState,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    fake_async_client_state.stream_payload = b"zip-data"

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
            AssertionError(
                "download_from_repo_url should not use aiohttp download_file"
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        zip_updator_module,
        "httpx",
        _build_fake_httpx_module(fake_async_client_state),
        raising=False,
    )

    target_path = tmp_path / "AstrBot"
    await RepoZipUpdator().download_from_repo_url(
        str(target_path),
        "https://github.com/AstrBotDevs/AstrBot",
    )

    assert (tmp_path / "AstrBot.zip").read_bytes() == b"zip-data"
    assert fake_async_client_state.stream_urls == ["https://example.com/archive.zip"]
    assert fake_async_client_state.init_kwargs is not None
    assert fake_async_client_state.init_kwargs["follow_redirects"] is True
    assert fake_async_client_state.init_kwargs["timeout"] == 1800.0
    assert fake_async_client_state.init_kwargs["trust_env"] is True
    assert fake_async_client_state.init_kwargs["verify"] == certifi.where()


def test_create_httpx_client_uses_custom_verify_setting(
    monkeypatch: pytest.MonkeyPatch,
    fake_async_client_state: _FakeAsyncClientState,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    custom_verify = "/tmp/custom-ca.pem"

    monkeypatch.setattr(
        zip_updator_module,
        "httpx",
        _build_fake_httpx_module(fake_async_client_state),
        raising=False,
    )

    RepoZipUpdator(verify=custom_verify)._create_httpx_client(timeout=45.0)

    assert fake_async_client_state.init_kwargs is not None
    assert fake_async_client_state.init_kwargs["follow_redirects"] is True
    assert fake_async_client_state.init_kwargs["timeout"] == 45.0
    assert fake_async_client_state.init_kwargs["trust_env"] is True
    assert fake_async_client_state.init_kwargs["verify"] == custom_verify


@pytest.mark.asyncio
async def test_fetch_release_info_logs_status_code_and_truncated_body_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    url = "https://api.soulter.top/releases"
    body = "x" * 1005
    log_messages: list[str] = []

    monkeypatch.setattr(
        RepoZipUpdator,
        "_create_httpx_client",
        staticmethod(
            lambda timeout=30.0: _FakeStatusErrorAsyncClient(  # noqa: ARG005
                _FakeStatusErrorResponse(502, body, url)
            )
        ),
    )
    monkeypatch.setattr(
        zip_updator_module.logger,
        "error",
        lambda message: log_messages.append(message),
    )

    with pytest.raises(Exception, match="解析版本信息失败"):
        await RepoZipUpdator().fetch_release_info(url)

    assert any("状态码: 502" in message for message in log_messages)
    assert any("内容: " in message for message in log_messages)
    assert any("...[truncated]" in message for message in log_messages)


@pytest.mark.asyncio
async def test_download_file_removes_partial_file_when_stream_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        RepoZipUpdator,
        "_create_httpx_client",
        staticmethod(
            lambda timeout=30.0: _FakeFailingStreamAsyncClient()  # noqa: ARG005
        ),
    )

    target_path = tmp_path / "partial.zip"

    with pytest.raises(RuntimeError, match="stream interrupted"):
        await RepoZipUpdator()._download_file(
            "https://example.com/archive.zip",
            str(target_path),
        )

    assert not target_path.exists()


@pytest.mark.asyncio
async def test_download_file_logs_url_and_target_path_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    url = "https://example.com/archive.zip"
    target_path = tmp_path / "logged-partial.zip"
    log_messages: list[str] = []

    monkeypatch.setattr(
        RepoZipUpdator,
        "_create_httpx_client",
        staticmethod(
            lambda timeout=30.0: _FakeFailingStreamAsyncClient()  # noqa: ARG005
        ),
    )
    monkeypatch.setattr(
        zip_updator_module.logger,
        "error",
        lambda message: log_messages.append(message),
    )

    with pytest.raises(RuntimeError, match="stream interrupted"):
        await RepoZipUpdator()._download_file(url, str(target_path))

    assert any(url in message for message in log_messages)
    assert any(str(target_path) in message for message in log_messages)
