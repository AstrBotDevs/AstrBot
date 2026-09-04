from __future__ import annotations

import asyncio
import os
import signal as signal_module
import sys
from pathlib import Path

from .base import (
    ProcessSandbox,
    SandboxLimits,
    SandboxProcess,
    SandboxSpec,
    SandboxStdin,
    SandboxStdout,
)


class UnixSandboxProcess:
    """Adapt an asyncio process to process-tree sandbox semantics."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        """Store the session-leading asyncio process.

        Args:
            process: Process started in a new Unix session.
        """
        self._process = process

    @property
    def pid(self) -> int:
        """Return the process-group leader identifier."""
        return self._process.pid

    @property
    def returncode(self) -> int | None:
        """Return the process exit status when available."""
        return self._process.returncode

    @property
    def stdin(self) -> SandboxStdin | None:
        """Return the native asyncio standard-input stream."""
        return self._process.stdin

    @property
    def stdout(self) -> SandboxStdout | None:
        """Return the native asyncio standard-output stream."""
        return self._process.stdout

    async def wait(self) -> int:
        """Wait for the session-leading process to exit."""
        return await self._process.wait()

    def interrupt(self) -> None:
        """Send SIGINT to the complete Unix process group."""
        self._send_signal(signal_module.SIGINT)

    def terminate(self) -> None:
        """Send SIGTERM to the complete Unix process group."""
        self._send_signal(signal_module.SIGTERM)

    def kill(self) -> None:
        """Send SIGKILL to the complete Unix process group."""
        self._send_signal(signal_module.SIGKILL)

    def _send_signal(self, signal: int) -> None:
        """Send a Unix signal to the process group if it still exists.

        Args:
            signal: Unix signal number to send.
        """
        try:
            os.killpg(self.pid, signal)
        except ProcessLookupError:
            pass


class UnixProcessSandbox(ProcessSandbox):
    """Common launcher behavior for Unix sandbox implementations."""

    async def spawn_shell(
        self,
        command: str,
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> SandboxProcess:
        """Start a shell command in a separately managed process group.

        Args:
            command: Shell command to execute inside the sandbox.
            spec: Filesystem, network, and resource policy.
            env: Additional environment variables exposed inside the sandbox.

        Returns:
            Process adapter whose lifecycle methods affect the process group.
        """
        process = await asyncio.create_subprocess_exec(
            *self.build_command(["/bin/sh", "-c", command], spec, env=env),
            cwd=spec.workspace.resolve(),
            env={"PATH": os.defpath},
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        return UnixSandboxProcess(process)


def build_resource_limited_argv(
    argv: list[str],
    limits: SandboxLimits,
) -> list[str]:
    """Wrap a command with Unix resource-limit setup.

    Args:
        argv: Command and arguments to execute after applying limits.
        limits: Resource ceilings requested by the common sandbox policy.

    Returns:
        Python command that applies supported Unix limits and then executes
        ``argv``.
    """
    wrapper_code = f"""
import os
import resource
import sys

limits = [
    (resource.RLIMIT_CPU, {limits.cpu_seconds}),
    (resource.RLIMIT_FSIZE, {limits.file_size_bytes}),
    (resource.RLIMIT_NOFILE, {limits.open_files}),
    (resource.RLIMIT_CORE, 0),
]
if sys.platform.startswith("linux"):
    # macOS RLIMIT_NPROC counts every process owned by the host user, and its
    # Python process starts above this virtual-address limit.
    limits.extend(
        (
            (resource.RLIMIT_NPROC, {limits.processes}),
            (resource.RLIMIT_AS, {limits.memory_bytes}),
        )
    )
for kind, requested in limits:
    _, hard = resource.getrlimit(kind)
    value = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
    resource.setrlimit(kind, (value, value))
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
"""
    return [
        str(Path(sys.executable).resolve()),
        "-I",
        "-S",
        "-c",
        wrapper_code,
        *argv,
    ]
