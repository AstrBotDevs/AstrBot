import pytest

from astrbot.core.updator import AstrBotUpdateError, AstrBotUpdator
from astrbot.core.zip_updator import FetchReleaseError, RepoZipUpdator


def test_normalize_release_payload_skips_invalid_entry_when_other_entries_are_valid():
    updator = RepoZipUpdator()
    payload = [
        {
            "name": "v1.0.0",
            "published_at": "2026-03-01T00:00:00Z",
            "tag_name": "v1.0.0",
            "zipball_url": "https://example.com/v1.0.0.zip",
        },
        {
            "name": "v1.0.1",
            "published_at": "2026-03-02T00:00:00Z",
            "body": "release body",
            "tag_name": "v1.0.1",
            "zipball_url": "https://example.com/v1.0.1.zip",
        },
    ]

    releases = updator._normalize_release_payload(
        payload,
        "https://example.invalid/releases",
    )

    assert len(releases) == 1
    assert releases[0]["tag_name"] == "v1.0.1"


def test_normalize_release_payload_raises_on_invalid_item_type():
    updator = RepoZipUpdator()

    with pytest.raises(FetchReleaseError, match="版本信息全部无效"):
        updator._normalize_release_payload(
            ["invalid-release-item"],
            "https://example.invalid/releases",
        )


def test_normalize_release_payload_accepts_valid_payload():
    updator = RepoZipUpdator()
    payload = {
        "name": "v1.0.0",
        "published_at": "2026-03-01T00:00:00Z",
        "body": "release body",
        "tag_name": "v1.0.0",
        "zipball_url": "https://example.com/v1.0.0.zip",
    }

    releases = updator._normalize_release_payload(
        payload,
        "https://example.invalid/releases",
    )

    assert len(releases) == 1
    assert releases[0]["tag_name"] == "v1.0.0"
    assert releases[0]["version"] == "v1.0.0"


def test_normalize_release_payload_raises_when_all_entries_invalid():
    updator = RepoZipUpdator()
    malformed_payload = [
        {
            "name": "v1.0.0",
            "published_at": "2026-03-01T00:00:00Z",
            "tag_name": "v1.0.0",
            "zipball_url": "https://example.com/v1.0.0.zip",
        }
    ]

    with pytest.raises(FetchReleaseError, match="版本信息全部无效"):
        updator._normalize_release_payload(
            malformed_payload,
            "https://example.invalid/releases",
        )


def test_normalize_release_payload_error_contains_context():
    updator = RepoZipUpdator()
    malformed_payload = ["invalid-release-item"]

    with pytest.raises(FetchReleaseError) as exc_info:
        updator._normalize_release_payload(
            malformed_payload,
            "https://example.invalid/releases",
        )

    error = exc_info.value
    assert error.url == "https://example.invalid/releases"
    assert error.detail is not None


@pytest.mark.asyncio
async def test_update_supports_nightly_tag(monkeypatch, tmp_path):
    updator = AstrBotUpdator()
    captured: dict[str, str] = {}

    async def mock_download_file(url: str, path: str, *args, **kwargs):
        captured["url"] = url
        captured["path"] = path

    async def mock_fetch_release_info(url: str):
        if url == updator.ASTRBOT_RELEASE_API:
            return []
        if url == f"{updator.GITHUB_RELEASE_API}/tags/{updator.NIGHTLY_TAG}":
            return [
                {
                    "version": "nightly",
                    "published_at": "2026-03-02T00:00:00Z",
                    "body": "nightly",
                    "tag_name": "nightly",
                    "zipball_url": "https://example.com/nightly.zip",
                }
            ]
        raise AssertionError(f"unexpected URL: {url}")

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

    assert captured["url"] == "https://example.com/nightly.zip"
    assert captured["path"] == "temp.zip"
    assert captured["zip_path"] == "temp.zip"
    assert captured["target_dir"] == str(tmp_path)


@pytest.mark.asyncio
async def test_resolve_update_target_nightly_uses_archive_fallback(monkeypatch):
    updator = AstrBotUpdator()
    updator.GITHUB_ARCHIVE_BASE = "https://github.com/example-org/example-repo/archive"

    async def mock_fetch_release_info(url: str):
        if url == f"{updator.GITHUB_RELEASE_API}/tags/{updator.NIGHTLY_TAG}":
            raise FetchReleaseError("请求失败")
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    target_version, file_url = await updator._resolve_update_target(
        latest=False,
        version="nightly",
    )
    assert target_version == "nightly"
    assert (
        file_url
        == "https://github.com/example-org/example-repo/archive/refs/tags/nightly.zip"
    )


@pytest.mark.asyncio
async def test_resolve_update_target_commit_uses_archive_base():
    updator = AstrBotUpdator()
    updator.GITHUB_ARCHIVE_BASE = "https://github.com/example-org/example-repo/archive"
    version_str = "1234567890123456789012345678901234567890"

    target_version, file_url = await updator._resolve_update_target(
        latest=False,
        version=version_str,
    )
    assert target_version == version_str
    assert (
        file_url
        == "https://github.com/example-org/example-repo/archive/1234567890123456789012345678901234567890.zip"
    )


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

    async def mock_fetch_release_info(url: str):
        if url == updator.ASTRBOT_RELEASE_API:
            return [stable_release]
        if url == f"{updator.GITHUB_RELEASE_API}/tags/{updator.NIGHTLY_TAG}":
            return [nightly_release]
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    releases = await updator.get_releases_with_nightly()

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

    async def mock_fetch_release_info(url: str):
        if url == updator.ASTRBOT_RELEASE_API:
            return [stable_nightly_release]
        if url == f"{updator.GITHUB_RELEASE_API}/tags/{updator.NIGHTLY_TAG}":
            return [github_nightly_release]
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    releases = await updator.get_releases_with_nightly()

    nightly_releases = [item for item in releases if item["tag_name"] == "nightly"]
    assert len(nightly_releases) == 1
    assert releases[0]["zipball_url"] == "https://example.com/stable-nightly.zip"


@pytest.mark.asyncio
async def test_get_releases_returns_stable_only(monkeypatch):
    updator = AstrBotUpdator()
    stable_release = {
        "version": "v9.9.9",
        "published_at": "2026-03-01T00:00:00Z",
        "body": "stable",
        "tag_name": "v9.9.9",
        "zipball_url": "https://example.com/stable.zip",
    }

    async def mock_fetch_release_info(url: str):
        if url == updator.ASTRBOT_RELEASE_API:
            return [stable_release]
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    releases = await updator.get_releases()
    assert len(releases) == 1
    assert releases[0]["tag_name"] == "v9.9.9"


@pytest.mark.asyncio
async def test_resolve_update_target_skips_prerelease_tags_for_latest(monkeypatch):
    updator = AstrBotUpdator()
    releases = [
        {
            "version": "v9.9.9-rc1",
            "published_at": "2026-03-02T00:00:00Z",
            "body": "rc",
            "tag_name": "v9.9.9-rc1",
            "zipball_url": "https://example.com/rc.zip",
        },
        {
            "version": "v9.9.8",
            "published_at": "2026-03-01T00:00:00Z",
            "body": "stable",
            "tag_name": "v9.9.8",
            "zipball_url": "https://example.com/stable.zip",
        },
    ]

    async def mock_get_releases():
        return releases

    monkeypatch.setattr(updator, "get_releases", mock_get_releases)
    monkeypatch.setattr(updator, "compare_version", lambda _current, _target: -1)

    target_version, file_url = await updator._resolve_update_target(
        latest=True,
        version=None,
    )
    assert target_version == "v9.9.8"
    assert file_url == "https://example.com/stable.zip"


@pytest.mark.asyncio
async def test_resolve_update_target_rejects_version_when_latest_true():
    updator = AstrBotUpdator()

    with pytest.raises(
        AstrBotUpdateError,
        match="latest=True 时不能同时指定 version，请将 latest 设为 False。",
    ):
        await updator._resolve_update_target(
            latest=True,
            version="nightly",
        )


@pytest.mark.asyncio
async def test_get_releases_with_nightly_skips_expected_nightly_fetch_error(monkeypatch):
    updator = AstrBotUpdator()
    stable_release = {
        "version": "v9.9.9",
        "published_at": "2026-03-01T00:00:00Z",
        "body": "stable",
        "tag_name": "v9.9.9",
        "zipball_url": "https://example.com/stable.zip",
    }

    async def mock_fetch_release_info(url: str):
        if url == updator.ASTRBOT_RELEASE_API:
            return [stable_release]
        if url == f"{updator.GITHUB_RELEASE_API}/tags/{updator.NIGHTLY_TAG}":
            raise FetchReleaseError("请求失败，状态码: 404")
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    releases = await updator.get_releases_with_nightly()
    assert len(releases) == 1
    assert releases[0]["tag_name"] == "v9.9.9"


@pytest.mark.asyncio
async def test_get_releases_with_nightly_raises_for_unexpected_nightly_error(
    monkeypatch,
):
    updator = AstrBotUpdator()
    stable_release = {
        "version": "v9.9.9",
        "published_at": "2026-03-01T00:00:00Z",
        "body": "stable",
        "tag_name": "v9.9.9",
        "zipball_url": "https://example.com/stable.zip",
    }

    async def mock_fetch_release_info(url: str):
        if url == updator.ASTRBOT_RELEASE_API:
            return [stable_release]
        if url == f"{updator.GITHUB_RELEASE_API}/tags/{updator.NIGHTLY_TAG}":
            raise KeyError("unexpected")
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(updator, "fetch_release_info", mock_fetch_release_info)

    with pytest.raises(KeyError):
        await updator.get_releases_with_nightly()


@pytest.mark.asyncio
async def test_check_update_skips_nightly_when_prerelease_disabled(monkeypatch):
    updator = RepoZipUpdator()

    async def mock_fetch_release_info(url: str):
        _ = url
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

    async def mock_fetch_release_info(url: str):
        _ = url
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
