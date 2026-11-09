from __future__ import annotations

import asyncio
import os
import signal as signal_module
import subprocess
import sys
import tempfile
from abc import abstractmethod
from pathlib import Path

from .base import (
    ProcessSandbox,
    SandboxLimits,
    SandboxProcess,
    SandboxRunResult,
    SandboxSpec,
    SandboxStdin,
    SandboxStdout,
    SandboxTimeoutError,
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

    def build_command(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Build a Unix sandbox wrapper command.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem, network, and resource policy.
            env: Additional environment variables exposed inside the sandbox.

        Returns:
            Platform sandbox command and arguments.
        """
        argv, workspace, env = self._prepare_command(argv, spec, env=env)
        return self._build_command(argv, workspace, spec, env)

    def run(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        output_limit: int | None = None,
        discard_stdout: bool = False,
    ) -> SandboxRunResult:
        """Run a command through the Unix sandbox wrapper.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem, network, and resource policy.
            env: Additional environment variables exposed inside the sandbox.
            timeout: Maximum wall-clock runtime in seconds.
            output_limit: Maximum captured bytes for each output stream.
            discard_stdout: Whether to discard standard output.

        Returns:
            Captured process result.

        Raises:
            SandboxTimeoutError: If the process exceeds ``timeout``.
            ValueError: If ``output_limit`` is not positive.
        """
        if output_limit is not None and output_limit <= 0:
            raise ValueError("Sandbox output limit must be greater than 0.")

        with (
            tempfile.TemporaryFile() as stdout_file,
            tempfile.TemporaryFile() as stderr_file,
        ):
            try:
                result = subprocess.run(
                    self.build_command(argv, spec, env=env),
                    cwd=spec.workspace.resolve(),
                    env={"PATH": os.defpath},
                    timeout=timeout,
                    stdout=subprocess.DEVNULL if discard_stdout else stdout_file,
                    stderr=stderr_file,
                )
            except subprocess.TimeoutExpired as exc:
                raise SandboxTimeoutError(
                    f"Sandbox command timed out after {timeout} seconds."
                ) from exc

            read_size = None if output_limit is None else output_limit + 1
            if discard_stdout:
                stdout = b""
            else:
                stdout_file.seek(0)
                stdout = stdout_file.read(read_size)
            stderr_file.seek(0)
            stderr = stderr_file.read(read_size)
        return SandboxRunResult(
            returncode=result.returncode,
            stdout=stdout[:output_limit] if output_limit is not None else stdout,
            stderr=stderr[:output_limit] if output_limit is not None else stderr,
            stdout_limited=output_limit is not None and len(stdout) > output_limit,
            stderr_limited=output_limit is not None and len(stderr) > output_limit,
        )

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

    @abstractmethod
    def _build_command(
        self,
        argv: list[str],
        workspace: Path,
        spec: SandboxSpec,
        env: dict[str, str],
    ) -> list[str]:
        """Build a Unix sandbox command after common input validation."""


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
