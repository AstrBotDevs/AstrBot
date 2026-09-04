from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    """Resource ceilings applied to a sandboxed process tree.

    Args:
        cpu_seconds: Maximum CPU time in seconds.
        file_size_bytes: Maximum size of a file created by one process.
        memory_bytes: Maximum address space or job memory in bytes.
        open_files: Maximum number of open file descriptors or handles when
            supported by the platform.
        processes: Maximum number of processes in the sandbox.
    """

    cpu_seconds: int = 300
    file_size_bytes: int = 100 * 1024 * 1024
    memory_bytes: int = 1024 * 1024 * 1024
    open_files: int = 256
    processes: int = 256

    def __post_init__(self) -> None:
        """Validate that every resource ceiling is a positive integer.

        Raises:
            ValueError: If a resource ceiling is not a positive integer.
        """
        for name in (
            "cpu_seconds",
            "file_size_bytes",
            "memory_bytes",
            "open_files",
            "processes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"Sandbox limit `{name}` must be a positive integer.")


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """Permissions, workspace, and limits for a sandboxed process.

    Args:
        workspace: Directory exposed as the process working directory.
        workspace_writable: Whether the process may modify the workspace.
        allow_network: Whether the process may access the network.
        filesystem_scope: Whether the process sees only its workspace or the
            host filesystem.
        limits: Resource ceilings enforced by the platform backend.
    """

    workspace: Path
    workspace_writable: bool = True
    allow_network: bool = False
    filesystem_scope: str = "workspace"
    limits: SandboxLimits = field(default_factory=SandboxLimits)


class SandboxProcess(Protocol):
    """Process operations used by managed Local shell sessions."""

    @property
    def pid(self) -> int:
        """Return the process identifier."""
        ...

    @property
    def returncode(self) -> int | None:
        """Return the exit status, or ``None`` while the process is running."""
        ...

    @property
    def stdin(self) -> asyncio.StreamWriter | None:
        """Return the process standard-input stream when configured."""
        ...

    @property
    def stdout(self) -> asyncio.StreamReader | None:
        """Return the process standard-output stream when configured."""
        ...

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
