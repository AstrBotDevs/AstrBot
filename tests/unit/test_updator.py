import pytest

from astrbot.core.updator import AstrBotUpdator
from astrbot.core.zip_updator import RepoZipUpdator


@pytest.mark.asyncio
async def test_update_supports_nightly_tag(monkeypatch, tmp_path):
    updator = AstrBotUpdator()
    captured: dict[str, str] = {}

    async def mock_download_file(url: str, path: str, *args, **kwargs):
        captured["url"] = url
        captured["path"] = path

    async def mock_fetch_release_info(*args, **kwargs):
        raise AssertionError("nightly update should not fetch stable release list")

    def mock_unzip_file(zip_path: str, target_dir: str):
        captured["zip_path"] = zip_path
        captured["target_dir"] = target_dir

    monkeypatch.delenv("ASTRBOT_CLI", raising=False)
    monkeypatch.delenv("ASTRBOT_LAUNCHER", raising=False)
    monkeypatch.setattr("astrbot.core.updator.download_file", mock_download_file)
    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)
    monkeypatch.setattr(updator, "unzip_file", mock_unzip_file)
    monkeypatch.setattr(updator, "MAIN_PATH", str(tmp_path))

    await updator.update(latest=False, version="nightly")

    assert captured["url"].endswith("/archive/refs/tags/nightly.zip")
    assert captured["path"] == "temp.zip"
    assert captured["zip_path"] == "temp.zip"
    assert captured["target_dir"] == str(tmp_path)


@pytest.mark.asyncio
async def test_get_releases_includes_nightly_tag(monkeypatch):
    updator = AstrBotUpdator()

    stable_release = {
        "version": "v9.9.9",
        "published_at": "2026-03-01T00:00:00Z",
        "body": "stable",
        "tag_name": "v9.9.9",
        "zipball_url": "https://example.com/stable.zip",
    }
    nightly_release = {
        "version": "nightly",
        "published_at": "2026-03-02T00:00:00Z",
        "body": "nightly",
        "tag_name": "nightly",
        "zipball_url": "https://example.com/nightly.zip",
    }

    async def mock_fetch_release_info(url: str, latest: bool = True):
        _ = latest
        if url == updator.ASTRBOT_RELEASE_API:
            return [stable_release]
        if url == f"{updator.GITHUB_RELEASE_API}/tags/{updator.NIGHTLY_TAG}":
            return [nightly_release]
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    releases = await updator.get_releases()

    assert releases[0]["tag_name"] == "nightly"
    assert releases[1]["tag_name"] == "v9.9.9"


@pytest.mark.asyncio
async def test_get_releases_deduplicates_nightly_when_already_in_stable(monkeypatch):
    updator = AstrBotUpdator()

    stable_nightly_release = {
        "version": "nightly",
        "published_at": "2026-03-01T00:00:00Z",
        "body": "stable nightly",
        "tag_name": "nightly",
        "zipball_url": "https://example.com/stable-nightly.zip",
    }
    github_nightly_release = {
        "version": "nightly",
        "published_at": "2026-03-02T00:00:00Z",
        "body": "github nightly",
        "tag_name": "nightly",
        "zipball_url": "https://example.com/github-nightly.zip",
    }

    async def mock_fetch_release_info(url: str, latest: bool = True):
        _ = latest
        if url == updator.ASTRBOT_RELEASE_API:
            return [stable_nightly_release]
        if url == f"{updator.GITHUB_RELEASE_API}/tags/{updator.NIGHTLY_TAG}":
            return [github_nightly_release]
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    releases = await updator.get_releases()

    nightly_releases = [item for item in releases if item["tag_name"] == "nightly"]
    assert len(nightly_releases) == 1
    assert releases[0]["zipball_url"] == "https://example.com/stable-nightly.zip"


@pytest.mark.asyncio
async def test_check_update_skips_nightly_when_prerelease_disabled(monkeypatch):
    updator = RepoZipUpdator()

    async def mock_fetch_release_info(url: str, latest: bool = True):
        _ = url, latest
        return [
            {
                "version": "nightly",
                "published_at": "2026-03-02T00:00:00Z",
                "body": "nightly build",
                "tag_name": "nightly",
                "zipball_url": "https://example.com/nightly.zip",
            },
            {
                "version": "v1.2.3",
                "published_at": "2026-03-01T00:00:00Z",
                "body": "stable release",
                "tag_name": "v1.2.3",
                "zipball_url": "https://example.com/stable.zip",
            },
        ]

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    release = await updator.check_update(
        "https://example.invalid/releases",
        "v1.0.0",
        consider_prerelease=False,
    )

    assert release is not None
    assert release.version == "v1.2.3"


@pytest.mark.asyncio
async def test_check_update_returns_none_when_only_prerelease_and_disabled(monkeypatch):
    updator = RepoZipUpdator()

    async def mock_fetch_release_info(url: str, latest: bool = True):
        _ = url, latest
        return [
            {
                "version": "nightly",
                "published_at": "2026-03-02T00:00:00Z",
                "body": "nightly build",
                "tag_name": "nightly",
                "zipball_url": "https://example.com/nightly.zip",
            },
            {
                "version": "v1.2.3-beta.1",
                "published_at": "2026-03-01T00:00:00Z",
                "body": "beta build",
                "tag_name": "v1.2.3-beta.1",
                "zipball_url": "https://example.com/beta.zip",
            },
        ]

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    release = await updator.check_update(
        "https://example.invalid/releases",
        "v1.0.0",
        consider_prerelease=False,
    )

    assert release is None
