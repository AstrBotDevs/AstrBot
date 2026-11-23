"""Shared Python cwd compatibility at the real Shipyard SDK boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from shipyard import ShipyardClient
from shipyard.python import PythonComponent as ShipyardPythonComponent

from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
    ShipyardBooter,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [{}, {"kernel_id": "existing-kernel", "timeout": 12, "silent": True}],
)
async def test_shipyard_python_adapter_uses_actual_sdk_signature(
    monkeypatch: pytest.MonkeyPatch, options: dict[str, object]
) -> None:
    client = ShipyardClient(endpoint_url="http://localhost:8123", access_token="test")
    execute = AsyncMock(return_value={"output": "2"})
    monkeypatch.setattr(client, "_exec_operation", execute)
    booter = ShipyardBooter.__new__(ShipyardBooter)
    booter._ship = SimpleNamespace(
        python=ShipyardPythonComponent(client, "ship", "session")
    )
    python = booter.python
    assert await python.exec("1 + 1", cwd=None, **options) == {"output": "2"}
    execute.assert_awaited_once_with(
        "ship",
        "ipython/exec",
        {"code": "1 + 1", "kernel_id": None, "timeout": 30, "silent": False, **options},
        "session",
    )
    with pytest.raises(NotImplementedError, match="cwd"):
        await python.exec("1 + 1", cwd="/workspace")
    assert execute.await_count == 1
