from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.misskey.misskey_api import MisskeyAPI


@pytest.mark.asyncio
async def test_download_file_bytes_does_not_retry_insecure_when_disabled():
    api = MisskeyAPI(
        "https://misskey.example",
        "token",
        allow_insecure_downloads=False,
    )
    api._download_with_existing_session = AsyncMock(
        side_effect=RuntimeError("ssl failed")
    )
    api._download_with_temp_session = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="ssl failed"):
        await api._download_file_bytes("https://files.example/test.png")

    api._download_with_existing_session.assert_awaited_once_with(
        "https://files.example/test.png",
        ssl_verify=True,
    )


@pytest.mark.asyncio
async def test_download_file_bytes_never_retries_insecure_when_enabled():
    api = MisskeyAPI(
        "https://misskey.example",
        "token",
        allow_insecure_downloads=True,
    )
    api._download_with_existing_session = AsyncMock(
        side_effect=RuntimeError("ssl failed")
    )
    api._download_with_temp_session = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="ssl failed"):
        await api._download_file_bytes("https://files.example/test.png")

    api._download_with_existing_session.assert_awaited_once_with(
        "https://files.example/test.png",
        ssl_verify=True,
    )
    api._download_with_temp_session.assert_not_awaited()
