import ntpath
import posixpath
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


class _FakeZipArchive:
    def __init__(self, names: list[str]):
        self._names = names

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def namelist(self) -> list[str]:
        return self._names

    def extractall(self, target_dir: str) -> None:  # noqa: ARG002
        return None


def _build_fake_archive_entries(archive_root: str) -> list[str]:
    return [archive_root, posixpath.join(archive_root, ".dockerignore")]


def _build_fake_archive_entries_with_first_file(root_dir: str) -> list[str]:
    return [f"{root_dir}/README.md", f"{root_dir}/src/app.py"]


def _exercise_unzip_file_windows_path_normalization(
    monkeypatch: pytest.MonkeyPatch,
    *,
    updater_module,
    zip_updator_module,
    updater,
    target_dir: str,
    archive_root: str,
    logger_method: str,
) -> dict[str, object | None]:
    captured: dict[str, object | None] = {
        "listdir": None,
        "move": None,
        "cleanup": None,
        "removed": None,
    }

    def fake_listdir(path: str) -> list[str]:
        captured["listdir"] = path
        return [".dockerignore"]

    monkeypatch.setattr(updater_module.os, "makedirs", lambda path, exist_ok=True: None)
    monkeypatch.setattr(updater_module.os.path, "join", ntpath.join)
    monkeypatch.setattr(updater_module.os.path, "normpath", ntpath.normpath)
    monkeypatch.setattr(updater_module.os.path, "commonpath", ntpath.commonpath)
    monkeypatch.setattr(updater_module.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(updater_module.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        updater_module.zipfile,
        "ZipFile",
        lambda path, mode: _FakeZipArchive(_build_fake_archive_entries(archive_root)),
    )
    monkeypatch.setattr(updater_module.logger, logger_method, lambda message: None)
    monkeypatch.setattr(updater_module.logger, "warning", lambda message: None)
    monkeypatch.setattr(updater_module.os, "listdir", fake_listdir)
    monkeypatch.setattr(
        zip_updator_module.shutil,
        "move",
        lambda src, dst: captured.__setitem__("move", (src, dst)),
    )
    monkeypatch.setattr(
        zip_updator_module.shutil,
        "rmtree",
        lambda path, onerror=None: captured.__setitem__("cleanup", path),
    )
    monkeypatch.setattr(
        updater_module.os,
        "remove",
        lambda path: captured.__setitem__("removed", path),
    )

    updater.unzip_file("temp.zip", target_dir)

    return captured


def _assert_unzip_file_windows_path_normalization(
    captured: dict[str, object | None],
    *,
    target_dir: str,
    archive_root: str,
) -> None:
    normalized_root = ntpath.normpath(archive_root)
    expected_root = (
        target_dir
        if normalized_root == "."
        else ntpath.join(target_dir, normalized_root)
    )
    expected_file = ntpath.join(expected_root, ".dockerignore")

    assert captured["removed"] == "temp.zip"
    if normalized_root == ".":
        assert captured["listdir"] is None
        assert captured["move"] is None
        assert captured["cleanup"] is None
        return

    assert captured["listdir"] == expected_root
    assert captured["move"] == (expected_file, target_dir)
    assert captured["cleanup"] == expected_root


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


@pytest.mark.parametrize(
    "archive_root",
    [
        "AstrBotDevs-AstrBot-39386ee/",
        "AstrBotDevs-AstrBot-39386ee",
        "owner-repo-branch/subdir/",
        ".",
    ],
)
def test_repo_unzip_file_normalizes_windows_extended_length_paths(
    monkeypatch: pytest.MonkeyPatch,
    archive_root: str,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    target_dir = r"\\?\C:\Users\admin\AppData\Local\AstrBot\backend\app"
    captured = _exercise_unzip_file_windows_path_normalization(
        monkeypatch,
        updater_module=zip_updator_module,
        zip_updator_module=zip_updator_module,
        updater=RepoZipUpdator(),
        target_dir=target_dir,
        archive_root=archive_root,
        logger_method="debug",
    )

    _assert_unzip_file_windows_path_normalization(
        captured, target_dir=target_dir, archive_root=archive_root
    )


@pytest.mark.parametrize(
    "archive_root",
    [
        "AstrBotDevs-demo-39386ee/",
        "AstrBotDevs-demo-39386ee",
        "owner-repo-branch/subdir/",
        ".",
    ],
)
def test_plugin_unzip_file_normalizes_windows_extended_length_paths(
    monkeypatch: pytest.MonkeyPatch,
    archive_root: str,
) -> None:
    import astrbot.core.star.updator as plugin_updator_module
    import astrbot.core.zip_updator as zip_updator_module

    target_dir = r"\\?\C:\Users\admin\AppData\Local\AstrBot\data\plugins\demo"
    captured = _exercise_unzip_file_windows_path_normalization(
        monkeypatch,
        updater_module=plugin_updator_module,
        zip_updator_module=zip_updator_module,
        updater=PluginUpdator.__new__(PluginUpdator),
        target_dir=target_dir,
        archive_root=archive_root,
        logger_method="info",
    )

    _assert_unzip_file_windows_path_normalization(
        captured, target_dir=target_dir, archive_root=archive_root
    )


@pytest.mark.parametrize(
    ("archive_root", "expected_error"),
    [
        ("../escape/", "path escapes root directory"),
        ("C:/escape", "path escapes root directory"),
    ],
)
def test_repo_unzip_file_rejects_archive_roots_outside_target_dir(
    monkeypatch: pytest.MonkeyPatch,
    archive_root: str,
    expected_error: str,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    monkeypatch.setattr(
        zip_updator_module.os, "makedirs", lambda path, exist_ok=True: None
    )
    monkeypatch.setattr(zip_updator_module.os.path, "join", ntpath.join)
    monkeypatch.setattr(zip_updator_module.os.path, "normpath", ntpath.normpath)
    monkeypatch.setattr(zip_updator_module.os.path, "commonpath", ntpath.commonpath)
    monkeypatch.setattr(
        zip_updator_module.zipfile,
        "ZipFile",
        lambda path, mode: _FakeZipArchive(_build_fake_archive_entries(archive_root)),
    )

    with pytest.raises(ValueError, match=expected_error):
        RepoZipUpdator().unzip_file("temp.zip", r"\\?\C:\Users\admin\target")


def test_repo_unzip_file_handles_archives_without_explicit_root_dir_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    target_dir = r"\\?\C:\Users\admin\AppData\Local\AstrBot\backend\app"
    archive_root = "repo-root"
    expected_root = ntpath.join(target_dir, archive_root)
    expected_file = ntpath.join(expected_root, "README.md")
    captured: dict[str, object | None] = {
        "listdir": None,
        "move": None,
        "cleanup": None,
        "removed": None,
    }

    def fake_listdir(path: str) -> list[str]:
        captured["listdir"] = path
        return ["README.md"]

    monkeypatch.setattr(
        zip_updator_module.os, "makedirs", lambda path, exist_ok=True: None
    )
    monkeypatch.setattr(zip_updator_module.os.path, "join", ntpath.join)
    monkeypatch.setattr(zip_updator_module.os.path, "normpath", ntpath.normpath)
    monkeypatch.setattr(zip_updator_module.os.path, "commonpath", ntpath.commonpath)
    monkeypatch.setattr(zip_updator_module.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(zip_updator_module.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        zip_updator_module.zipfile,
        "ZipFile",
        lambda path, mode: _FakeZipArchive(
            _build_fake_archive_entries_with_first_file(archive_root)
        ),
    )
    monkeypatch.setattr(zip_updator_module.logger, "debug", lambda message: None)
    monkeypatch.setattr(zip_updator_module.logger, "warning", lambda message: None)
    monkeypatch.setattr(zip_updator_module.os, "listdir", fake_listdir)
    monkeypatch.setattr(
        zip_updator_module.shutil,
        "move",
        lambda src, dst: captured.__setitem__("move", (src, dst)),
    )
    monkeypatch.setattr(
        zip_updator_module.shutil,
        "rmtree",
        lambda path, onerror=None: captured.__setitem__("cleanup", path),
    )
    monkeypatch.setattr(
        zip_updator_module.os,
        "remove",
        lambda path: captured.__setitem__("removed", path),
    )

    RepoZipUpdator().unzip_file("temp.zip", target_dir)

    assert captured["listdir"] == expected_root
    assert captured["move"] == (expected_file, target_dir)
    assert captured["cleanup"] == expected_root
    assert captured["removed"] == "temp.zip"
