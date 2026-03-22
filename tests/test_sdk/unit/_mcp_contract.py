from __future__ import annotations


async def exercise_local_mcp_contract(backend) -> None:
    listed = await backend.list_servers()
    assert listed
    first = listed[0]
    assert first.name == "demo"
    assert first.scope.value == "local"

    fetched = await backend.get_server("demo")
    assert fetched is not None
    assert fetched.name == "demo"

    disabled = await backend.disable_server("demo")
    assert disabled.active is False
    assert disabled.running is False

    enabled = await backend.enable_server("demo")
    assert enabled.active is True
    assert enabled.running is True

    ready = await backend.wait_until_ready("demo", timeout=0.2)
    assert ready.running is True
