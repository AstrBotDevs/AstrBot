from __future__ import annotations

from typing import Protocol


class LocalMCPBackendContract(Protocol):
    async def get_server(self, name: str): ...

    async def list_servers(self): ...

    async def enable_server(self, name: str): ...

    async def disable_server(self, name: str): ...

    async def wait_until_ready(self, name: str, *, timeout: float): ...


async def exercise_local_mcp_contract(
    backend: LocalMCPBackendContract,
) -> None:
    """Exercise the minimum local MCP behavior expected by SDK tests.

    The caller is expected to provision a local server named ``demo`` before
    invoking this helper. Keeping the contract in-repo prevents the SDK test
    suite from depending on AstrBot's external test tree.
    """

    server = await backend.get_server("demo")
    assert server is not None
    assert server.name == "demo"
    assert server.scope.value == "local"
    assert server.active is True
    assert server.running is True

    servers = await backend.list_servers()
    assert [item.name for item in servers] == ["demo"]

    disabled = await backend.disable_server("demo")
    assert disabled.name == "demo"
    assert disabled.scope.value == "local"
    assert disabled.active is False
    assert disabled.running is False

    disabled_snapshot = await backend.get_server("demo")
    assert disabled_snapshot is not None
    assert disabled_snapshot.active is False
    assert disabled_snapshot.running is False

    enabled = await backend.enable_server("demo")
    assert enabled.name == "demo"
    assert enabled.scope.value == "local"
    assert enabled.active is True
    assert enabled.running is True
    assert enabled.tools == ["lookup"]

    ready = await backend.wait_until_ready("demo", timeout=0.1)
    assert ready.name == "demo"
    assert ready.scope.value == "local"
    assert ready.active is True
    assert ready.running is True
    assert ready.tools == ["lookup"]
