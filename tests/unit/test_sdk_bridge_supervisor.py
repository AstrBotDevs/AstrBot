from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from astrbot_sdk.capabilities import CapabilityGrant, CapabilitySet
from astrbot_sdk.errors import HostUnavailable, RemotePluginError
from astrbot_sdk.events import (
    UMO,
    MessageEvent,
    MessageRef,
    MessageType,
    Sender,
)
from astrbot_sdk.message_components import Plain
from astrbot_sdk.messages import MessageChain

from astrbot.core.star.sdk_bridge.supervisor import (
    CircuitOpenError,
    RunnerSupervisor,
    SupervisorTiming,
)


def write_legacy_plugin(plugin_root: Path, main_py: str) -> None:
    plugin_root.mkdir()
    (plugin_root / "metadata.yaml").write_text(
        yaml.safe_dump(
            {
                "name": plugin_root.name,
                "desc": "supervisor test plugin",
                "author": "AstrBot",
                "version": "1.0.0",
            },
        ),
        "utf-8",
    )
    (plugin_root / "main.py").write_text(main_py, "utf-8")


def make_event(text: str = "ok") -> MessageEvent:
    return MessageEvent(
        id="event-1",
        umo=UMO("platform-1", MessageType.PRIVATE, "user-1"),
        platform_type="webchat",
        message_ref=MessageRef("message-1"),
        message=MessageChain(Plain(text)),
        sender=Sender("user-1", "Moon"),
        timestamp=datetime.now(UTC),
    )


async def no_capabilities(
    grant: CapabilityGrant,
    operation: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    raise AssertionError(f"unexpected capability call: {grant.id} {operation}")


def make_supervisor(
    plugin_root: Path,
    *,
    timing: SupervisorTiming | None = None,
    on_circuit_open: Any = None,
) -> RunnerSupervisor:
    return RunnerSupervisor(
        plugin_root,
        legacy=True,
        python_executable=Path(sys.executable),
        env={},
        grants=CapabilitySet.from_ids("storage.kv", "assets.transfer", "message.send"),
        config=None,
        capability_handler=no_capabilities,
        logger=__import__("logging").getLogger("test.supervisor"),
        on_circuit_open=on_circuit_open,
        timing=timing,
    )


async def wait_for_client(
    supervisor: RunnerSupervisor,
    timeout: float = 10.0,
    old_client: Any = None,
) -> None:
    """Wait until the supervisor has a running client again.

    When old_client is given, the wait only completes once the supervisor
    holds a different (restarted) client instance.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            client = supervisor.require_client()
            if old_client is not None and client is old_client:
                await asyncio.sleep(0.05)
                continue
            return
        except HostUnavailable:
            await asyncio.sleep(0.05)
    raise TimeoutError("runner did not come back")


@pytest.mark.asyncio
async def test_crash_restarts_runner(tmp_path: Path) -> None:
    plugin_root = tmp_path / "crasher"
    write_legacy_plugin(
        plugin_root,
        """
import os

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class CrasherPlugin(Star):
    @filter.command("boom")
    async def boom(self, event: AstrMessageEvent):
        os._exit(3)

    @filter.command("ok")
    async def ok(self, event: AstrMessageEvent):
        yield event.plain_result("fine")
""",
    )
    supervisor = make_supervisor(
        plugin_root,
        timing=SupervisorTiming(base_backoff=0.05, stable_seconds=0),
    )
    try:
        await supervisor.start()
        with pytest.raises((RemotePluginError, HostUnavailable)):
            _ = [
                r
                async for r in supervisor.require_client().invoke("boom", make_event())
            ]
        await wait_for_client(supervisor)
        results = [
            r async for r in supervisor.require_client().invoke("ok", make_event())
        ]
        assert [r.message.text for r in results if r is not None] == ["fine"]
    finally:
        await supervisor.stop()
    # Deliberate stop leaves nothing running.
    with pytest.raises(HostUnavailable):
        supervisor.require_client()


@pytest.mark.asyncio
async def test_crash_loop_opens_circuit(tmp_path: Path) -> None:
    marker = tmp_path / "crash.marker"
    plugin_root = tmp_path / "looper"
    write_legacy_plugin(
        plugin_root,
        f"""
import os
import sys

if os.path.exists({str(marker)!r}):
    raise SystemExit(1)

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class LooperPlugin(Star):
    @filter.command("boom")
    async def boom(self, event: AstrMessageEvent):
        open({str(marker)!r}, "w").close()
        os._exit(3)
""",
    )
    opened = asyncio.Event()

    def on_open() -> None:
        opened.set()

    supervisor = make_supervisor(
        plugin_root,
        timing=SupervisorTiming(
            base_backoff=0.01,
            max_backoff=0.02,
            max_crashes=3,
            stable_seconds=0,
        ),
        on_circuit_open=on_open,
    )
    try:
        await supervisor.start()
        with pytest.raises((RemotePluginError, HostUnavailable)):
            _ = [
                r
                async for r in supervisor.require_client().invoke("boom", make_event())
            ]
        await asyncio.wait_for(opened.wait(), timeout=15)
        assert supervisor.failed
        with pytest.raises(CircuitOpenError, match="circuit opened"):
            supervisor.require_client()
    finally:
        await supervisor.stop()


@pytest.mark.asyncio
async def test_unresponsive_runner_is_killed_and_restarted(
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "wedged"
    write_legacy_plugin(
        plugin_root,
        """
import time

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class WedgedPlugin(Star):
    @filter.command("wedge")
    async def wedge(self, event: AstrMessageEvent):
        time.sleep(60)
        yield event.plain_result("unreachable")

    @filter.command("ok")
    async def ok(self, event: AstrMessageEvent):
        yield event.plain_result("fine")
""",
    )
    supervisor = make_supervisor(
        plugin_root,
        timing=SupervisorTiming(
            base_backoff=0.05,
            stable_seconds=0,
            ping_interval=0.1,
            ping_timeout=0.2,
            ping_max_misses=2,
        ),
    )
    try:
        await supervisor.start()
        # Fire the wedging handler without awaiting its stream; the runner
        # blocks its event loop inside time.sleep.
        first_client = supervisor.require_client()
        wedged = asyncio.create_task(
            _collect(first_client.invoke("wedge", make_event())),
        )
        await asyncio.sleep(0.3)
        await wait_for_client(supervisor, timeout=20, old_client=first_client)
        results = [
            r async for r in supervisor.require_client().invoke("ok", make_event())
        ]
        assert [r.message.text for r in results if r is not None] == ["fine"]
        wedged.cancel()
        await asyncio.gather(wedged, return_exceptions=True)
    finally:
        await supervisor.stop()


async def _collect(stream: Any) -> None:
    async for _ in stream:
        pass


@pytest.mark.asyncio
async def test_ping_reports_protocol_version(tmp_path: Path) -> None:
    plugin_root = tmp_path / "pinger"
    write_legacy_plugin(
        plugin_root,
        """
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star


class PingerPlugin(Star):
    @filter.command("ok")
    async def ok(self, event: AstrMessageEvent):
        yield event.plain_result("fine")
""",
    )
    supervisor = make_supervisor(plugin_root)
    try:
        await supervisor.start()
        payload = await supervisor.require_client().ping()
        assert payload["protocol_version"] >= 1
    finally:
        await supervisor.stop()
