import pytest

from astrbot.core.zip_updator import RepoZipUpdator


class _FakeResponse:
    def __init__(self):
        self.status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return ""

    async def json(self):
        return [
            {
                "name": "v1.0.0",
                "published_at": "2026-03-24T00:00:00Z",
                "body": "release notes",
                "tag_name": "v1.0.0",
                "zipball_url": "https://github.com/AstrBotDevs/AstrBot/archive/v1.0.0.zip",
            }
        ]


class _FakeSession:
    def __init__(self, *, headers=None, **kwargs):
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url):
        return _FakeResponse()


@pytest.mark.asyncio
async def test_fetch_release_info_only_sends_github_token_to_github_api(monkeypatch):
    seen_headers = []

    def _build_session(*args, **kwargs):
        seen_headers.append(kwargs.get("headers", {}))
        return _FakeSession(**kwargs)

    monkeypatch.setattr("astrbot.core.zip_updator.ssl.create_default_context", lambda **kwargs: object())
    monkeypatch.setattr("astrbot.core.zip_updator.aiohttp.TCPConnector", lambda **kwargs: object())
    monkeypatch.setattr("astrbot.core.zip_updator.aiohttp.ClientSession", _build_session)

    updator = RepoZipUpdator(github_token="ghp_test")

    github_releases = await updator.fetch_release_info(
        "https://api.github.com/repos/AstrBotDevs/AstrBot/releases"
    )
    mirror_releases = await updator.fetch_release_info("https://api.soulter.top/releases")

    assert github_releases[0]["tag_name"] == "v1.0.0"
    assert mirror_releases[0]["tag_name"] == "v1.0.0"
    assert seen_headers == [
        {"Authorization": "token ghp_test"},
        {},
    ]
