from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from shipyard_neo.errors import NotFoundError

from astrbot.core.computer.booters.shipyard_neo import ShipyardNeoBooter


def _make_booter() -> ShipyardNeoBooter:
    return ShipyardNeoBooter(
        endpoint_url="http://bay:8114",
        access_token="test-token",
    )


def _attach_sandbox_references(
    booter: ShipyardNeoBooter,
    sandbox: SimpleNamespace,
) -> tuple[object, object, object, object]:
    components = (object(), object(), object(), object())
    booter._sandbox = sandbox  # type: ignore[assignment]
    booter._fs, booter._python, booter._shell, booter._browser = components  # type: ignore[assignment]
    return components


@pytest.mark.asyncio
async def test_not_found_invalidates_expired_sandbox_references() -> None:
    booter = _make_booter()
    sandbox = SimpleNamespace(
        id="sandbox-expired",
        refresh=AsyncMock(side_effect=NotFoundError("Sandbox not found")),
    )
    _attach_sandbox_references(booter, sandbox)

    with patch("astrbot.core.computer.booters.shipyard_neo.logger") as logger:
        assert await booter.available() is False

    assert booter._sandbox is None
    assert booter._fs is None
    assert booter._python is None
    assert booter._shell is None
    assert booter._browser is None
    logger.info.assert_called_once()
    logger.error.assert_not_called()


@pytest.mark.asyncio
async def test_not_found_does_not_clear_concurrent_replacement() -> None:
    booter = _make_booter()
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    async def _expired_refresh() -> None:
        refresh_started.set()
        await release_refresh.wait()
        raise NotFoundError("Sandbox not found")

    expired = SimpleNamespace(id="sandbox-expired", refresh=_expired_refresh)
    _attach_sandbox_references(booter, expired)

    check_task = asyncio.create_task(booter.available())
    await refresh_started.wait()

    replacement = SimpleNamespace(id="sandbox-replacement")
    replacement_components = _attach_sandbox_references(booter, replacement)
    release_refresh.set()

    assert await check_task is True
    assert booter._sandbox is replacement
    assert (booter._fs, booter._python, booter._shell, booter._browser) == (
        replacement_components
    )


@pytest.mark.asyncio
async def test_non_not_found_error_remains_observable_without_invalidating() -> None:
    booter = _make_booter()
    sandbox = SimpleNamespace(
        id="sandbox-current",
        refresh=AsyncMock(side_effect=RuntimeError("Bay connection lost")),
    )
    components = _attach_sandbox_references(booter, sandbox)

    with patch("astrbot.core.computer.booters.shipyard_neo.logger") as logger:
        assert await booter.available() is False

    assert booter._sandbox is sandbox
    assert (booter._fs, booter._python, booter._shell, booter._browser) == components
    logger.error.assert_called_once()
    assert "Bay connection lost" in str(logger.error.call_args)


@pytest.mark.asyncio
async def test_get_booter_closes_expired_client_and_rebuilds(monkeypatch) -> None:
    from astrbot.core.computer import computer_client

    booter = _make_booter()
    sandbox = SimpleNamespace(
        id="sandbox-expired",
        refresh=AsyncMock(side_effect=NotFoundError("Sandbox not found")),
        delete=AsyncMock(),
    )
    _attach_sandbox_references(booter, sandbox)
    old_client = SimpleNamespace(__aexit__=AsyncMock())
    booter._client = old_client  # type: ignore[assignment]

    session_id = "shipyard-expiry-regression"
    config = {
        "provider_settings": {
            "computer_use_runtime": "sandbox",
            "sandbox": {
                "booter": "shipyard_neo",
                "shipyard_neo_endpoint": "http://bay:8114",
                "shipyard_neo_access_token": "test-token",
                "shipyard_neo_profile": "browser-python",
                "shipyard_neo_ttl": 3600,
            },
        }
    }
    context = SimpleNamespace(get_config=lambda umo=None: config)
    monkeypatch.setitem(computer_client.session_booter, session_id, booter)

    booted_session_ids: list[str] = []

    async def _fake_boot(new_booter: ShipyardNeoBooter, new_session_id: str) -> None:
        booted_session_ids.append(new_session_id)
        replacement = SimpleNamespace(id="sandbox-replacement")
        _attach_sandbox_references(new_booter, replacement)
        new_booter._client = SimpleNamespace(__aexit__=AsyncMock())  # type: ignore[assignment]

    with (
        patch.object(ShipyardNeoBooter, "boot", _fake_boot),
        patch(
            "astrbot.core.computer.computer_client._sync_skills_to_sandbox",
            AsyncMock(),
        ),
    ):
        rebuilt = await computer_client.get_booter(context, session_id)

    sandbox.delete.assert_not_awaited()
    old_client.__aexit__.assert_awaited_once_with(None, None, None)
    assert booter._client is None
    assert rebuilt is computer_client.session_booter[session_id]
    assert rebuilt is not booter
    assert rebuilt.sandbox.id == "sandbox-replacement"
    assert len(booted_session_ids) == 1
