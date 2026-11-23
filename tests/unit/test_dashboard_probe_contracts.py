"""Validate bounded probe downloads and configuration alias precedence."""

from itertools import count
from unittest.mock import Mock

import pytest

from astrbot.dashboard.schemas import BotConfigRequest, ProviderConfigRequest
from astrbot.dashboard.services import stat_service
from astrbot.dashboard.services.stat_service import StatService, StatServiceError


class _Response:
    charset = "utf-8"

    def __init__(self, chunks=(), status=200):
        self.chunks = chunks
        self.status = status
        self.content = self
        self.consumed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def iter_chunked(self, size):
        assert size == 65536
        for chunk in self.chunks:
            self.consumed += 1
            yield chunk


class _Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, **kwargs):
        self.urls.append(url)
        return next(self.responses)


@pytest.mark.asyncio
@pytest.mark.parametrize("pypi", [False, True])
@pytest.mark.parametrize("mode", ["byte_budget", "time_budget", "empty", "error"])
async def test_probe_downloads_keep_byte_time_and_status_boundaries(
    monkeypatch, pypi, mode
):
    body = _Response(
        [] if mode == "empty" else [b"ab", b"cd", b"unused"],
        status=403 if mode == "error" else 200,
    )
    page = _Response([b'<a href="pip-24.0-py3-none-any.whl">pip</a>'])
    session = _Session([page, body] if pypi else [body])
    monkeypatch.setattr(stat_service.aiohttp, "ClientSession", lambda: session)
    ticks = count(100)
    monkeypatch.setattr(stat_service.time, "time", lambda: next(ticks))
    monkeypatch.setattr(stat_service, "_SPEED_SAMPLE_MAX_BYTES", 3)
    monkeypatch.setattr(
        stat_service, "_SPEED_SAMPLE_SECONDS", 0 if mode == "time_budget" else 50
    )
    service = object.__new__(StatService)
    operation = (
        service.measure_pypi_index_speed if pypi else service.measure_ghproxy_speed
    )
    if mode in {"empty", "error"}:
        with pytest.raises(
            StatServiceError,
            match="No data received" if mode == "empty" else "Failed. Status code: 403",
        ):
            await operation("https://example.test/simple")
        assert body.consumed == 0
    else:
        result = await operation("https://example.test/simple")
        assert result["bytes"] == (2 if mode == "time_budget" else 4)
        assert body.consumed == (1 if mode == "time_budget" else 2)
        assert result["duration"] > 0
    if pypi:
        assert session.urls[0] == "https://example.test/simple/pip/"
        assert session.urls[1].endswith("/pip/pip-24.0-py3-none-any.whl")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method", ["test_pypi_index_connection", "measure_pypi_index_speed"]
)
@pytest.mark.parametrize("url", [None, "", "file:///tmp/wheel", "invalid"])
async def test_index_url_validation_precedes_session_creation(monkeypatch, method, url):
    create = Mock()
    monkeypatch.setattr(stat_service.aiohttp, "ClientSession", create)
    service = object.__new__(StatService)
    with pytest.raises(StatServiceError, match="index_url"):
        await getattr(service, method)(url)
    create.assert_not_called()


@pytest.mark.parametrize("model", [BotConfigRequest, ProviderConfigRequest])
@pytest.mark.parametrize(
    "values,expected",
    [
        ({}, True),
        ({"config": {"enable": False}}, False),
        ({"enabled": False, "enable": True, "config": {"enable": True}}, False),
        ({"enable": False, "config": {"enable": True}}, False),
        ({"enabled": True, "enable": False}, True),
    ],
)
def test_config_enabled_aliases_preserve_precedence_and_nested_values(
    model, values, expected
):
    result = model(**values).to_dashboard_config()
    assert result["enable"] is expected
