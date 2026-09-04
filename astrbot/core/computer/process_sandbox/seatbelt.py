from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .base import ProcessSandbox, SandboxSpec
from .unix import build_resource_limited_argv

_PROFILE = """
(version 1)
(deny default)
(deny mach-priv-host-port)
(import "system.sb")

(allow process-fork)
(allow process-exec)
(allow process-info* (target self))
(deny process-exec
    (literal "/usr/bin/open")
    (literal "/usr/bin/osascript"))
(deny appleevent-send)
(deny mach-lookup
    (global-name "com.apple.coreservices.launchservicesd")
    (global-name "com.apple.lsd.mapdb")
    (global-name "com.apple.lsd.modifydb")
    (global-name "com.apple.lsd.open")
    (global-name "com.apple.lsd.xpc"))

(allow file-read-metadata file-test-existence)
(allow file-read* file-test-existence
    (subpath "/bin")
    (subpath "/usr/bin")
    (subpath "/usr/libexec")
    (literal (param "EXECUTABLE"))
    (subpath (param "WORKSPACE"))
    (subpath (param "PYTHON_PREFIX"))
    (subpath (param "PYTHON_BASE_PREFIX")))
(allow file-map-executable
    (subpath "/bin")
    (subpath "/usr/bin")
    (subpath "/usr/libexec")
    (literal (param "EXECUTABLE"))
    (subpath (param "WORKSPACE"))
    (subpath (param "PYTHON_PREFIX"))
    (subpath (param "PYTHON_BASE_PREFIX")))
(allow file-write*
    (subpath (param "WORKSPACE")))

(deny file-read*
    (literal "/private/etc/master.passwd")
    (literal "/private/etc/passwd"))
(deny network*)
"""
_READ_ONLY_PROFILE = _PROFILE.replace(
    '(allow file-write*\n    (subpath (param "WORKSPACE")))',
    "(deny file-write*)",
)


class SeatbeltProcessSandbox(ProcessSandbox):
    """macOS restricted-process launcher backed by Seatbelt."""

    def _build_command(
        self,
        argv: list[str],
        workspace: Path,
        spec: SandboxSpec,
        env: dict[str, str],
    ) -> list[str]:
        """Build the Seatbelt command for validated inputs."""
        seatbelt_path = shutil.which("sandbox-exec", path="/usr/bin")
        if seatbelt_path != "/usr/bin/sandbox-exec":
            raise RuntimeError(
                "Seatbelt (`/usr/bin/sandbox-exec`) is required for restricted "
                "Local execution on macOS."
            )

        executable_path = (
            Path(argv[0]).resolve()
            if Path(argv[0]).is_absolute() and Path(argv[0]).exists()
            else Path(sys.executable).resolve()
        )
        profile = _PROFILE if spec.workspace_writable else _READ_ONLY_PROFILE
        if spec.filesystem_scope == "host":
            profile = profile.replace(
                '(import "system.sb")',
                '(import "system.sb")\n\n'
                "(allow file-read* file-write* file-test-existence "
                "file-read-metadata file-map-executable)",
            ).replace(
                "(deny file-read*\n"
                '    (literal "/private/etc/master.passwd")\n'
                '    (literal "/private/etc/passwd"))\n',
                "",
            )
        if spec.allow_network:
            profile = profile.replace("(deny network*)", "(allow network*)")

        executable_definitions: list[str] = []
        executable_rules: list[str] = []
        for index, read_path in enumerate(self._executable_read_paths(executable_path)):
            parameter = f"EXECUTABLE_{index}"
            executable_definitions.extend(("-D", f"{parameter}={read_path}"))
            executable_rules.append(f'(literal (param "{parameter}"))')
        profile = profile.replace(
            '(literal (param "EXECUTABLE"))',
            "\n    ".join(executable_rules),
        )

        sandbox_python = str(Path(sys.executable).resolve())
        environment = [
            *(f"{key}={value}" for key, value in sorted(env.items())),
            f"PATH={Path(sandbox_python).parent}:/usr/bin:/bin",
            f"HOME={workspace}",
            f"TMPDIR={workspace}",
            "LANG=C.UTF-8",
        ]
        return [
            seatbelt_path,
            "-D",
            f"WORKSPACE={workspace}",
            *executable_definitions,
            "-D",
            f"PYTHON_PREFIX={Path(sys.prefix).resolve()}",
            "-D",
            f"PYTHON_BASE_PREFIX={Path(sys.base_prefix).resolve()}",
            "-p",
            profile,
            "/usr/bin/env",
            "-i",
            *environment,
            *build_resource_limited_argv(argv, spec.limits),
        ]

    def _executable_read_paths(self, executable_path: Path) -> tuple[Path, ...]:
        """Collect executable and dynamic-library paths needed by Seatbelt.

        Args:
            executable_path: Executable launched inside Seatbelt.

        Returns:
            Existing absolute files that the dynamic loader may need to read.
        """
        read_paths = {executable_path, executable_path.resolve()}
        resolved_executable = executable_path.resolve()
        if any(
            resolved_executable.is_relative_to(root)
            for root in (
                Path("/bin"),
                Path("/usr"),
                Path(sys.prefix).resolve(),
                Path(sys.base_prefix).resolve(),
            )
        ):
            return tuple(sorted(read_paths, key=str))

        pending = [resolved_executable]
        inspected: set[Path] = set()
        while pending and len(inspected) < 64:
            current = pending.pop()
            if current in inspected:
                continue
            inspected.add(current)
            try:
                result = subprocess.run(
                    ["/usr/bin/otool", "-L", str(current)],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode != 0:
                continue
            for line in result.stdout.decode("utf-8", errors="replace").splitlines()[
                1:
            ]:
                dependency_text = line.strip().split(" (", 1)[0]
                if not dependency_text.startswith("/"):
                    continue
                dependency = Path(dependency_text)
                if not dependency.exists():
                    continue
                resolved_dependency = dependency.resolve()
                read_paths.update((dependency, resolved_dependency))
                if not (
                    resolved_dependency.is_relative_to("/usr")
                    or resolved_dependency.is_relative_to("/System")
                ):
                    pending.append(resolved_dependency)
        return tuple(sorted(read_paths, key=str))
