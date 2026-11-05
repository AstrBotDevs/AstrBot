import importlib.metadata
from types import SimpleNamespace

import pytest

from astrbot.core.agent import mcp_client


@pytest.mark.asyncio
async def test_connect_to_server_rejects_unsupported_mcp_major(monkeypatch):
    """An mcp 2.x install must report the real reason, not per-server timeouts.

    The stdio command below is denied by validation, so reaching RuntimeError
    proves the version guard runs before any connection attempt.
    """
    monkeypatch.setattr(
        mcp_client,
        "importlib_metadata",
        SimpleNamespace(
            version=lambda _name: "2.3.0",
            PackageNotFoundError=importlib.metadata.PackageNotFoundError,
        ),
    )
    client = mcp_client.MCPClient()

    with pytest.raises(RuntimeError, match=r"mcp 2\.3\.0"):
        await client.connect_to_server({"command": "bash"}, "demo_server")

    assert client._connection_task is None


@pytest.mark.asyncio
async def test_connect_to_server_accepts_supported_mcp_1x(monkeypatch):
    """The guard must not reject the supported mcp 1.x line."""
    monkeypatch.setattr(
        mcp_client,
        "importlib_metadata",
        SimpleNamespace(
            version=lambda _name: "1.30.0",
            PackageNotFoundError=importlib.metadata.PackageNotFoundError,
        ),
    )
    client = mcp_client.MCPClient()

    # A denied stdio command fails validation inside the connection path, which
    # proves the version guard let the connection attempt through.
    with pytest.raises(ValueError, match="not allowed"):
        await client.connect_to_server({"command": "bash"}, "demo_server")

    await client.cleanup()
    assert client._connection_task is None
