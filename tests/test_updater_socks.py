import ntpath
import posixpath
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import certifi
import httpx
import pytest

from astrbot.core import dashboard_assets, process_restart
from astrbot.core import updater as core_updater
from astrbot.core.star.updater import _PluginUpdater
from astrbot.core.updater import AstrBotUpdater, UpdateProgress
from astrbot.core.zip_updater import ReleaseInfo, _RepoZipUpdater


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


def test_process_restart_spawns_new_console_on_windows(
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

    monkeypatch.setattr(process_restart.os, "name", "nt")
    monkeypatch.setattr(process_restart.sys, "frozen", False, raising=False)
    monkeypatch.setattr(
        process_restart.subprocess,
        "CREATE_NEW_CONSOLE",
        0x00000010,
        raising=False,
    )
    monkeypatch.setattr(process_restart.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(process_restart.os, "_exit", fake_exit)
    monkeypatch.setattr(process_restart.os, "execv", fake_execv)

    with pytest.raises(SystemExit) as exc_info:
        process_restart._exec_restart(
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
            process_restart.subprocess.CREATE_NEW_CONSOLE,
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
        if name.endswith(("metadata.yaml", "metadata.yml")):
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
        posixpath.join(archive_root, "metadata.yml"),
    ]


def _build_fake_archive_entries_with_first_file(root_dir: str) -> list[str]:
    return [f"{root_dir}/README.md", f"{root_dir}/src/app.py"]


def _exercise_unzip_file_windows_path_normalization(
    monkeypatch: pytest.MonkeyPatch,
    *,
    updater_module,
    zip_updater_module,
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
        zip_updater_module.shutil,
        "move",
        lambda src, dst: captured.__setitem__("move", (src, dst)),
    )
    monkeypatch.setattr(
        zip_updater_module.shutil,
        "rmtree",
        lambda path, onerror=None: captured.__setitem__("cleanup", path),
    )
    monkeypatch.setattr(
        updater_module.os,
        "remove",
        lambda path: captured.__setitem__("removed", path),
    )

    extract_archive = getattr(
        updater,
        "_extract_plugin_archive",
        updater._extract_archive,
    )
    extract_archive("temp.zip", target_dir)

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
async def test_plugin_updater_install_prefers_download_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = {}
    updater = _PluginUpdater()
    updater.plugin_store_path = str(tmp_path)

    async def fake_download_file(url: str, path: str, timeout: float = 1800.0):  # noqa: ARG001
        calls["download"] = (url, path)
        Path(path).write_bytes(b"zip-data")

    async def fail_download_from_repo_url(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("install should use download_url instead of GitHub")

    def fake_unzip_file(zip_path: str, target_dir: str):
        calls["unzip"] = (zip_path, target_dir)

    monkeypatch.setattr(updater, "_download_file", fake_download_file)
    monkeypatch.setattr(updater, "_download_repository", fail_download_from_repo_url)
    monkeypatch.setattr(updater, "_extract_plugin_archive", fake_unzip_file)

    plugin_path = await updater.install(
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


def test_plugin_unzip_file_accepts_metadata_yml(tmp_path: Path) -> None:
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

    updater = _PluginUpdater.__new__(_PluginUpdater)
    updater._extract_plugin_archive(str(zip_path), str(target_dir))

    assert (target_dir / "metadata.yml").is_file()
    assert (target_dir / "main.py").is_file()
    assert not zip_path.exists()


def test_plugin_unzip_file_rejects_archive_without_metadata(tmp_path: Path) -> None:
    zip_path = tmp_path / "plugin.zip"
    target_dir = tmp_path / "plugin"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("demo-plugin/main.py", "VALUE = 1\n")

    updater = _PluginUpdater.__new__(_PluginUpdater)
    with pytest.raises(ValueError, match="未找到 metadata.yaml 或 metadata.yml"):
        updater._extract_plugin_archive(str(zip_path), str(target_dir))

    assert not target_dir.exists()


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
        _PluginUpdater.validate_plugin_archive(str(zip_path))


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
        _PluginUpdater.validate_plugin_archive(str(zip_path))


@pytest.mark.asyncio
async def test_plugin_update_validates_archive_before_removing_existing_plugin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = _PluginUpdater.__new__(_PluginUpdater)
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
        "_download_repository",
        fake_download_from_repo_url,
    )

    with pytest.raises(ValueError, match="未找到 metadata.yaml 或 metadata.yml"):
        await updater.update(plugin)

    assert marker_path.read_text(encoding="utf-8") == "VALUE = 'old'\n"


@pytest.mark.asyncio
async def test_plugin_update_validates_git_checkout_before_replacing_plugin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = _PluginUpdater.__new__(_PluginUpdater)
    updater.plugin_store_path = str(tmp_path)
    plugin_dir = tmp_path / "demo_plugin"
    plugin_dir.mkdir()
    marker_path = plugin_dir / "main.py"
    marker_path.write_text("VALUE = 'old'\n", encoding="utf-8")
    plugin = SimpleNamespace(
        name="demo_plugin",
        repo="https://github.com/AstrBotDevs/demo-plugin",
        root_dir_name="demo_plugin",
    )

    async def fake_clone_repository(repo_url: str, target_path: Path) -> None:
        assert repo_url == "git@gitlab.com:AstrBotDevs/demo-plugin.git"
        target_path.mkdir(parents=True)
        (target_path / "main.py").write_text("VALUE = 'new'\n", encoding="utf-8")

    monkeypatch.setattr(updater, "_clone_repository", fake_clone_repository)

    with pytest.raises(ValueError, match="metadata.yaml 或 metadata.yml"):
        await updater.update(
            plugin,
            repo_url="git@gitlab.com:AstrBotDevs/demo-plugin.git",
        )

    assert marker_path.read_text(encoding="utf-8") == "VALUE = 'old'\n"


@pytest.mark.asyncio
async def test_astrbot_updater_prepares_both_packages_before_applying(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = AstrBotUpdater()
    calls: list[str] = []
    progress_events: list[UpdateProgress] = []
    fetch_count = 0
    observer_failed = False
    release_data = {
        "tag_name": "v99.0.0",
        "zipball_url": "https://example.com/core.zip",
    }

    async def fake_fetch_release_info(_url: str):
        nonlocal fetch_count
        fetch_count += 1
        return [release_data]

    async def fake_download_dashboard(*, path: str, **kwargs) -> None:
        calls.append("download-dashboard")
        assert kwargs["version"] == "v99.0.0"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("dist/index.html", "dashboard")
        await kwargs["progress_callback"](
            {"downloaded": 10, "total": 10, "percent": 1, "speed": 1}
        )

    async def fake_download_core(*, path: Path, **kwargs) -> Path:
        calls.append("download-core")
        assert kwargs["latest"] is False
        assert kwargs["version"] == "v99.0.0"
        assert kwargs["release_data"] is release_data
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AstrBot-main/README.md", "core")
        await kwargs["progress_callback"](
            {"downloaded": 10, "total": 10, "percent": 1, "speed": 1}
        )
        return path

    def fake_apply_core(_path: Path) -> None:
        calls.append("apply-core")

    def fake_extract_dashboard(_path: Path, _data_path: Path) -> None:
        calls.append("apply-dashboard")

    async def record_progress(event: UpdateProgress) -> None:
        nonlocal observer_failed
        progress_events.append(event)
        if not observer_failed:
            observer_failed = True
            raise RuntimeError("observer failed")

    monkeypatch.setattr(
        core_updater,
        "get_astrbot_temp_path",
        lambda: str(tmp_path / "temp"),
    )
    monkeypatch.setattr(updater, "_fetch_release_info", fake_fetch_release_info)
    monkeypatch.setattr(
        core_updater,
        "get_astrbot_data_path",
        lambda: str(tmp_path / "data"),
    )
    monkeypatch.setattr(
        core_updater,
        "_download_package",
        fake_download_dashboard,
    )
    monkeypatch.setattr(updater, "_download_core_package", fake_download_core)
    monkeypatch.setattr(updater, "_apply_core_package", fake_apply_core)
    monkeypatch.setattr(
        core_updater,
        "_extract_package",
        fake_extract_dashboard,
    )

    await updater.update(progress_callback=record_progress)

    assert calls == [
        "download-dashboard",
        "download-core",
        "apply-core",
        "apply-dashboard",
    ]
    assert fetch_count == 1
    assert observer_failed is True
    assert any(event.stage == "verify" for event in progress_events)
    assert progress_events[-1].stage == "apply"
    assert progress_events[-1].status == "done"


@pytest.mark.asyncio
async def test_astrbot_updater_exposes_release_info_without_download_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = AstrBotUpdater()

    async def fake_fetch_release_info(_url: str):
        return [
            {
                "version": "AstrBot v99.0.0",
                "tag_name": "v99.0.0",
                "published_at": "2026-08-01T00:00:00Z",
                "body": "release notes",
                "zipball_url": "https://example.com/internal.zip",
            }
        ]

    monkeypatch.setattr(updater, "_fetch_release_info", fake_fetch_release_info)

    releases = await updater.get_releases()
    update = await updater.check_update()

    assert len(releases) == 1
    assert isinstance(releases[0], ReleaseInfo)
    assert releases[0].version == "v99.0.0"
    assert releases[0].published_at == "2026-08-01T00:00:00Z"
    assert releases[0].body == "release notes"
    assert update is not None
    assert update.body == "release notes"


@pytest.mark.asyncio
async def test_astrbot_updater_does_not_apply_unverified_packages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = AstrBotUpdater()
    calls: list[str] = []

    async def fake_fetch_release_info(_url: str):
        return [
            {
                "tag_name": "v99.0.0",
                "zipball_url": "https://example.com/core.zip",
            }
        ]

    async def fake_download_dashboard(*, path: str, **_kwargs) -> None:
        calls.append("download-dashboard")
        Path(path).write_bytes(b"not a zip")

    async def fake_download_core(*, path: Path, **_kwargs) -> Path:
        calls.append("download-core")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AstrBot-main/README.md", "core")
        return path

    monkeypatch.setattr(
        core_updater,
        "get_astrbot_temp_path",
        lambda: str(tmp_path / "temp"),
    )
    monkeypatch.setattr(updater, "_fetch_release_info", fake_fetch_release_info)
    monkeypatch.setattr(
        core_updater,
        "_download_package",
        fake_download_dashboard,
    )
    monkeypatch.setattr(updater, "_download_core_package", fake_download_core)
    monkeypatch.setattr(
        updater,
        "_apply_core_package",
        lambda _path: calls.append("apply-core"),
    )
    monkeypatch.setattr(
        core_updater,
        "_extract_package",
        lambda *_args: calls.append("apply-dashboard"),
    )

    with pytest.raises(zipfile.BadZipFile):
        await updater.update(version="v99.0.0")

    assert calls == ["download-dashboard", "download-core"]


@pytest.mark.asyncio
async def test_astrbot_updater_ensure_dashboard_uses_compatible_managed_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = AstrBotUpdater()
    data_dist = tmp_path / "data" / "dist"
    data_dist.mkdir(parents=True)
    bundled_dist = tmp_path / "bundled-dist"

    monkeypatch.setattr(
        core_updater,
        "get_astrbot_data_path",
        lambda: str(tmp_path / "data"),
    )
    monkeypatch.setattr(
        core_updater,
        "_get_bundled_dist_path",
        lambda: bundled_dist,
    )
    monkeypatch.setattr(
        core_updater,
        "_is_dist_compatible",
        lambda path, _version: path == data_dist,
    )

    assert await updater.ensure_dashboard() == data_dist


@pytest.mark.asyncio
async def test_astrbot_updater_ensure_dashboard_downloads_matching_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = AstrBotUpdater()
    data_path = tmp_path / "data"
    data_dist = data_path / "dist"
    calls: list[dict] = []

    async def fake_download_dashboard(**kwargs) -> None:
        calls.append(kwargs)
        data_dist.mkdir(parents=True)
        (data_dist / "index.html").write_text("dashboard", encoding="utf-8")

    monkeypatch.setattr(core_updater, "get_astrbot_data_path", lambda: str(data_path))
    monkeypatch.setattr(
        core_updater,
        "_get_bundled_dist_path",
        lambda: tmp_path / "missing-bundled-dist",
    )
    monkeypatch.setattr(
        core_updater,
        "_is_dist_compatible",
        lambda path, _version: path == data_dist and (path / "index.html").is_file(),
    )
    monkeypatch.setattr(
        core_updater,
        "_should_use_bundled_dist",
        lambda *_args: False,
    )
    monkeypatch.setattr(
        core_updater,
        "_download_package",
        fake_download_dashboard,
    )

    assert await updater.ensure_dashboard() == data_dist
    assert calls == [
        {
            "version": f"v{core_updater.VERSION}",
            "allow_insecure_ssl_fallback": False,
        }
    ]


@pytest.mark.asyncio
async def test_astrbot_updater_ensure_dashboard_keeps_usable_stale_assets_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = AstrBotUpdater()
    data_path = tmp_path / "data"
    data_dist = data_path / "dist"
    data_dist.mkdir(parents=True)
    (data_dist / "index.html").write_text("stale", encoding="utf-8")

    async def fail_download(**_kwargs) -> None:
        raise RuntimeError("unavailable")

    monkeypatch.setattr(core_updater, "get_astrbot_data_path", lambda: str(data_path))
    monkeypatch.setattr(
        core_updater,
        "_get_bundled_dist_path",
        lambda: tmp_path / "missing-bundled-dist",
    )
    monkeypatch.setattr(
        core_updater,
        "_is_dist_compatible",
        lambda *_args: False,
    )
    monkeypatch.setattr(
        core_updater,
        "_should_use_bundled_dist",
        lambda *_args: False,
    )
    monkeypatch.setattr(
        core_updater,
        "_read_dashboard_version",
        lambda _path: "v0.0.1",
    )
    monkeypatch.setattr(
        core_updater,
        "_download_package",
        fail_download,
    )

    assert await updater.ensure_dashboard() == data_dist


@pytest.mark.asyncio
async def test_astrbot_updater_prefers_hosted_core_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ASTRBOT_CLI", raising=False)
    monkeypatch.delenv("ASTRBOT_LAUNCHER", raising=False)
    monkeypatch.setenv("ASTRBOT_CORE_PACKAGE_BASE_URL", "https://cdn.example/core")

    updater = AstrBotUpdater()
    calls: list[str] = []

    async def fake_fetch_release_info(url: str, latest: bool = True):  # noqa: ARG001
        return [
            {
                "version": "AstrBot v99.0.0",
                "published_at": "2026-06-19T00:00:00Z",
                "body": "hosted core package",
                "tag_name": "v99.0.0",
                "zipball_url": "https://github.example/archive.zip",
            }
        ]

    async def fake_download_file(url: str, path: str, progress_callback=None):  # noqa: ARG001
        calls.append(url)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AstrBot-v99.0.0/README.md", "hosted-core")

    monkeypatch.setattr(updater, "_fetch_release_info", fake_fetch_release_info)
    monkeypatch.setattr(updater, "_download_file", fake_download_file)

    zip_path = await updater._download_core_package(
        latest=False,
        version="v99.0.0",
        path=tmp_path / "core.zip",
    )

    assert zip_path == tmp_path / "core.zip"
    assert zipfile.is_zipfile(zip_path)
    assert calls == ["https://cdn.example/core/v99.0.0/source.zip"]


@pytest.mark.asyncio
async def test_astrbot_updater_falls_back_when_hosted_core_package_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ASTRBOT_CLI", raising=False)
    monkeypatch.delenv("ASTRBOT_LAUNCHER", raising=False)
    monkeypatch.setenv("ASTRBOT_CORE_PACKAGE_BASE_URL", "https://cdn.example/core")

    updater = AstrBotUpdater()
    calls: list[str] = []

    async def fake_fetch_release_info(url: str, latest: bool = True):  # noqa: ARG001
        return [
            {
                "version": "AstrBot v99.0.0",
                "published_at": "2026-06-19T00:00:00Z",
                "body": "hosted core package",
                "tag_name": "v99.0.0",
                "zipball_url": "https://github.example/archive.zip",
            }
        ]

    async def fake_download_file(url: str, path: str, progress_callback=None):  # noqa: ARG001
        calls.append(url)
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.hostname == "cdn.example":
            raise RuntimeError("404")
        Path(path).write_bytes(b"github-core")

    monkeypatch.setattr(updater, "_fetch_release_info", fake_fetch_release_info)
    monkeypatch.setattr(updater, "_download_file", fake_download_file)

    zip_path = await updater._download_core_package(
        latest=False,
        version="v99.0.0",
        path=tmp_path / "core.zip",
    )

    assert zip_path == tmp_path / "core.zip"
    assert zip_path.read_bytes() == b"github-core"
    assert calls == [
        "https://cdn.example/core/v99.0.0/source.zip",
        "https://github.example/archive.zip",
    ]


@pytest.mark.asyncio
async def test_astrbot_updater_falls_back_when_hosted_core_package_is_not_zip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ASTRBOT_CLI", raising=False)
    monkeypatch.delenv("ASTRBOT_LAUNCHER", raising=False)
    monkeypatch.setenv("ASTRBOT_CORE_PACKAGE_BASE_URL", "https://cdn.example/core")

    updater = AstrBotUpdater()
    calls: list[str] = []

    async def fake_fetch_release_info(url: str, latest: bool = True):  # noqa: ARG001
        return [
            {
                "version": "AstrBot v99.0.0",
                "published_at": "2026-06-19T00:00:00Z",
                "body": "hosted core package",
                "tag_name": "v99.0.0",
                "zipball_url": "https://github.example/archive.zip",
            }
        ]

    async def fake_download_file(url: str, path: str, progress_callback=None):  # noqa: ARG001
        calls.append(url)
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.hostname == "cdn.example":
            Path(path).write_bytes(b"not a zip")
            return
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AstrBot-v99.0.0/README.md", "github-core")

    monkeypatch.setattr(updater, "_fetch_release_info", fake_fetch_release_info)
    monkeypatch.setattr(updater, "_download_file", fake_download_file)

    zip_path = await updater._download_core_package(
        latest=False,
        version="v99.0.0",
        path=tmp_path / "core.zip",
    )

    assert zip_path == tmp_path / "core.zip"
    assert zipfile.is_zipfile(zip_path)
    assert calls == [
        "https://cdn.example/core/v99.0.0/source.zip",
        "https://github.example/archive.zip",
    ]


@pytest.mark.asyncio
async def test_download_dashboard_falls_back_when_hosted_package_is_not_zip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    async def fake_download_file(
        url: str,
        path: str,
        show_progress: bool = False,  # noqa: ARG001
        progress_callback=None,  # noqa: ARG001
        allow_insecure_ssl_fallback: bool = True,  # noqa: ARG001
    ) -> None:
        calls.append(url)
        parsed = urlparse(url)
        if (
            parsed.scheme == "https"
            and parsed.hostname == "astrbot-registry.soulter.top"
        ):
            Path(path).write_bytes(b"not a zip")
            return
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("dist/index.html", "dashboard")

    monkeypatch.setattr(dashboard_assets, "download_file", fake_download_file)

    zip_path = tmp_path / "dashboard.zip"
    await dashboard_assets._download_package(
        path=str(zip_path),
        version="v99.0.0",
        extract=False,
    )

    assert zipfile.is_zipfile(zip_path)
    assert calls == [
        "https://astrbot-registry.soulter.top/download/astrbot-dashboard/v99.0.0/dist.zip",
        "https://github.com/AstrBotDevs/AstrBot/releases/download/v99.0.0/AstrBot-v99.0.0-dashboard.zip",
    ]


@pytest.mark.asyncio
async def test_fetch_release_info_uses_httpx_client_with_env_proxy_support(
    monkeypatch: pytest.MonkeyPatch,
    fake_async_client_state: _FakeAsyncClientState,
) -> None:
    import astrbot.core.zip_updater as zip_updater_module

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
        zip_updater_module,
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
        zip_updater_module,
        "httpx",
        _build_fake_httpx_module(fake_async_client_state),
        raising=False,
    )

    release_info = await _RepoZipUpdater()._fetch_release_info(
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
    import astrbot.core.zip_updater as zip_updater_module

    fake_async_client_state.json_payload = {"default_branch": "trunk"}
    fake_async_client_state.stream_payload = b"zip-data"
    monkeypatch.setattr(
        zip_updater_module,
        "download_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError(
                "download_from_repo_url should not use aiohttp download_file"
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        zip_updater_module,
        "httpx",
        _build_fake_httpx_module(fake_async_client_state),
        raising=False,
    )

    target_path = tmp_path / "AstrBot"
    await _RepoZipUpdater()._download_repository(
        str(target_path),
        "https://github.com/AstrBotDevs/AstrBot",
    )

    assert (tmp_path / "AstrBot.zip").read_bytes() == b"zip-data"
    assert fake_async_client_state.requested_urls == [
        "https://api.github.com/repos/AstrBotDevs/AstrBot"
    ]
    assert fake_async_client_state.stream_urls == [
        "https://github.com/AstrBotDevs/AstrBot/archive/refs/heads/trunk.zip"
    ]
    assert fake_async_client_state.init_kwargs is not None
    assert fake_async_client_state.init_kwargs["follow_redirects"] is True
    assert fake_async_client_state.init_kwargs["timeout"] == 1800.0
    assert fake_async_client_state.init_kwargs["trust_env"] is True
    assert fake_async_client_state.init_kwargs["verify"] == certifi.where()


@pytest.mark.asyncio
async def test_download_from_repo_url_uses_explicit_branch_without_default_branch_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    updater = _RepoZipUpdater()
    calls: list[str] = []

    async def fail_fetch_repository_default_branch(
        repository,
    ):  # noqa: ARG001
        raise AssertionError("explicit branch should not fetch the default branch")

    async def fake_download_file(url: str, path: str):
        calls.append(url)
        Path(path).write_bytes(b"zip-data")

    monkeypatch.setattr(
        updater,
        "_fetch_repository_default_branch",
        fail_fetch_repository_default_branch,
    )
    monkeypatch.setattr(updater, "_download_file", fake_download_file)

    await updater._download_repository(
        str(tmp_path / "AstrBot"),
        "https://github.com/AstrBotDevs/AstrBot/tree/dev",
        proxy="https://proxy.example/",
    )

    assert calls == [
        "https://proxy.example/https://github.com/AstrBotDevs/AstrBot/archive/refs/heads/dev.zip"
    ]


@pytest.mark.asyncio
async def test_plugin_updater_shallow_clones_non_github_repository(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import astrbot.core.star.updater as plugin_updater_module

    updater = _PluginUpdater()
    updater.plugin_store_path = str(tmp_path)
    clone_args: tuple[str, ...] = ()

    class FakeGitProcess:
        returncode = 0

        async def communicate(self):
            target = Path(clone_args[-1])
            target.mkdir(parents=True)
            (target / ".git").mkdir()
            (target / "metadata.yaml").write_text(
                "\n".join(
                    [
                        "name: demo_plugin",
                        "desc: Demo plugin",
                        "version: 1.0.0",
                        "author: AstrBot Team",
                    ]
                ),
                encoding="utf-8",
            )
            return b"", b""

        def kill(self) -> None:
            raise AssertionError("successful clone must not be killed")

    async def fake_create_subprocess_exec(*args, **_kwargs):
        nonlocal clone_args
        clone_args = args
        return FakeGitProcess()

    monkeypatch.setattr(plugin_updater_module.shutil, "which", lambda _name: "/git")
    monkeypatch.setattr(
        plugin_updater_module.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    plugin_path = await updater.install("https://gitee.com/astrbot/demo-plugin.git")

    assert plugin_path == str(tmp_path / "demo_plugin")
    assert clone_args == (
        "/git",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        "--",
        "https://gitee.com/astrbot/demo-plugin.git",
        str(tmp_path / "demo_plugin"),
    )
    assert not (tmp_path / "demo_plugin" / ".git").exists()


@pytest.mark.asyncio
async def test_plugin_updater_git_clone_requires_git(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import astrbot.core.star.updater as plugin_updater_module

    updater = _PluginUpdater()
    monkeypatch.setattr(plugin_updater_module.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="未找到 git 命令"):
        await updater._clone_repository(
            "git@github.com:AstrBotDevs/demo.git",
            tmp_path / "demo",
        )


@pytest.mark.asyncio
async def test_plugin_updater_inspects_github_repository_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = _PluginUpdater()
    requested_urls: list[str] = []
    source = SimpleNamespace(
        raw_file_url=lambda filename: (
            "https://raw.githubusercontent.com/AstrBotDevs/"
            f"astrbot-plugin-demo/trunk/{filename}"
        ),
    )

    async def fake_resolve_repository_source(repo_url: str):
        assert repo_url == "https://github.com/AstrBotDevs/astrbot-plugin-demo"
        return source

    def handle_request(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.endswith("metadata.yaml"):
            return httpx.Response(404)
        return httpx.Response(
            200,
            text="\n".join(
                [
                    "name: astrbot_plugin_demo",
                    "description: Demo plugin",
                    "version: 2.0.0",
                    "author: AstrBotDevs",
                ]
            ),
        )

    monkeypatch.setattr(
        updater,
        "_resolve_repository_source",
        fake_resolve_repository_source,
    )
    monkeypatch.setattr(
        updater,
        "_create_httpx_client",
        lambda timeout=30.0: httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request),
            timeout=timeout,
        ),
    )

    result = await updater.inspect_repository(
        "https://github.com/AstrBotDevs/astrbot-plugin-demo",
        "https://proxy.example/",
    )

    assert result["name"] == "astrbot_plugin_demo"
    assert result["desc"] == "Demo plugin"
    assert requested_urls[-1] == (
        "https://proxy.example/https://raw.githubusercontent.com/AstrBotDevs/"
        "astrbot-plugin-demo/trunk/metadata.yml"
    )


@pytest.mark.asyncio
async def test_plugin_updater_rejects_large_repository_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updater = _PluginUpdater()
    source = SimpleNamespace(
        raw_file_url=lambda filename: f"https://example.com/{filename}",
    )

    async def fake_resolve_repository_source(repo_url: str):  # noqa: ARG001
        return source

    def handle_request(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(
            200,
            headers={"Content-Length": str(1024 * 1024 + 1)},
        )

    monkeypatch.setattr(
        updater,
        "_resolve_repository_source",
        fake_resolve_repository_source,
    )
    monkeypatch.setattr(
        updater,
        "_create_httpx_client",
        lambda timeout=30.0: httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request),
            timeout=timeout,
        ),
    )

    with pytest.raises(ValueError, match="metadata.yaml 超过 1MB"):
        await updater.inspect_repository("https://github.com/example/plugin")


def test_create_httpx_client_uses_custom_verify_setting(
    monkeypatch: pytest.MonkeyPatch,
    fake_async_client_state: _FakeAsyncClientState,
) -> None:
    import astrbot.core.zip_updater as zip_updater_module

    custom_verify = "/tmp/custom-ca.pem"

    monkeypatch.setattr(
        zip_updater_module,
        "httpx",
        _build_fake_httpx_module(fake_async_client_state),
        raising=False,
    )

    _RepoZipUpdater(verify=custom_verify)._create_httpx_client(timeout=45.0)

    assert fake_async_client_state.init_kwargs is not None
    assert fake_async_client_state.init_kwargs["follow_redirects"] is True
    assert fake_async_client_state.init_kwargs["timeout"] == 45.0
    assert fake_async_client_state.init_kwargs["trust_env"] is True
    assert fake_async_client_state.init_kwargs["verify"] == custom_verify


@pytest.mark.asyncio
async def test_fetch_release_info_logs_status_code_and_truncated_body_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updater as zip_updater_module

    url = "https://api.soulter.top/releases"
    body = "x" * 1005
    log_messages: list[str] = []

    monkeypatch.setattr(
        _RepoZipUpdater,
        "_create_httpx_client",
        staticmethod(
            lambda timeout=30.0: _FakeStatusErrorAsyncClient(  # noqa: ARG005
                _FakeStatusErrorResponse(502, body, url)
            )
        ),
    )
    monkeypatch.setattr(
        zip_updater_module.logger,
        "error",
        lambda message: log_messages.append(message),
    )

    with pytest.raises(Exception, match="Failed to parse release information"):
        await _RepoZipUpdater()._fetch_release_info(url)

    assert any("status 502" in message for message in log_messages)
    assert any("response: " in message for message in log_messages)
    assert any("...[truncated]" in message for message in log_messages)


@pytest.mark.asyncio
async def test_download_file_removes_partial_file_when_stream_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        _RepoZipUpdater,
        "_create_httpx_client",
        staticmethod(
            lambda timeout=30.0: _FakeFailingStreamAsyncClient()  # noqa: ARG005
        ),
    )

    target_path = tmp_path / "partial.zip"

    with pytest.raises(RuntimeError, match="stream interrupted"):
        await _RepoZipUpdater()._download_file(
            "https://example.com/archive.zip",
            str(target_path),
        )

    assert not target_path.exists()


@pytest.mark.asyncio
async def test_download_file_logs_url_and_target_path_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import astrbot.core.zip_updater as zip_updater_module

    url = "https://example.com/archive.zip"
    target_path = tmp_path / "logged-partial.zip"
    log_messages: list[str] = []

    monkeypatch.setattr(
        _RepoZipUpdater,
        "_create_httpx_client",
        staticmethod(
            lambda timeout=30.0: _FakeFailingStreamAsyncClient()  # noqa: ARG005
        ),
    )
    monkeypatch.setattr(
        zip_updater_module.logger,
        "error",
        lambda message: log_messages.append(message),
    )

    with pytest.raises(RuntimeError, match="stream interrupted"):
        await _RepoZipUpdater()._download_file(url, str(target_path))

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
    import astrbot.core.zip_updater as zip_updater_module

    target_dir = r"\\?\C:\Users\admin\AppData\Local\AstrBot\backend\app"
    captured = _exercise_unzip_file_windows_path_normalization(
        monkeypatch,
        updater_module=zip_updater_module,
        zip_updater_module=zip_updater_module,
        updater=_RepoZipUpdater(),
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
    import astrbot.core.star.updater as plugin_updater_module
    import astrbot.core.zip_updater as zip_updater_module

    target_dir = r"\\?\C:\Users\admin\AppData\Local\AstrBot\data\plugins\demo"
    captured = _exercise_unzip_file_windows_path_normalization(
        monkeypatch,
        updater_module=plugin_updater_module,
        zip_updater_module=zip_updater_module,
        updater=_PluginUpdater.__new__(_PluginUpdater),
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
    import astrbot.core.zip_updater as zip_updater_module

    monkeypatch.setattr(
        zip_updater_module.os, "makedirs", lambda path, exist_ok=True: None
    )
    monkeypatch.setattr(zip_updater_module, "ensure_dir", lambda path: None)
    monkeypatch.setattr(zip_updater_module.os.path, "join", ntpath.join)
    monkeypatch.setattr(zip_updater_module.os.path, "normpath", ntpath.normpath)
    monkeypatch.setattr(zip_updater_module.os.path, "commonpath", ntpath.commonpath)
    monkeypatch.setattr(
        zip_updater_module.zipfile,
        "ZipFile",
        lambda path, mode: _FakeZipArchive(_build_fake_archive_entries(archive_root)),
    )

    with pytest.raises(ValueError, match=expected_error):
        _RepoZipUpdater()._extract_archive(
            "temp.zip",
            r"\\?\C:\Users\admin\target",
        )


def test_repo_unzip_file_handles_archives_without_explicit_root_dir_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import astrbot.core.zip_updater as zip_updater_module

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
        zip_updater_module.os, "makedirs", lambda path, exist_ok=True: None
    )
    monkeypatch.setattr(zip_updater_module, "ensure_dir", lambda path: None)
    monkeypatch.setattr(zip_updater_module.os.path, "join", ntpath.join)
    monkeypatch.setattr(zip_updater_module.os.path, "normpath", ntpath.normpath)
    monkeypatch.setattr(zip_updater_module.os.path, "commonpath", ntpath.commonpath)
    monkeypatch.setattr(zip_updater_module.os.path, "isdir", lambda path: False)
    monkeypatch.setattr(zip_updater_module.os.path, "exists", lambda path: False)
    monkeypatch.setattr(
        zip_updater_module.zipfile,
        "ZipFile",
        lambda path, mode: _FakeZipArchive(
            _build_fake_archive_entries_with_first_file(archive_root)
        ),
    )
    monkeypatch.setattr(zip_updater_module.logger, "debug", lambda message: None)
    monkeypatch.setattr(zip_updater_module.logger, "warning", lambda message: None)
    monkeypatch.setattr(zip_updater_module.os, "listdir", fake_listdir)
    monkeypatch.setattr(
        zip_updater_module.shutil,
        "move",
        lambda src, dst: captured.__setitem__("move", (src, dst)),
    )
    monkeypatch.setattr(
        zip_updater_module.shutil,
        "rmtree",
        lambda path, onerror=None: captured.__setitem__("cleanup", path),
    )
    monkeypatch.setattr(
        zip_updater_module.os,
        "remove",
        lambda path: captured.__setitem__("removed", path),
    )

    _RepoZipUpdater()._extract_archive("temp.zip", target_dir)

    assert captured["listdir"] == expected_root
    assert captured["move"] == (expected_file, target_dir)
    assert captured["cleanup"] == expected_root
    assert captured["removed"] == "temp.zip"
