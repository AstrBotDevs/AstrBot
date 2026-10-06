"""Runner supervision: crash restarts, backoff, circuit breaking, liveness.

The supervisor owns the StdioPluginClient lifecycle for one isolated
plugin. Unexpected exits trigger a restart with exponential backoff; a
crash storm opens the circuit and marks the plugin failed instead of
retrying forever. A periodic protocol ping kills unresponsive runners so
they go through the same crash path. Deliberate stops never restart.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astrbot_sdk.capabilities import CapabilitySet
from astrbot_sdk.errors import HostUnavailable
from astrbot_sdk.runtime.stdio_client import StdioPluginClient
from astrbot_sdk.runtime.transport import WebSocketTransport
from astrbot_sdk.runtime.ws_client import WSPluginClient

from astrbot import __version__ as _ASTRBOT_VERSION


class CircuitOpenError(RuntimeError):
    """The runner crashed too often; invocations fail fast until reload."""


@dataclass(frozen=True, slots=True)
class SupervisorTiming:
    """Tunable supervisor constants (overridable in tests)."""

    window_seconds: float = 60.0
    max_crashes: int = 5
    stable_seconds: float = 60.0
    base_backoff: float = 1.0
    max_backoff: float = 30.0
    ping_interval: float = 15.0
    ping_timeout: float = 5.0
    ping_max_misses: int = 3


class RunnerSupervisor:
    """Own one plugin Runner's process lifecycle."""

    def __init__(
        self,
        plugin_root: Path,
        *,
        legacy: bool,
        python_executable: Path | str | None,
        env: Mapping[str, str],
        grants: CapabilitySet,
        config: Any,
        capability_handler: Any,
        logger: logging.Logger,
        on_circuit_open: Callable[[], None] | None = None,
        timing: SupervisorTiming | None = None,
        host_info: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the supervisor for one plugin.

        Args:
            plugin_root: Plugin directory the runner loads.
            legacy: Load through the legacy compat layer.
            python_executable: Plugin venv python, or None for the core one.
            env: Extra environment for the runner (over the whitelist).
            grants: Capability grants passed to every start.
            config: Plugin config passed to every start.
            capability_handler: Runner-to-Host capability dispatcher.
            logger: Logger for lifecycle events.
            on_circuit_open: Called once when the circuit opens.
            timing: Optional timing overrides.
            host_info: Extra metadata shipped in the initialize handshake.
        """
        self.plugin_root = plugin_root
        self.legacy = legacy
        self.host_info = dict(host_info or {})
        self.python_executable = python_executable
        self.env = dict(env)
        self.grants = grants
        self.config = config
        self.capability_handler = capability_handler
        self.logger = logger
        self.on_circuit_open = on_circuit_open
        self.timing = timing or SupervisorTiming()
        self._client: StdioPluginClient | None = None
        self._stopping = False
        self._failed = False
        self._started_at = 0.0
        self._consecutive = 0
        self._crashes: list[float] = []
        self._lifecycle_task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None

    @property
    def failed(self) -> bool:
        """Whether the circuit is open."""
        return self._failed

    async def _make_client(self) -> StdioPluginClient:
        """Create the next client; external supervisors await a redial here."""
        return StdioPluginClient(
            self.plugin_root,
            python_executable=self.python_executable,
            capability_handler=self.capability_handler,
            logger=self.logger,
            legacy=self.legacy,
            env=self.env,
            start_timeout=60.0,
        )

    async def start(self) -> Any:
        """Start the runner and return its handshake.

        First-start failures propagate (the plugin fails to load); only
        restarts after a successful first start are supervised.
        """
        self._client = await self._make_client()
        self._started_at = time.monotonic()
        handshake = await self._client.start(
            granted_capabilities=self.grants,
            config=self.config,
            host_info={"version": _ASTRBOT_VERSION, **self.host_info},
        )
        self._lifecycle_task = asyncio.create_task(self._lifecycle())
        self._health_task = asyncio.create_task(self._health_loop())
        return handshake

    async def stop(self) -> None:
        """Stop the runner deliberately; no restart is scheduled."""
        self._stopping = True
        for task in (self._lifecycle_task, self._health_task):
            if task is not None:
                task.cancel()
        for task in (self._lifecycle_task, self._health_task):
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
        self._lifecycle_task = None
        self._health_task = None
        if self._client is not None:
            await self._client.close()
            self._client = None

    def require_client(self) -> StdioPluginClient:
        """Return the running client or fail the invocation fast."""
        if self._failed:
            raise CircuitOpenError(
                f"plugin runner for {self.plugin_root.name} is unavailable: "
                "circuit opened after repeated crashes"
            )
        if self._client is None or not self._client.is_running:
            raise HostUnavailable(
                f"plugin runner for {self.plugin_root.name} is restarting"
            )
        return self._client

    def _register_crash(self) -> bool:
        """Record one crash; returns False when the circuit should open."""
        now = time.monotonic()
        if now - self._started_at >= self.timing.stable_seconds:
            self._consecutive = 0
        self._consecutive += 1
        self._crashes = [
            stamp for stamp in self._crashes if now - stamp < self.timing.window_seconds
        ]
        self._crashes.append(now)
        return len(self._crashes) < self.timing.max_crashes

    async def _lifecycle(self) -> None:
        """Watch the runner and restart it after unexpected exits."""
        while not self._stopping:
            client = self._client
            code = await client.wait_exited() if client is not None else None
            if self._stopping or self._client is not client:
                return
            self._client = None
            if code is not None:
                self.logger.warning(
                    f"Plugin runner for {self.plugin_root.name} exited "
                    f"unexpectedly (code={code})",
                )
            if not self._register_crash():
                self._failed = True
                self.logger.error(
                    f"Plugin runner for {self.plugin_root.name} crashed "
                    f"{self.timing.max_crashes} times within "
                    f"{self.timing.window_seconds:.0f}s; circuit opened",
                )
                if self.on_circuit_open is not None:
                    self.on_circuit_open()
                return
            delay = min(
                self.timing.max_backoff,
                self.timing.base_backoff * (2 ** (self._consecutive - 1)),
            )
            delay *= 0.5 + random.random() * 0.5
            self.logger.info(
                f"Restarting plugin runner for {self.plugin_root.name} "
                f"in {delay:.1f}s (attempt {self._consecutive})",
            )
            await asyncio.sleep(delay)
            if self._stopping:
                return
            client = await self._make_client()
            try:
                self._started_at = time.monotonic()
                await client.start(
                    granted_capabilities=self.grants,
                    config=self.config,
                )
            except Exception as exc:  # noqa: BLE001 - any start failure counts
                self.logger.error(
                    f"Plugin runner for {self.plugin_root.name} failed to "
                    f"restart: {exc}",
                )
                await client.close()
                # The next loop iteration registers this failed attempt.
                self._client = None
                continue
            self._client = client
            self.logger.info(
                f"Plugin runner for {self.plugin_root.name} restarted",
            )

    async def _health_loop(self) -> None:
        """Kill runners that stop answering protocol pings."""
        misses = 0
        while not self._stopping:
            await asyncio.sleep(self.timing.ping_interval)
            client = self._client
            if client is None or self._stopping or self._failed:
                continue
            try:
                await asyncio.wait_for(
                    client.ping(),
                    timeout=self.timing.ping_timeout,
                )
                misses = 0
            except Exception:  # noqa: BLE001 - any ping failure is a miss
                misses += 1
                if misses >= self.timing.ping_max_misses:
                    self.logger.error(
                        f"Plugin runner for {self.plugin_root.name} is "
                        "unresponsive; killing it",
                    )
                    client.kill_process()
                    misses = 0


class ExternalRunnerSupervisor(RunnerSupervisor):
    """Supervise one externally spawned Runner connected over WebSocket.

    The Runner process lifecycle belongs to the operator (systemd, Docker,
    a remote machine). After a disconnect the supervisor backs off and
    waits for the Runner to redial instead of respawning anything.
    """

    def __init__(
        self,
        name: str,
        *,
        claims: asyncio.Queue[WebSocketTransport],
        legacy: bool,
        grants: CapabilitySet,
        config: Any,
        capability_handler: Any,
        logger: logging.Logger,
        on_circuit_open: Callable[[], None] | None = None,
        timing: SupervisorTiming | None = None,
        host_info: Mapping[str, Any] | None = None,
    ) -> None:
        """Initialize the supervisor for one external plugin slot.

        Args:
            name: External plugin name used in logs and registry paths.
            claims: Queue yielding accepted transports for this slot.
            legacy: Load through the legacy compat layer.
            grants: Capability grants passed to every start.
            config: Plugin config passed to every start.
            capability_handler: Runner-to-Host capability dispatcher.
            logger: Logger for lifecycle events.
            on_circuit_open: Called once when the circuit opens.
            timing: Optional timing overrides.
            host_info: Extra metadata shipped in the initialize handshake.
        """
        super().__init__(
            Path(name),
            legacy=legacy,
            python_executable=None,
            env={},
            grants=grants,
            config=config,
            capability_handler=capability_handler,
            logger=logger,
            on_circuit_open=on_circuit_open,
            timing=timing,
            host_info=host_info,
        )
        self._claims = claims

    async def _make_client(self) -> WSPluginClient:
        """Wait for the Runner to dial in and wrap its connection."""
        transport = await self._claims.get()
        return WSPluginClient(
            transport,
            capability_handler=self.capability_handler,
            logger=self.logger,
            legacy=self.legacy,
            start_timeout=60.0,
        )
