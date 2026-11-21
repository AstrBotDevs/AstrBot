"""External plugin Runners over WebSocket: token routing and redial restart."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import pytest
import websockets
from astrbot_sdk.capabilities import CapabilitySet
from astrbot_sdk.runtime.env import runner_env
from astrbot_sdk.runtime.ws_runner import RUNNER_TOKEN_ENV

from astrbot.core.star.sdk_bridge.supervisor import (
    ExternalRunnerSupervisor,
    SupervisorTiming,
)
from astrbot.core.star.sdk_bridge.ws_listener import ExternalRunnerListener
from tests.unit.test_sdk_bridge_supervisor import (
    make_event,
    no_capabilities,
    wait_for_client,
    write_legacy_plugin,
)


async def spawn_ws_runner(plugin_root: Path, url: str, token: str):
    """Spawn one legacy Runner process dialed into the test listener."""
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "astrbot_sdk.runtime",
        "--ws",
        url,
        "--legacy",
        "--plugin-root",
        str(plugin_root),
        env=runner_env({RUNNER_TOKEN_ENV: token}),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


@pytest.mark.asyncio
async def test_listener_routes_connections_by_token() -> None:
    listener = ExternalRunnerListener("127.0.0.1", 0)
    await listener.start()
    url = f"ws://127.0.0.1:{listener.port}"
    try:
        claims_a = listener.register("token-a")
        listener.register("token-b")
        with pytest.raises(ValueError, match="duplicate"):
            listener.register("token-a")

        # Unknown tokens are rejected during the HTTP upgrade.
        with pytest.raises(websockets.exceptions.InvalidStatus) as exc_info:
            async with websockets.connect(
                url,
                additional_headers={"Authorization": "Bearer nope"},
                proxy=None,
            ):
                pass
        assert exc_info.value.response.status_code == 401

        # A registered token connects and lands in its own claim queue.
        async with websockets.connect(
            url,
            additional_headers={"Authorization": "Bearer token-a"},
            proxy=None,
        ):
            transport = await asyncio.wait_for(claims_a.get(), timeout=5)
            assert not transport.closed
        # The owner observes the peer's close without running a read loop.
        await asyncio.wait_for(transport.wait_closed(), timeout=5)
        assert transport.closed

        # After unregister the same token is rejected again.
        listener.unregister("token-a")
        with pytest.raises(websockets.exceptions.InvalidStatus):
            async with websockets.connect(
                url,
                additional_headers={"Authorization": "Bearer token-a"},
                proxy=None,
            ):
                pass
    finally:
        await listener.stop()


@pytest.mark.asyncio
async def test_external_supervisor_waits_for_redial(tmp_path: Path) -> None:
    plugin_root = tmp_path / "ext_legacy"
    write_legacy_plugin(
        plugin_root,
        """
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class ExtPlugin(Star):
    @filter.command("ok")
    async def ok(self, event: AstrMessageEvent):
        yield event.plain_result("fine")
""",
    )
    listener = ExternalRunnerListener("127.0.0.1", 0)
    await listener.start()
    url = f"ws://127.0.0.1:{listener.port}"
    claims = listener.register("token-1")
    supervisor = ExternalRunnerSupervisor(
        "ext_legacy",
        claims=claims,
        legacy=True,
        grants=CapabilitySet.from_ids("storage.kv", "assets.transfer", "message.send"),
        config=None,
        capability_handler=no_capabilities,
        logger=logging.getLogger("test.external_supervisor"),
        timing=SupervisorTiming(base_backoff=0.05, max_backoff=0.1),
    )
    process = await spawn_ws_runner(plugin_root, url, "token-1")
    try:
        handshake = await supervisor.start()
        assert handshake.name == "ext_legacy"
        first_client = supervisor.require_client()
        results = [r async for r in first_client.invoke("ok", make_event())]
        assert [r.message.text for r in results if r is not None] == ["fine"]

        # The runner dies; instead of respawning, the supervisor backs off
        # and waits for the operator's runner to dial back in.
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=10)
        process = await spawn_ws_runner(plugin_root, url, "token-1")
        await wait_for_client(supervisor, old_client=first_client)
        restarted = supervisor.require_client()
        assert restarted is not first_client
        results = [r async for r in restarted.invoke("ok", make_event())]
        assert [r.message.text for r in results if r is not None] == ["fine"]
    finally:
        await supervisor.stop()
        await listener.stop()
        if process.returncode is None:
            process.terminate()
            await process.wait()
