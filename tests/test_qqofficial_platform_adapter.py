import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialGatewayUnavailableError,
    QQOfficialPlatformAdapter,
)


def _platform_config() -> dict:
    return {
        "id": "qq-official-test",
        "appid": "appid",
        "secret": "secret",
        "enable_group_c2c": True,
        "enable_guild_direct_message": True,
    }


@pytest.mark.asyncio
async def test_qqofficial_run_retries_after_gateway_timeout(monkeypatch):
    first_client = SimpleNamespace(
        start=AsyncMock(
            side_effect=QQOfficialGatewayUnavailableError(
                "gateway metadata unavailable during qq_official startup"
            )
        ),
        close=AsyncMock(),
    )
    adapter_holder: dict[str, QQOfficialPlatformAdapter] = {}

    async def second_start(*args, **kwargs):
        adapter_holder["adapter"]._shutdown_event.set()
        return None

    second_client = SimpleNamespace(
        start=AsyncMock(side_effect=second_start),
        close=AsyncMock(),
    )
    clients = iter([first_client, second_client])
    monkeypatch.setattr(
        QQOfficialPlatformAdapter,
        "_create_client",
        lambda self: next(clients),
    )

    adapter = QQOfficialPlatformAdapter(_platform_config(), {}, asyncio.Queue())
    adapter_holder["adapter"] = adapter
    adapter.STARTUP_RETRY_DELAY_SECONDS = 0

    await adapter.run()

    first_client.start.assert_awaited_once_with(appid="appid", secret="secret")
    first_client.close.assert_awaited_once()
    second_client.start.assert_awaited_once_with(appid="appid", secret="secret")
    second_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_qqofficial_run_reraises_non_retryable_error(monkeypatch):
    client = SimpleNamespace(
        start=AsyncMock(side_effect=ValueError("invalid credentials")),
        close=AsyncMock(),
    )
    monkeypatch.setattr(
        QQOfficialPlatformAdapter,
        "_create_client",
        lambda self: client,
    )

    adapter = QQOfficialPlatformAdapter(_platform_config(), {}, asyncio.Queue())

    with pytest.raises(ValueError, match="invalid credentials"):
        await adapter.run()

    client.start.assert_awaited_once_with(appid="appid", secret="secret")
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_qqofficial_bot_login_raises_gateway_error_when_metadata_missing():
    adapter = QQOfficialPlatformAdapter(_platform_config(), {}, asyncio.Queue())
    adapter.client.http = SimpleNamespace(login=AsyncMock(return_value=SimpleNamespace()))
    adapter.client.api = SimpleNamespace(get_ws_url=AsyncMock(return_value=None))

    with pytest.raises(
        QQOfficialGatewayUnavailableError,
        match="gateway metadata unavailable",
    ):
        await adapter.client._bot_login(SimpleNamespace())

    await adapter.terminate()


@pytest.mark.asyncio
async def test_qqofficial_run_propagates_cancelled_error(monkeypatch):
    client = SimpleNamespace(
        start=AsyncMock(side_effect=asyncio.CancelledError()),
        close=AsyncMock(),
    )
    monkeypatch.setattr(
        QQOfficialPlatformAdapter,
        "_create_client",
        lambda self: client,
    )

    adapter = QQOfficialPlatformAdapter(_platform_config(), {}, asyncio.Queue())

    with pytest.raises(asyncio.CancelledError):
        await adapter.run()

    client.close.assert_awaited_once()
