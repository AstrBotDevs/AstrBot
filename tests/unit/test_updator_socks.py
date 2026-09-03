import ntpath
import posixpath
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from astrbot.core import process_reboot as process_reboot_module
from astrbot.core.process_reboot import ProcessRebooter
from astrbot.core.star.updator import PluginUpdator
from astrbot.core.utils.outbound_http import PLUGIN_REPOSITORY
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


def test_process_rebooter_exec_reboot_spawns_new_console_on_windows(
    monkeypatch: pytest.MonkeyPatch,
):
    popen_calls = []
    exit_codes = []
    execv_calls = []

    def fake_popen(args, creationflags=0):
        popen_calls.append((args, creationflags))
        return SimpleNamespace(pid=1234)

    def fake_exit(code):
        exit_codes.append(code)
        raise SystemExit(code)

    def fake_execv(*args):
        execv_calls.append(args)

    monkeypatch.setattr(process_reboot_module.os, "name", "nt")
    monkeypatch.setattr(process_reboot_module.sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        process_reboot_module.subprocess,
        "CREATE_NEW_CONSOLE",
        0x00000010,
        raising=False,
    )
    monkeypatch.setattr(process_reboot_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(process_reboot_module.os, "_exit", fake_exit)
    monkeypatch.setattr(process_reboot_module.os, "execv", fake_execv)

    with pytest.raises(SystemExit) as exc_info:
        ProcessRebooter._exec_reboot(
            r"C:\Python312\python.exe",
            [
                r"C:\Python312\python.exe",
                "main.py",
                "--webui-dir",
                r"C:\AstrBot WebUI\dist",
            ],
        )

    assert exc_info.value.code == 0
    assert popen_calls == [
        (
            [
                r"C:\Python312\python.exe",
                "main.py",
                "--webui-dir",
                r"C:\AstrBot WebUI\dist",
            ],
            process_reboot_module.subprocess.CREATE_NEW_CONSOLE,
        )
    ]
    assert exit_codes == [0]
    assert execv_calls == []


@dataclass
class _FakeAsyncClientState:
    json_payload: object = field(default_factory=list)
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


class _FakeTimeoutAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str):
        request = httpx.Request("GET", url)
        raise httpx.ReadTimeout("timed out", request=request)


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

    def read(self, name: str) -> bytes:
        if name.endswith("metadata.yaml"):
            return (
                b"name: demo\ndesc: Demo plugin\nversion: 1.0.0\nauthor: AstrBot Team\n"
            )
        return b""

    def extractall(self, target_dir: str) -> None:  # noqa: ARG002
        return None


def _build_fake_archive_entries(archive_root: str) -> list[str]:
    return [
        archive_root,
        posixpath.join(archive_root, ".dockerignore"),
        posixpath.join(archive_root, "metadata.yaml"),
    ]


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
    monkeypatch.setattr(updater_module, "ensure_dir", lambda path: None)
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

    async def fake_download_file(
        url: str,
        path: str,
        timeout_seconds: float = 1800.0,
        **kwargs,
    ):  # noqa: ARG001
        del timeout_seconds, kwargs
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


def _plugin_updator_for_update(tmp_path: Path) -> PluginUpdator:
    updater = PluginUpdator.__new__(PluginUpdator)
    updater.plugin_store_path = str(tmp_path)
    return updater


def _stub_plugin_update_fs(
    monkeypatch: pytest.MonkeyPatch, updater: PluginUpdator
) -> None:
    monkeypatch.setattr(updater, "validate_plugin_archive", lambda _path: None)
    monkeypatch.setattr("astrbot.core.star.updator.remove_dir", lambda _path: None)
    monkeypatch.setattr(updater, "unzip_file", lambda *_args: None)


@pytest.mark.asyncio
async def test_plugin_updator_update_uses_explicit_repo_when_plugin_metadata_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, tuple[str, str, str]] = {}
    updater = _plugin_updator_for_update(tmp_path)
    plugin = SimpleNamespace(
        name="demo_plugin",
        repo="",
        root_dir_name="demo_plugin",
    )

    async def fake_download_from_repo_url(
        plugin_path: str,
        repo_url: str,
        proxy: str = "",
    ) -> None:
        calls["download"] = (plugin_path, repo_url, proxy)

    monkeypatch.setattr(updater, "download_from_repo_url", fake_download_from_repo_url)
    _stub_plugin_update_fs(monkeypatch, updater)

    await updater.update(
        plugin,
        proxy="https://mirror.example",
        repo_url="https://github.com/example/plugin",
    )

    assert plugin.repo == ""
    assert calls["download"] == (
        str(tmp_path / "demo_plugin"),
        "https://github.com/example/plugin",
        "https://mirror.example",
    )


@pytest.mark.asyncio
async def test_plugin_updator_update_prefers_explicit_repo_over_plugin_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, tuple[str, str, str]] = {}
    updater = _plugin_updator_for_update(tmp_path)
    plugin = SimpleNamespace(
        name="demo_plugin",
        repo="https://github.com/local/stale",
        root_dir_name="demo_plugin",
    )

    async def fake_download_from_repo_url(
        plugin_path: str,
        repo_url: str,
        proxy: str = "",
    ) -> None:
        calls["download"] = (plugin_path, repo_url, proxy)

    monkeypatch.setattr(updater, "download_from_repo_url", fake_download_from_repo_url)
    _stub_plugin_update_fs(monkeypatch, updater)

    await updater.update(
        plugin,
        proxy="https://mirror.example",
        repo_url="https://github.com/example/plugin",
    )

    assert plugin.repo == "https://github.com/local/stale"
    assert calls["download"] == (
        str(tmp_path / "demo_plugin"),
        "https://github.com/example/plugin",
        "https://mirror.example",
    )


@pytest.mark.asyncio
async def test_plugin_updator_update_prefers_download_url_over_repo_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, tuple[str, str]] = {}
    updater = _plugin_updator_for_update(tmp_path)
    plugin = SimpleNamespace(
        name="demo_plugin",
        repo="https://github.com/local/stale",
        root_dir_name="demo_plugin",
    )

    async def fake_download_file(
        url: str,
        path: str,
        timeout_seconds: float = 1800.0,
        **kwargs,
    ) -> None:
        del timeout_seconds, kwargs
        calls["download"] = (url, path)

    async def fail_download_from_repo_url(*args, **kwargs):
        del args, kwargs
        raise AssertionError("update should use download_url instead of GitHub")

    monkeypatch.setattr(updater, "_download_file", fake_download_file)
    monkeypatch.setattr(updater, "download_from_repo_url", fail_download_from_repo_url)
    _stub_plugin_update_fs(monkeypatch, updater)

    await updater.update(
        plugin,
        download_url="https://cdn.example/plugin.zip",
        repo_url="https://github.com/example/plugin",
    )

    assert plugin.repo == "https://github.com/local/stale"
    assert calls["download"] == (
        "https://cdn.example/plugin.zip",
        str(tmp_path / "demo_plugin") + ".zip",
    )


@pytest.mark.asyncio
async def test_plugin_updator_update_uses_download_url_without_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, tuple[str, str]] = {}
    updater = _plugin_updator_for_update(tmp_path)
    plugin = SimpleNamespace(
        name="demo_plugin",
        repo="",
        root_dir_name="demo_plugin",
    )

    async def fake_download_file(
        url: str,
        path: str,
        timeout_seconds: float = 1800.0,
        **kwargs,
    ) -> None:
        del timeout_seconds, kwargs
        calls["download"] = (url, path)

    async def fail_download_from_repo_url(*args, **kwargs):
        del args, kwargs
        raise AssertionError("update should use download_url instead of GitHub")

    monkeypatch.setattr(updater, "_download_file", fake_download_file)
    monkeypatch.setattr(updater, "download_from_repo_url", fail_download_from_repo_url)
    _stub_plugin_update_fs(monkeypatch, updater)

    await updater.update(plugin, download_url="https://cdn.example/plugin.zip")

    assert calls["download"] == (
        "https://cdn.example/plugin.zip",
        str(tmp_path / "demo_plugin") + ".zip",
    )


@pytest.mark.asyncio
async def test_plugin_updator_update_uses_plugin_repo_when_repo_url_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: dict[str, tuple[str, str, str]] = {}
    updater = _plugin_updator_for_update(tmp_path)
    plugin = SimpleNamespace(
        name="demo_plugin",
        repo="https://github.com/local/installed",
        root_dir_name="demo_plugin",
    )

    async def fake_download_from_repo_url(
        plugin_path: str,
        repo_url: str,
        proxy: str = "",
    ) -> None:
        calls["download"] = (plugin_path, repo_url, proxy)

    monkeypatch.setattr(updater, "download_from_repo_url", fake_download_from_repo_url)
    _stub_plugin_update_fs(monkeypatch, updater)

    await updater.update(plugin, proxy="https://mirror.example")

    assert plugin.repo == "https://github.com/local/installed"
    assert calls["download"] == (
        str(tmp_path / "demo_plugin"),
        "https://github.com/local/installed",
        "https://mirror.example",
    )


def test_plugin_unzip_file_rejects_metadata_yml(tmp_path: Path) -> None:
    zip_path = tmp_path / "plugin.zip"
    target_dir = tmp_path / "plugin"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "demo-plugin/metadata.yml",
            "\n".join(
                [
                    "name: demo_plugin",
                    "desc: Demo plugin",
                    "version: 1.0.0",
                    "author: AstrBot Team",
                ]
            ),
        )
        archive.writestr("demo-plugin/main.py", "VALUE = 1\n")

    updater = PluginUpdator.__new__(PluginUpdator)
    with pytest.raises(ValueError, match="未找到 metadata.yaml"):
        updater.unzip_file(str(zip_path), str(target_dir))

    assert not target_dir.exists()


def test_plugin_unzip_file_rejects_archive_without_metadata(tmp_path: Path) -> None:
    zip_path = tmp_path / "plugin.zip"
    target_dir = tmp_path / "plugin"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("demo-plugin/main.py", "VALUE = 1\n")

    updater = PluginUpdator.__new__(PluginUpdator)
    with pytest.raises(ValueError, match="未找到 metadata.yaml"):
        updater.unzip_file(str(zip_path), str(target_dir))

    assert not target_dir.exists()


def test_plugin_unzip_file_rejects_path_traversal(tmp_path: Path) -> None:
    zip_path = tmp_path / "plugin.zip"
    target_dir = tmp_path / "plugin"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "demo-plugin/metadata.yaml",
            "\n".join(
                [
                    "name: demo_plugin",
                    "desc: Demo plugin",
                    "version: 1.0.0",
                    "author: AstrBot Team",
                ]
            ),
        )
        archive.writestr("../escape.txt", "escape")

    updater = PluginUpdator.__new__(PluginUpdator)
    updater.validate_plugin_archive = lambda _zip_path: "demo-plugin/metadata.yaml"
    with pytest.raises(ValueError, match="Unsafe plugin archive path"):
        updater.unzip_file(str(zip_path), str(target_dir))

    assert not (tmp_path / "escape.txt").exists()


def test_plugin_validate_archive_rejects_incomplete_metadata(tmp_path: Path) -> None:
    zip_path = tmp_path / "plugin.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "demo-plugin/metadata.yaml",
            "\n".join(
                [
                    "name: demo_plugin",
                    "desc: Demo plugin",
                    "author: AstrBot Team",
                ]
            ),
        )
        archive.writestr("demo-plugin/main.py", "VALUE = 1\n")

    with pytest.raises(ValueError, match="version"):
        PluginUpdator.validate_plugin_archive(str(zip_path))


def test_plugin_validate_archive_rejects_empty_metadata_fields(
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "plugin.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "demo-plugin/metadata.yaml",
            "\n".join(
                [
                    "name: demo_plugin",
                    "desc: Demo plugin",
                    "version: ''",
                    "author: AstrBot Team",
                ]
            ),
        )
        archive.writestr("demo-plugin/main.py", "VALUE = 1\n")

    with pytest.raises(ValueError, match="version.*非空字符串"):
        PluginUpdator.validate_plugin_archive(str(zip_path))


@pytest.mark.asyncio
async def test_plugin_update_validates_archive_before_removing_existing_plugin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = PluginUpdator.__new__(PluginUpdator)
    updater.plugin_store_path = str(tmp_path)
    plugin_dir = tmp_path / "demo_plugin"
    plugin_dir.mkdir()
    marker_path = plugin_dir / "main.py"
    marker_path.write_text("VALUE = 'old'\n", encoding="utf-8")
    plugin = SimpleNamespace(
        name="demo_plugin",
        repo="https://github.com/Owner/demo-plugin",
        root_dir_name="demo_plugin",
    )

    async def fake_download_from_repo_url(
        plugin_path: str,
        repo_url: str,
        proxy: str = "",
    ) -> None:
        del repo_url, proxy
        with zipfile.ZipFile(plugin_path + ".zip", "w") as archive:
            archive.writestr("demo-plugin/main.py", "VALUE = 'new'\n")

    monkeypatch.setattr(
        updater,
        "download_from_repo_url",
        fake_download_from_repo_url,
    )

    with pytest.raises(ValueError, match="未找到 metadata.yaml"):
        await updater.update(plugin)

    assert marker_path.read_text(encoding="utf-8") == "VALUE = 'old'\n"


@pytest.mark.asyncio
async def test_fetch_release_info_uses_outbound_json_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    async def fake_fetch_json(url, policy, **kwargs):
        del policy, kwargs
        assert url == "https://api.soulter.top/releases"
        return [
            {
                "name": "AstrBot v4.23.2",
                "published_at": "2026-04-16T00:00:00Z",
                "body": "fix updater socks proxy support",
                "tag_name": "v4.23.2",
                "zipball_url": "https://example.com/astrbot.zip",
            }
        ]

    monkeypatch.setattr(zip_updator_module, "fetch_json", fake_fetch_json)
    release_info = await RepoZipUpdator().fetch_release_info(
        "https://api.soulter.top/releases"
    )
    assert release_info[0]["tag_name"] == "v4.23.2"


@pytest.mark.asyncio
async def test_download_from_repo_url_uses_outbound_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    async def fake_fetch_json(url, policy, **kwargs):
        del policy, kwargs
        assert "api.github.com" in url
        return {"default_branch": "trunk"}

    async def fake_download_to_path(url, path, policy, **kwargs):
        del policy, kwargs
        assert url.endswith("trunk.zip")
        Path(path).write_bytes(b"zip-data")

    monkeypatch.setattr(zip_updator_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(zip_updator_module, "download_to_path", fake_download_to_path)
    target_path = tmp_path / "AstrBot"
    await RepoZipUpdator().download_from_repo_url(
        str(target_path),
        "https://github.com/AstrBotDevs/AstrBot",
    )
    assert (tmp_path / "AstrBot.zip").read_bytes() == b"zip-data"


@pytest.mark.asyncio
async def test_download_from_repo_url_uses_explicit_branch_without_default_branch_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updator = RepoZipUpdator()
    calls: list[str] = []

    async def fail_fetch_github_default_branch(author: str, repo: str):  # noqa: ARG001
        raise AssertionError("explicit branch should not fetch GitHub default branch")

    async def fake_download_file(url: str, path: str, **kwargs):
        calls.append(url)
        Path(path).write_bytes(b"zip-data")

    monkeypatch.setattr(
        updator,
        "fetch_github_default_branch",
        fail_fetch_github_default_branch,
    )
    monkeypatch.setattr(updator, "_download_file", fake_download_file)
    monkeypatch.setattr(
        "astrbot.core.zip_updator.validate_github_mirror_origin",
        lambda mirror, **kwargs: SimpleNamespace(
            url=mirror.rstrip("/"),
            hostname="proxy.example",
        ),
    )
    monkeypatch.setattr(
        "astrbot.core.zip_updator.compose_github_mirror_url",
        lambda mirror, github_url, **kwargs: f"{mirror.rstrip('/')}/{github_url}",
    )
    monkeypatch.setattr(
        "astrbot.core.zip_updator.policy_for_github_mirror_download",
        lambda host: PLUGIN_REPOSITORY,
    )

    await updator.download_from_repo_url(
        str(tmp_path / "AstrBot"),
        "https://github.com/AstrBotDevs/AstrBot/tree/dev",
        proxy="https://proxy.example/",
    )

    assert calls == [
        "https://proxy.example/https://github.com/AstrBotDevs/AstrBot/archive/refs/heads/dev.zip"
    ]


def test_repo_zip_updator_keeps_verify_setting() -> None:
    assert (
        RepoZipUpdator(verify="/tmp/custom-ca.pem").httpx_verify == "/tmp/custom-ca.pem"
    )


@pytest.mark.asyncio
async def test_fetch_release_info_logs_status_code_and_truncated_body_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    url = "https://api.soulter.top/releases"
    log_messages: list[str] = []

    async def fake_fetch_json(*args, **kwargs):
        del args, kwargs
        raise zip_updator_module.OutboundRequestError("Download failed with HTTP 502")

    monkeypatch.setattr(zip_updator_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(
        zip_updator_module.logger,
        "error",
        lambda *args, **kwargs: log_messages.append(str(args)),
    )

    with pytest.raises(Exception, match="解析版本信息失败"):
        await RepoZipUpdator().fetch_release_info(url)

    assert log_messages


@pytest.mark.asyncio
async def test_fetch_release_info_reports_timeout_clearly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    url = "https://api.soulter.top/releases"
    log_messages: list[str] = []

    async def fake_fetch_json(*args, **kwargs):
        del args, kwargs
        raise zip_updator_module.OutboundRequestError("timeout")

    monkeypatch.setattr(zip_updator_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(
        zip_updator_module.logger,
        "error",
        lambda *args, **kwargs: log_messages.append(str(args)),
    )

    with pytest.raises(Exception, match="解析版本信息失败"):
        await RepoZipUpdator().fetch_release_info(url)

    assert log_messages


@pytest.mark.asyncio
async def test_download_file_removes_partial_file_when_stream_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def boom(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("stream interrupted")

    monkeypatch.setattr("astrbot.core.zip_updator.download_to_path", boom)

    target_path = tmp_path / "partial.zip"
    target_path.write_bytes(b"partial")

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

    async def boom(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("stream interrupted")

    monkeypatch.setattr(zip_updator_module, "download_to_path", boom)
    monkeypatch.setattr(
        zip_updator_module.logger,
        "error",
        lambda *args, **kwargs: log_messages.append(
            " ".join(str(item) for item in args)
        ),
    )

    with pytest.raises(RuntimeError, match="stream interrupted"):
        await RepoZipUpdator()._download_file(url, str(target_path))

    assert any("下载文件失败" in message for message in log_messages)
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
    monkeypatch.setattr(zip_updator_module, "ensure_dir", lambda path: None)
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
    monkeypatch.setattr(zip_updator_module, "ensure_dir", lambda path: None)
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


@pytest.mark.asyncio
async def test_check_update_returns_none_when_no_releases_are_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_release_info(url: str):
        del url
        return []

    updator = RepoZipUpdator()
    monkeypatch.setattr(updator, "fetch_release_info", fake_fetch_release_info)
    assert (
        await updator.check_update(
            "https://api.github.com/repos/Xero-Team/AstrBot/releases",
            "v4.27.4",
        )
        is None
    )


@pytest.mark.asyncio
async def test_fetch_release_info_rejects_non_list_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    async def fake_fetch_json(url, policy, **kwargs):
        del url, policy, kwargs
        return {"message": "Not Found"}

    monkeypatch.setattr(zip_updator_module, "fetch_json", fake_fetch_json)
    with pytest.raises(Exception, match="解析版本信息失败"):
        await RepoZipUpdator().fetch_release_info(
            "https://api.github.com/repos/Xero-Team/AstrBot/releases"
        )


@pytest.mark.asyncio
async def test_fetch_release_info_rejects_non_object_array_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updator as zip_updator_module

    async def fake_fetch_json(url, policy, **kwargs):
        del url, policy, kwargs
        return ["v1"]

    monkeypatch.setattr(zip_updator_module, "fetch_json", fake_fetch_json)
    with pytest.raises(Exception, match="解析版本信息失败"):
        await RepoZipUpdator().fetch_release_info(
            "https://api.github.com/repos/Xero-Team/AstrBot/releases"
        )
