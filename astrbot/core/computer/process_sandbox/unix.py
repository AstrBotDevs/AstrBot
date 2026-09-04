from __future__ import annotations

import sys
from pathlib import Path

from .base import SandboxLimits


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
