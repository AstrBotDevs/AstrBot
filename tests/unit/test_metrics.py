"""Tests for anonymous metrics payload privacy."""

from unittest.mock import AsyncMock

import pytest

import astrbot.core.utils.metrics as metrics


class _FakeResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self):
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json, timeout):
        self.post_calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse()


@pytest.mark.asyncio
async def test_post_metrics_omits_installation_identifiers(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(metrics.Metric, "_is_disabled", staticmethod(lambda: False))
    monkeypatch.setattr(
        metrics.aiohttp,
        "ClientSession",
        lambda **kwargs: session,
    )

    await metrics.Metric._post_metrics({"et": "test"})

    payload = session.post_calls[0]["json"]["metrics_data"]
    assert "hn" not in payload
    assert "iid" not in payload
    assert payload["v"]
    assert payload["os"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repo", "expected"),
    [
        (
            "https://user:secret@GitHub.com/org/repo.git?token=secret#fragment",
            "https://github.com/org/repo.git",
        ),
        (
            "git@github.com:org/repo.git",
            "https://github.com/org/repo.git",
        ),
        (
            "ssh://git@github.com/org/repo.git",
            "ssh://github.com/org/repo.git",
        ),
        ("not a repository URL", "<invalid>"),
    ],
)
async def test_upload_sanitizes_repository_url(monkeypatch, repo, expected):
    captured = {}

    async def capture_pending(kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(metrics.Metric, "_is_disabled", staticmethod(lambda: False))
    monkeypatch.setattr(metrics.Metric, "_save_platform_stats", AsyncMock())
    monkeypatch.setattr(metrics.Metric, "_add_pending_metrics", capture_pending)

    await metrics.Metric.upload(et="install_star", repo=repo)

    assert captured["repo"] == expected
