from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_MAX_CPU_SECONDS = 300
_MAX_FILE_BYTES = 100 * 1024 * 1024
_MAX_MEMORY_BYTES = 1024 * 1024 * 1024
_MAX_OPEN_FILES = 256
_MAX_PROCESSES = 256
_RESOURCE_LIMIT_WRAPPER_CODE = f"""
import os
import resource
import sys

limits = [
    (resource.RLIMIT_CPU, {_MAX_CPU_SECONDS}),
    (resource.RLIMIT_FSIZE, {_MAX_FILE_BYTES}),
    (resource.RLIMIT_NOFILE, {_MAX_OPEN_FILES}),
    (resource.RLIMIT_CORE, 0),
]
if sys.platform.startswith("linux"):
    # macOS RLIMIT_NPROC counts every process owned by the host user, and its
    # Python process starts above this virtual-address limit.
    limits.extend(
        (
            (resource.RLIMIT_NPROC, {_MAX_PROCESSES}),
            (resource.RLIMIT_AS, {_MAX_MEMORY_BYTES}),
        )
    )
for kind, requested in limits:
    _, hard = resource.getrlimit(kind)
    value = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
    resource.setrlimit(kind, (value, value))
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
"""


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """Permissions and workspace exposed to a sandboxed process."""

    workspace: Path
    workspace_writable: bool = True
    allow_network: bool = False
    filesystem_scope: str = "workspace"


class SandboxProcess(Protocol):
    """Process operations used by managed Local shell sessions."""

    pid: int
    returncode: int | None
    stdin: asyncio.StreamWriter | None
    stdout: asyncio.StreamReader | None

    async def wait(self) -> int:
        """Wait for the process to exit."""
        ...

    def send_signal(self, signal: int) -> None:
        """Send a signal to the process."""
        ...

    def terminate(self) -> None:
        """Request graceful process termination."""
        ...

    def kill(self) -> None:
        """Force process termination."""
        ...


class ProcessSandbox(ABC):
    """Platform-independent launcher for restricted child processes."""

    def build_command(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Validate common inputs and build a platform sandbox command.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem and network access granted to the process.
            env: Additional environment variables exposed inside the sandbox.

        Returns:
            Platform sandbox command and arguments.

        Raises:
            RuntimeError: If the workspace does not exist.
            ValueError: If the command, scope, or environment is invalid.
        """
        if not argv:
            raise ValueError("A sandbox command is required.")
        if spec.filesystem_scope not in {"workspace", "host"}:
            raise ValueError(
                f"Invalid Local filesystem scope: {spec.filesystem_scope}."
            )

        sandbox_argv = list(argv)
        if Path(sandbox_argv[0]) == Path(sys.executable):
            sandbox_argv[0] = str(Path(sys.executable).resolve())
        workspace = spec.workspace.resolve()
        if not workspace.is_dir():
            raise RuntimeError(f"Sandbox workspace does not exist: {workspace}")

        normalized_env: dict[str, str] = {}
        for raw_key, raw_value in (env or {}).items():
            key = str(raw_key)
            value = str(raw_value)
            if not key or "=" in key or "\x00" in key or "\x00" in value:
                raise ValueError(f"Invalid sandbox environment variable name: {key!r}.")
            normalized_env[key] = value

        return self._build_command(sandbox_argv, workspace, spec, normalized_env)

    def run(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[Any]:
        """Run a restricted process synchronously.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem and network access granted to the process.
            env: Additional environment variables exposed inside the sandbox.
            **kwargs: Extra keyword arguments passed to ``subprocess.run``.

        Returns:
            Completed restricted process.
        """
        return subprocess.run(
            self.build_command(argv, spec, env=env),
            cwd=spec.workspace.resolve(),
            env={"PATH": os.defpath},
            **kwargs,
        )

    async def spawn(
        self,
        argv: list[str],
        spec: SandboxSpec,
        *,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> SandboxProcess:
        """Start a restricted process asynchronously.

        Args:
            argv: Command and arguments to execute inside the sandbox.
            spec: Filesystem and network access granted to the process.
            env: Additional environment variables exposed inside the sandbox.
            **kwargs: Extra keyword arguments passed to the asyncio launcher.

        Returns:
            Running restricted process.
        """
        return await asyncio.create_subprocess_exec(
            *self.build_command(argv, spec, env=env),
            cwd=spec.workspace.resolve(),
            env={"PATH": os.defpath},
            start_new_session=True,
            **kwargs,
        )

    @abstractmethod
    def _build_command(
        self,
        argv: list[str],
        workspace: Path,
        spec: SandboxSpec,
        env: dict[str, str],
    ) -> list[str]:
        """Build a platform command after common input validation."""
