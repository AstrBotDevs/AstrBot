import asyncio
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import httpx
import pytest

from astrbot.core.repository import GitHubRepository
from astrbot.core.star.updater import _PluginUpdater
from astrbot.core.zip_updater import _RepoZipUpdater

REPO_URL = "https://github.com/example/plugin"
API_URL = "https://api.github.com/repos/example/plugin"
METADATA = b"name: plugin\ndesc: Demo\nversion: 1.0.0\nauthor: Example\n"


@pytest.fixture
def mock_http(monkeypatch):
    """Provide an HTTP transport while exercising the real updater methods.

    Returns:
        A transport installer that returns its ordered request URL list.
    """

    def install(updater, handler):
        requests = []

        async def record(request):
            requests.append(str(request.url))
            result = handler(request)
            return await result if asyncio.iscoroutine(result) else result

        monkeypatch.setattr(
            updater,
            "_create_httpx_client",
            lambda timeout=30.0: httpx.AsyncClient(
                transport=httpx.MockTransport(record),
                follow_redirects=True,
                timeout=timeout,
            ),
        )
        return requests

    return install


@pytest.mark.parametrize("branch", [None, "main", "master", "release/custom", "HEAD"])
def test_repository_archive_and_raw_reference(branch):
    repository = GitHubRepository("example", "plugin", branch)
    expected_archive = (
        f"{REPO_URL}/archive/refs/heads/{branch}.zip"
        if branch
        else f"{REPO_URL}/archive/HEAD.zip"
    )
    assert repository.branch == branch
    assert repository.archive_url == expected_archive
    assert repository.raw_file_url("metadata.yaml") == (
        f"https://raw.githubusercontent.com/example/plugin/{branch or 'HEAD'}/metadata.yaml"
    )
    assert repository.revision_archive_url("HEAD") == f"{REPO_URL}/archive/HEAD.zip"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "proxy", ["", "https://proxy.example", "https://proxy.example/"]
)
@pytest.mark.parametrize(
    ("source", "expected_branch"),
    [
        ("main", "main"),
        ("master", "master"),
        ("release/custom", "release/custom"),
        ("explicit:dev", "dev"),
        ("explicit:feature/demo", "feature/demo"),
        ("403", None),
        ("connect", None),
        ("timeout", None),
        ("empty", None),
        ("missing", None),
        ("null", None),
        ("whitespace", None),
    ],
)
async def test_download_repository_source(
    mock_http, tmp_path, caplog, proxy, source, expected_branch
):
    updater = _RepoZipUpdater()
    explicit = source.startswith("explicit:")
    repo_url = f"{REPO_URL}/tree/{expected_branch}" if explicit else REPO_URL
    archive_url = (
        f"{REPO_URL}/archive/refs/heads/{expected_branch}.zip"
        if expected_branch
        else f"{REPO_URL}/archive/HEAD.zip"
    )
    request_url = f"{proxy.rstrip('/')}/{archive_url}" if proxy else archive_url
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr("plugin-commit/main.py", "VALUE = 2\n")

    def handler(request):
        if str(request.url) == API_URL:
            assert not explicit, "Explicit branches must skip repository metadata"
            if source == "403":
                return httpx.Response(403)
            if source == "connect":
                raise httpx.ConnectError("offline", request=request)
            if source == "timeout":
                raise httpx.ReadTimeout("timed out", request=request)
            values = {"empty": "", "null": None, "whitespace": "  "}
            return httpx.Response(
                200,
                json={}
                if source == "missing"
                else {"default_branch": values.get(source, source)},
            )
        if str(request.url) == request_url:
            return httpx.Response(200, content=payload.getvalue())
        return httpx.Response(404)

    requests = mock_http(updater, handler)
    target = tmp_path / "plugin"
    await updater._download_repository(str(target), repo_url, proxy)

    assert requests == ([] if explicit else [API_URL]) + [request_url]
    if expected_branch is None:
        assert "Could not resolve" in caplog.text
        assert "default reference HEAD" in caplog.text
        assert "branch main" not in caplog.text
    with ZipFile(target.with_suffix(".zip")) as archive:
        assert archive.testzip() is None
        assert archive.read("plugin-commit/main.py") == b"VALUE = 2\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["install", "update"])
@pytest.mark.parametrize(
    "archive_root", ["plugin-main", "plugin-master", "plugin-trunk", "plugin-0c0d52b"]
)
async def test_plugin_fallback_extracts_archive(
    mock_http, tmp_path, operation, archive_root
):
    # Root names test extraction compatibility, not remote branch selection.
    updater = _PluginUpdater()
    updater.plugin_store_path = str(tmp_path)
    payload = BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr(f"{archive_root}/metadata.yaml", METADATA)
        archive.writestr(f"{archive_root}/main.py", "VALUE = 2\n")

    def handler(request):
        if str(request.url) == API_URL:
            return httpx.Response(403)
        if str(request.url) == f"{REPO_URL}/archive/HEAD.zip":
            return httpx.Response(
                302,
                headers={
                    "Location": "https://codeload.github.com/example/plugin/zip/commit"
                },
            )
        if request.url.host == "codeload.github.com":
            return httpx.Response(200, content=payload.getvalue())
        return httpx.Response(404)

    requests = mock_http(updater, handler)
    target = tmp_path / "plugin"
    if operation == "install":
        result = await updater.install(REPO_URL)
    else:
        target.mkdir()
        (target / "old.py").write_text("old", encoding="utf-8")
        result = await updater.update(
            SimpleNamespace(name="plugin", root_dir_name="plugin", repo=REPO_URL)
        )
    assert result == str(target)
    assert (target / "main.py").read_bytes() == b"VALUE = 2\n"
    assert (target / "metadata.yaml").read_bytes() == METADATA
    assert not (target / "old.py").exists()
    assert not (target / archive_root).exists()
    assert not target.with_suffix(".zip").exists()
    assert requests == [
        API_URL,
        f"{REPO_URL}/archive/HEAD.zip",
        "https://codeload.github.com/example/plugin/zip/commit",
    ]


class InterruptedStream(httpx.AsyncByteStream):
    """Deliver a full buffered chunk before failing or cancelling the transfer."""

    def __init__(self, error):
        self.error = error

    async def __aiter__(self):
        yield b"partial!" * 1024
        raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["install", "update"])
@pytest.mark.parametrize(
    "source", ["fallback", "resolved", "explicit:dev", "explicit:feature/demo"]
)
@pytest.mark.parametrize(
    "failure", [404, 403, 429, 500, "timeout", "connect", "stream", "cancel"]
)
async def test_failed_archive_preserves_installed_plugin(
    mock_http, tmp_path, caplog, operation, source, failure
):
    updater = _PluginUpdater()
    updater.plugin_store_path = str(tmp_path)
    target = tmp_path / "plugin"
    target.mkdir()
    (target / "main.py").write_bytes(b"original plugin")
    (target / "metadata.yaml").write_bytes(METADATA)
    explicit = source.startswith("explicit:")
    branch = source.split(":", 1)[1] if explicit else "main"
    repo_url = f"{REPO_URL}/tree/{branch}" if explicit else REPO_URL
    archive_url = (
        f"{REPO_URL}/archive/HEAD.zip"
        if source == "fallback"
        else f"{REPO_URL}/archive/refs/heads/{branch}.zip"
    )
    error_type = {
        "timeout": httpx.ReadTimeout,
        "connect": httpx.ConnectError,
        "stream": httpx.ReadError,
        "cancel": asyncio.CancelledError,
    }.get(failure, httpx.HTTPStatusError)

    def handler(request):
        if str(request.url) == API_URL:
            assert not explicit
            return httpx.Response(
                403 if source == "fallback" else 200,
                json={"default_branch": "main"},
            )
        if isinstance(failure, int):
            return httpx.Response(failure, content=b"not a ZIP")
        error = error_type("transfer failed")
        if failure in {"stream", "cancel"}:
            return httpx.Response(200, stream=InterruptedStream(error))
        raise error

    requests = mock_http(updater, handler)
    with pytest.raises(error_type):
        if operation == "install":
            await updater.install(repo_url, target_dir=tmp_path / "new_plugin")
        else:
            await updater.update(
                SimpleNamespace(name="plugin", root_dir_name="plugin", repo=repo_url)
            )

    assert requests == ([] if explicit else [API_URL]) + [archive_url]
    assert "Failed to download file:" in caplog.text
    assert (target / "main.py").read_bytes() == b"original plugin"
    assert (target / "metadata.yaml").read_bytes() == METADATA
    assert sorted(p.name for p in tmp_path.iterdir()) == ["plugin"]
    assert sorted(p.name for p in target.iterdir()) == ["main.py", "metadata.yaml"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "proxy", ["", "https://proxy.example", "https://proxy.example/"]
)
async def test_inspection_uses_default_reference_when_api_fails(mock_http, proxy):
    updater = _PluginUpdater()
    raw_url = "https://raw.githubusercontent.com/example/plugin/HEAD/metadata.yaml"
    request_url = f"{proxy.rstrip('/')}/{raw_url}" if proxy else raw_url

    def handler(request):
        if str(request.url) == API_URL:
            return httpx.Response(403)
        return httpx.Response(
            200 if str(request.url) == request_url else 404, content=METADATA
        )

    requests = mock_http(updater, handler)
    result = await updater.inspect_repository(REPO_URL, proxy)
    assert result["name"] == "plugin"
    assert requests == [API_URL, request_url]


@pytest.mark.asyncio
async def test_concurrent_repository_resolution_is_local(mock_http, tmp_path):
    updater = _RepoZipUpdater()
    second_api_seen = asyncio.Event()

    async def handler(request):
        if request.url.host == "api.github.com":
            if request.url.path.endswith("/plugin"):
                await second_api_seen.wait()
                return httpx.Response(403)
            second_api_seen.set()
            return httpx.Response(200, json={"default_branch": "custom"})
        return httpx.Response(200, content=str(request.url).encode())

    requests = mock_http(updater, handler)
    await asyncio.wait_for(
        asyncio.gather(
            updater._download_repository(str(tmp_path / "first"), REPO_URL),
            updater._download_repository(str(tmp_path / "second"), f"{REPO_URL}2"),
        ),
        timeout=5,
    )
    assert (tmp_path / "first.zip").read_text() == f"{REPO_URL}/archive/HEAD.zip"
    assert (
        tmp_path / "second.zip"
    ).read_text() == f"{REPO_URL}2/archive/refs/heads/custom.zip"
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_unresolved_branch_stays_unknown(mock_http):
    updater = _RepoZipUpdater()
    requests = mock_http(updater, lambda request: httpx.Response(403))
    repository = await updater._resolve_repository_source(REPO_URL)
    assert repository.branch is None
    assert requests == [API_URL]


@pytest.mark.asyncio
async def test_archive_write_failure_removes_partial_file(
    mock_http, monkeypatch, tmp_path
):
    updater = _RepoZipUpdater()
    target = tmp_path / "plugin.zip"
    requests = mock_http(
        updater, lambda request: httpx.Response(200, content=b"archive")
    )
    original_open = Path.open
    progress = []

    @contextmanager
    def failing_open(path, *args, **kwargs):
        with original_open(path, *args, **kwargs) as file:

            def write(data):
                file.write(data[:3])
                raise OSError("disk full")

            yield SimpleNamespace(write=write)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(OSError, match="disk full"):
        await updater._download_file(
            f"{REPO_URL}/archive/HEAD.zip",
            str(target),
            progress_callback=progress.append,
        )
    assert not target.exists()
    assert requests == [f"{REPO_URL}/archive/HEAD.zip"]
    assert all(event["percent"] != 1 for event in progress)


@pytest.mark.asyncio
async def test_metadata_cancellation_does_not_start_archive_download(
    mock_http, tmp_path
):
    updater = _RepoZipUpdater()

    def handler(request):
        raise asyncio.CancelledError

    requests = mock_http(updater, handler)
    with pytest.raises(asyncio.CancelledError):
        await updater._download_repository(str(tmp_path / "plugin"), REPO_URL)
    assert requests == [API_URL]
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("default_branch", ["main", "master", "custom"])
async def test_fallback_does_not_choose_an_existing_nondefault_branch(
    mock_http, tmp_path, default_branch
):
    # Model a server with both main and master. Real HEAD semantics are verified
    # separately; this test checks that the updater never guesses a branch.
    updater = _RepoZipUpdater()

    def handler(request):
        if str(request.url) == API_URL:
            return httpx.Response(403)
        branch = {
            f"{REPO_URL}/archive/HEAD.zip": default_branch,
            f"{REPO_URL}/archive/refs/heads/main.zip": "main",
            f"{REPO_URL}/archive/refs/heads/master.zip": "master",
        }[str(request.url)]
        payload = BytesIO()
        with ZipFile(payload, "w") as archive:
            archive.writestr("plugin/source.txt", branch)
        return httpx.Response(200, content=payload.getvalue())

    requests = mock_http(updater, handler)
    await updater._download_repository(str(tmp_path / "plugin"), REPO_URL)
    assert requests == [API_URL, f"{REPO_URL}/archive/HEAD.zip"]
    with ZipFile(tmp_path / "plugin.zip") as archive:
        assert archive.read("plugin/source.txt").decode() == default_branch
