"""Regression coverage for mirror-first source and Dashboard updates."""

import hashlib
import io
import tarfile
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from astrbot.core import updater as updater_module
from astrbot.core.updater import AstrBotUpdater


def _sdist(files=None, extra=None, version="99.0.0"):
    """Build a complete source archive with optional corruptions.

    Args:
        files: Relative file overrides; None values remove a file.
        extra: Optional tar member for archive safety tests.
        version: Package version shared by metadata and bundled assets.

    Returns:
        Compressed source archive bytes.
    """
    contents = {
        "PKG-INFO": f"Metadata-Version: 2.4\nName: AstrBot\nVersion: {version}\n\n",
        "main.py": "SOURCE = 'mirror'\n",
        "pyproject.toml": f'[project]\nname="AstrBot"\nversion="{version}"\n',
        "requirements.txt": "httpx\n",
        "astrbot/__init__.py": f'__version__ = "{version}"\n',
        "astrbot/dashboard/dist/index.html": '<script src="/assets/app.js"></script>',
        "astrbot/dashboard/dist/assets/app.js": "// mirror dashboard\n",
        "astrbot/dashboard/dist/assets/version": f"v{version}",
    }
    contents.update(files or {})
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, content in contents.items():
            if content is None:
                continue
            data = content.encode()
            member = tarfile.TarInfo(f"astrbot-{version}/{name}")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if extra:
            archive.addfile(extra, io.BytesIO(b""))
    return stream.getvalue()


@pytest.fixture
def mirror_update(monkeypatch, tmp_path):
    """Isolate all update writes and mirror requests from the running installation."""
    monkeypatch.delenv("ASTRBOT_CLI", raising=False)
    monkeypatch.delenv("ASTRBOT_LAUNCHER", raising=False)
    install = tmp_path / "install"
    install.mkdir()
    (install / "main.py").write_text("old core")
    data = tmp_path / "data"
    (data / "dist").mkdir(parents=True)
    (data / "dist/index.html").write_text("old dashboard")
    updater = AstrBotUpdater()
    updater._main_path = str(install)
    monkeypatch.setattr(
        updater_module, "get_astrbot_temp_path", lambda: str(tmp_path / "temp")
    )
    monkeypatch.setattr(updater_module, "get_astrbot_data_path", lambda: str(data))
    state = SimpleNamespace(
        updater=updater,
        install=install,
        data=data,
        temp=tmp_path / "temp",
        payload=_sdist(),
        index=None,
        index_status=200,
        download_status=200,
        network_error=None,
        requests=[],
        fallback=[],
        events=[],
    )

    def handle(request):
        state.requests.append(str(request.url))
        if request.url.host == "mirrors.cernet.edu.cn":
            return httpx.Response(
                302,
                headers={"Location": "https://mirror.example/pypi/web/simple/astrbot/"},
            )
        if request.url.path.endswith("/simple/astrbot/"):
            if state.network_error == "index":
                raise httpx.ReadTimeout("mirror timed out", request=request)
            index = state.index
            if index is None:
                digest = hashlib.sha256(state.payload).hexdigest()
                index = f'<a href="../../packages/astrbot-99.0.0.tar.gz#sha256={digest}">source</a>'
            return httpx.Response(state.index_status, text=index)
        assert request.url.host == "mirror.example"
        assert request.url.path == "/pypi/web/packages/astrbot-99.0.0.tar.gz"
        assert not request.url.fragment
        if state.network_error == "download":
            raise httpx.ReadTimeout("download timed out", request=request)
        return httpx.Response(state.download_status, content=state.payload)

    monkeypatch.setattr(
        updater,
        "_create_httpx_client",
        lambda timeout=30: httpx.AsyncClient(
            transport=httpx.MockTransport(handle),
            follow_redirects=True,
            timeout=timeout,
        ),
    )
    state.releases = AsyncMock(
        return_value=[
            {
                "tag_name": "v99.0.0",
                "zipball_url": "https://github.example/core.zip",
            }
        ]
    )
    monkeypatch.setattr(updater, "_fetch_release_info", state.releases)

    async def legacy_dashboard(*, path, **kwargs):
        state.fallback.append(("dashboard", kwargs))
        assert (install / "main.py").read_text() == "old core"
        assert (data / "dist/index.html").read_text() == "old dashboard"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "dist/index.html", '<script src="/assets/fallback.js"></script>'
            )
            archive.writestr("dist/assets/fallback.js", "// fallback")
            archive.writestr("dist/assets/version", "v99.0.0")

    async def legacy_core(*, path, **kwargs):
        state.fallback.append(("core", kwargs))
        assert (install / "main.py").read_text() == "old core"
        assert (data / "dist/index.html").read_text() == "old dashboard"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AstrBot-release/main.py", "fallback core")
        return path

    monkeypatch.setattr(updater_module, "_download_package", legacy_dashboard)
    monkeypatch.setattr(updater, "_download_core_package", legacy_core)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["v99.0.0", None, "latest"])
async def test_mirror_applies_matching_source_and_bundled_dashboard(
    mirror_update, version
):
    state = mirror_update

    async def progress(event):
        state.events.append(event)

    await state.updater.update(
        version, proxy="https://github-proxy.example", progress_callback=progress
    )
    assert (state.install / "main.py").read_text() == "SOURCE = 'mirror'\n"
    assert (state.data / "dist/assets/app.js").read_text() == "// mirror dashboard\n"
    assert (state.install / "astrbot/dashboard/dist/assets/app.js").read_bytes() == (
        state.data / "dist/assets/app.js"
    ).read_bytes()
    assert state.fallback == []
    assert len(state.requests) == 3
    assert state.releases.await_count == (0 if version == "v99.0.0" else 1)
    assert [(event.stage, event.status) for event in state.events][-1] == (
        "apply",
        "done",
    )
    assert {event.stage for event in state.events} == {
        "dashboard",
        "core",
        "verify",
        "apply",
    }
    assert not list((state.temp / "updates").iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "missing-version",
        "index-error",
        "index-timeout",
        "download-timeout",
        "download-error",
        "hash-mismatch",
        "missing-hash",
        "corrupt-tar",
        "missing-dashboard",
        "incomplete-dashboard",
        "wrong-dashboard-version",
        "missing-core",
        "wrong-metadata",
        "traversal",
        "symlink",
        "hardlink",
        "absolute",
        "windows-path",
        "duplicate",
        "multiple-roots",
        "yanked",
        "wheel-only",
    ],
)
async def test_mirror_failure_uses_existing_downloads_before_applying(
    mirror_update, failure
):
    state = mirror_update
    if failure == "missing-version":
        state.index = '<a href="astrbot-99.0.1.tar.gz">other version</a>'
    elif failure in ("index-timeout", "download-timeout"):
        state.network_error = failure.split("-")[0]
    elif failure == "index-error":
        state.index_status = 503
    elif failure == "download-error":
        state.download_status = 404
    elif failure in ("hash-mismatch", "missing-hash"):
        fragment = "#sha256=" + "0" * 64 if failure == "hash-mismatch" else ""
        state.index = (
            f'<a href="../../packages/astrbot-99.0.0.tar.gz{fragment}">source</a>'
        )
    elif failure == "corrupt-tar":
        state.payload = b"not an archive"
    elif failure == "missing-dashboard":
        state.payload = _sdist({"astrbot/dashboard/dist/index.html": None})
    elif failure == "incomplete-dashboard":
        state.payload = _sdist({"astrbot/dashboard/dist/assets/app.js": None})
    elif failure == "wrong-dashboard-version":
        state.payload = _sdist({"astrbot/dashboard/dist/assets/version": "v98.0.0"})
    elif failure == "missing-core":
        state.payload = _sdist({"main.py": None})
    elif failure == "wrong-metadata":
        state.payload = _sdist({"PKG-INFO": "Name: AstrBot\nVersion: 98.0.0\n"})
    elif failure in (
        "traversal",
        "absolute",
        "windows-path",
        "multiple-roots",
        "duplicate",
    ):
        path = {
            "traversal": "astrbot-99.0.0/../outside",
            "absolute": "/outside",
            "windows-path": "astrbot-99.0.0/C:\\outside",
            "multiple-roots": "other/outside",
            "duplicate": "astrbot-99.0.0/main.py",
        }[failure]
        state.payload = _sdist(extra=tarfile.TarInfo(path))
    elif failure in ("symlink", "hardlink"):
        member = tarfile.TarInfo("astrbot-99.0.0/link")
        member.type = tarfile.SYMTYPE if failure == "symlink" else tarfile.LNKTYPE
        member.linkname = "../../outside"
        state.payload = _sdist(extra=member)
    elif failure == "yanked":
        state.index = '<a data-yanked="" href="astrbot-99.0.0.tar.gz">yanked</a>'
    elif failure == "wheel-only":
        state.index = '<a href="astrbot-99.0.0-py3-none-any.whl">wheel</a>'
    await state.updater.update("v99.0.0", proxy="https://github-proxy.example")
    assert [kind for kind, _ in state.fallback] == ["dashboard", "core"]
    assert all(
        kwargs["proxy"] == "https://github-proxy.example"
        for _, kwargs in state.fallback
    )
    assert (state.install / "main.py").read_text() == "fallback core"
    assert (state.data / "dist/assets/fallback.js").is_file()
    assert not (state.install / "astrbot").exists()
    assert not list((state.temp / "updates").iterdir())
    state.releases.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_updates_skip_pypi(mirror_update):
    state = mirror_update
    revision = "a" * 40
    await state.updater.update(revision)
    assert state.requests == []
    state.releases.assert_not_awaited()
    assert all(kwargs["version"] == revision for _, kwargs in state.fallback)


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["ASTRBOT_CLI", "ASTRBOT_LAUNCHER"])
async def test_managed_installs_cannot_bypass_update_restriction(
    mirror_update, monkeypatch, environment
):
    monkeypatch.setenv(environment, "1")
    with pytest.raises(RuntimeError, match="pip or uv tool upgrade"):
        await mirror_update.updater.update("v99.0.0")
    assert mirror_update.requests == []
    assert mirror_update.fallback == []
