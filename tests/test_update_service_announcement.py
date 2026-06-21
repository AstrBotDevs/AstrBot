"""Tests for UpdateService.get_announcement.

Covers the announcement proxy logic that delegates the upstream update server's
``/announcement`` endpoint to the dashboard frontend via
``/api/system/announcement``. Status code semantics are intentionally preserved
end-to-end so the frontend can distinguish "no announcement" (404) from
"upstream error" (502).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from astrbot.dashboard.services.update_service import (
    UpdateService,
    UpdateServiceError,
)


def _make_service() -> UpdateService:
    """Build a bare UpdateService with stub dependencies for unit tests.

    The announcement flow only touches ``self`` as a namespace; every external
    dependency is patched at the call site, so we can leave the constructor
    arguments as simple sentinels.
    """
    return UpdateService(
        astrbot_updator=MagicMock(),
        core_lifecycle=MagicMock(),
        download_dashboard_func=AsyncMock(),
        extract_dashboard_func=MagicMock(),
        get_dashboard_version_func=AsyncMock(return_value=None),
        pip_install_func=AsyncMock(),
        demo_mode=False,
        clear_site_data_headers={},
    )


def _mock_session_with_response(
    *,
    status: int,
    json_payload=None,
    text_payload: str = "",
) -> MagicMock:
    """Build a mock aiohttp.ClientSession whose ``get()`` returns the given response."""
    response_cm = MagicMock()
    response_cm.status = status
    if json_payload is not None:
        response_cm.json = AsyncMock(return_value=json_payload)
    if text_payload:
        response_cm.text = AsyncMock(return_value=text_payload)
    response_cm.__aenter__ = AsyncMock(return_value=response_cm)
    response_cm.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.get = MagicMock(return_value=response_cm)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


class _FakeClientSessionCM:
    """Async context manager wrapper that yields the given session mock."""

    def __init__(self, session: MagicMock) -> None:
        self._session = session

    async def __aenter__(self) -> MagicMock:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def test_resolve_announcement_url_derives_from_core_release_api() -> None:
    """Upstream URL = scheme + netloc of release_api_url + ``/announcement``."""
    with patch(
        "astrbot.dashboard.services.update_service.UpdateConfig"
    ) as mock_config_cls:
        mock_config_cls.return_value.get_core_release_api_url.return_value = (
            "https://api.soulter.top/releases"
        )
        url = UpdateService._resolve_announcement_url()
    assert url == "https://api.soulter.top/announcement"


def test_resolve_announcement_url_strips_subpath_from_release_api() -> None:
    """Any trailing path on release_api_url is dropped before ``/announcement`` is appended."""
    with patch(
        "astrbot.dashboard.services.update_service.UpdateConfig"
    ) as mock_config_cls:
        mock_config_cls.return_value.get_core_release_api_url.return_value = (
            "http://internal:8080/api/v2/releases/latest"
        )
        url = UpdateService._resolve_announcement_url()
    assert url == "http://internal:8080/announcement"


def test_resolve_announcement_url_returns_none_when_url_invalid() -> None:
    """A release_api_url without scheme/netloc is rejected (no upstream call)."""
    with patch(
        "astrbot.dashboard.services.update_service.UpdateConfig"
    ) as mock_config_cls:
        mock_config_cls.return_value.get_core_release_api_url.return_value = "garbage"
        assert UpdateService._resolve_announcement_url() is None


@pytest.mark.asyncio
async def test_get_announcement_returns_payload_on_200() -> None:
    """A 200 with a JSON body is returned as a success result carrying the payload."""
    service = _make_service()
    session = _mock_session_with_response(
        status=200,
        json_payload={"title": "Hi", "content": "body", "enabled": True, "version": 1},
    )
    with (
        patch(
            "astrbot.dashboard.services.update_service.UpdateConfig"
        ) as mock_config_cls,
        patch(
            "astrbot.dashboard.services.update_service.aiohttp.ClientSession",
            return_value=_FakeClientSessionCM(session),
        ),
    ):
        mock_config_cls.return_value.get_core_release_api_url.return_value = (
            "https://api.soulter.top/releases"
        )
        result = await service.get_announcement()

    assert result.status == "success"
    assert result.data == {
        "title": "Hi",
        "content": "body",
        "enabled": True,
        "version": 1,
    }


@pytest.mark.asyncio
async def test_get_announcement_raises_on_404() -> None:
    """A 404 from upstream is mapped to ``当前没有公告`` so the frontend hides the bar."""
    service = _make_service()
    session = _mock_session_with_response(status=404)
    with (
        patch(
            "astrbot.dashboard.services.update_service.UpdateConfig"
        ) as mock_config_cls,
        patch(
            "astrbot.dashboard.services.update_service.aiohttp.ClientSession",
            return_value=_FakeClientSessionCM(session),
        ),
    ):
        mock_config_cls.return_value.get_core_release_api_url.return_value = (
            "https://api.soulter.top/releases"
        )
        with pytest.raises(UpdateServiceError, match="当前没有公告"):
            await service.get_announcement()


@pytest.mark.asyncio
async def test_get_announcement_raises_on_5xx() -> None:
    """A 5xx upstream response is reported as an upstream HTTP error."""
    service = _make_service()
    session = _mock_session_with_response(status=503, text_payload="down")
    with (
        patch(
            "astrbot.dashboard.services.update_service.UpdateConfig"
        ) as mock_config_cls,
        patch(
            "astrbot.dashboard.services.update_service.aiohttp.ClientSession",
            return_value=_FakeClientSessionCM(session),
        ),
    ):
        mock_config_cls.return_value.get_core_release_api_url.return_value = (
            "https://api.soulter.top/releases"
        )
        with pytest.raises(UpdateServiceError, match="HTTP 503"):
            await service.get_announcement()


@pytest.mark.asyncio
async def test_get_announcement_raises_on_network_error() -> None:
    """A connection failure surfaces as UpdateServiceError (no raw aiohttp leak)."""
    service = _make_service()

    failing_session = MagicMock()
    failing_session.get = MagicMock(
        side_effect=aiohttp.ClientConnectionError("dns failed")
    )
    failing_session.__aenter__ = AsyncMock(return_value=failing_session)
    failing_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "astrbot.dashboard.services.update_service.UpdateConfig"
        ) as mock_config_cls,
        patch(
            "astrbot.dashboard.services.update_service.aiohttp.ClientSession",
            return_value=_FakeClientSessionCM(failing_session),
        ),
    ):
        mock_config_cls.return_value.get_core_release_api_url.return_value = (
            "https://api.soulter.top/releases"
        )
        with pytest.raises(UpdateServiceError, match="无法连接更新服务器"):
            await service.get_announcement()


@pytest.mark.asyncio
async def test_get_announcement_raises_on_unconfigured_url() -> None:
    """If the release_api_url is missing/invalid, raise before any network call."""
    service = _make_service()
    with patch(
        "astrbot.dashboard.services.update_service.UpdateConfig"
    ) as mock_config_cls:
        mock_config_cls.return_value.get_core_release_api_url.return_value = "garbage"
        with pytest.raises(UpdateServiceError, match="未配置或格式不合法"):
            await service.get_announcement()
