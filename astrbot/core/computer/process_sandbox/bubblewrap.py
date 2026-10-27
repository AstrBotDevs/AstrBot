from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .base import SandboxSpec
from .unix import UnixProcessSandbox, build_resource_limited_argv

_TMP_BYTES = 256 * 1024 * 1024
_NETWORK_CONFIG_PATHS = {
    Path("/etc/resolv.conf"),
    Path("/etc/hosts"),
    Path("/etc/host.conf"),
    Path("/etc/gai.conf"),
}


class BubblewrapProcessSandbox(UnixProcessSandbox):
    """Linux restricted-process launcher backed by bubblewrap."""

    def _build_command(
        self,
        argv: list[str],
        workspace: Path,
        spec: SandboxSpec,
        env: dict[str, str],
    ) -> list[str]:
        """Build the bubblewrap command for validated inputs."""
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            raise RuntimeError(
                "bubblewrap (`bwrap`) is required for restricted Local execution."
            )
        if not Path("/bin/sh").exists():
            raise RuntimeError("The Local bubblewrap sandbox requires /bin/sh.")

        executable_path = (
            Path(argv[0]).resolve()
            if Path(argv[0]).is_absolute() and Path(argv[0]).exists()
            else Path(sys.executable).resolve()
        )
        command = [
            bwrap_path,
            "--unshare-all",
            "--new-session",
            "--die-with-parent",
            "--clearenv",
        ]
        if spec.allow_network:
            command.append("--share-net")

        if spec.filesystem_scope == "host":
            command.extend(
                (
                    "--bind",
                    "/",
                    "/",
                    "--proc",
                    "/proc",
                    "--dev",
                    "/dev",
                    "--chdir",
                    str(workspace),
                )
            )
        else:
            command.extend(
                ("--dir", "/tmp", "--size", str(_TMP_BYTES), "--tmpfs", "/tmp")
            )

        readonly_paths = {
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/lib"),
            Path("/lib64"),
            Path("/etc/alternatives"),
            Path("/etc/ld.so.cache"),
            Path("/etc/ld.so.conf"),
            Path("/etc/ld.so.conf.d"),
            Path("/etc/localtime"),
            Path("/etc/nsswitch.conf"),
            Path("/etc/passwd"),
            Path("/etc/group"),
            Path(sys.prefix).resolve(),
            Path(sys.base_prefix).resolve(),
        }
        if spec.filesystem_scope == "workspace":
            if spec.allow_network:
                readonly_paths.update(_NETWORK_CONFIG_PATHS)
            readonly_paths.update(root.resolve() for root in spec.readable_roots)
            writable_paths = {root.resolve() for root in spec.writable_roots}
            if spec.workspace_writable:
                writable_paths.add(workspace)
            else:
                readonly_paths.add(workspace)
            readonly_paths.difference_update(writable_paths)
            if not any(
                executable_path == path or executable_path.is_relative_to(path)
                for path in readonly_paths
            ):
                readonly_paths.add(executable_path)
            # Keep the venv entry point usable when uv links its interpreter
            # through a directory alias outside the mounted Python prefixes.
            pending = [Path(sys.executable)]
            seen_links: set[Path] = set()
            while pending:
                path = pending.pop()
                for link in (path, *path.parents):
                    if link in seen_links or not link.is_symlink():
                        continue
                    seen_links.add(link)
                    target = link.parent / link.readlink() / path.relative_to(link)
                    pending.append(Path(os.path.abspath(target)))
                    if not any(link.is_relative_to(root) for root in readonly_paths):
                        readonly_paths.add(link)
            readonly_paths = {path for path in readonly_paths if path.exists()}

            required_directories = {Path("/tmp"), Path("/tmp/home")}
            for path in (*readonly_paths, *writable_paths):
                required_directories.update(
                    parent
                    for parent in path.parents
                    if parent != Path("/") and parent not in readonly_paths
                )
            for directory in sorted(
                required_directories,
                key=lambda path: len(path.parts),
            ):
                if directory != Path("/tmp"):
                    command.extend(("--dir", str(directory)))
            command.extend(("--proc", "/proc", "--dev", "/dev"))

            for path in sorted(readonly_paths, key=lambda item: len(item.parts)):
                # Resolver files often link into /run. Bind their contents without
                # exposing the rest of the host service's runtime directory.
                if path.is_symlink() and path not in _NETWORK_CONFIG_PATHS:
                    command.extend(("--symlink", os.readlink(path), str(path)))
                else:
                    command.extend(("--ro-bind", str(path), str(path)))
            for path in sorted(writable_paths, key=lambda item: len(item.parts)):
                command.extend(("--bind", str(path), str(path)))
            # A writable workspace or attachment root must not make AstrBot's
            # Python installation writable when it contains that installation.
            for path in sorted(
                {Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()},
                key=lambda item: len(item.parts),
            ):
                if any(
                    path.is_relative_to(root) or root.is_relative_to(path)
                    for root in writable_paths
                ):
                    command.extend(("--ro-bind", str(path), str(path)))
            command.extend(("--chdir", str(workspace)))

        for key, value in sorted(env.items()):
            command.extend(("--setenv", key, value))
        command.extend(
            (
                "--setenv",
                "PATH",
                f"{Path(sys.executable).parent}:/usr/local/bin:/usr/bin:/bin",
                "--setenv",
                "HOME",
                str(workspace) if spec.filesystem_scope == "host" else "/tmp/home",
                "--setenv",
                "TMPDIR",
                "/tmp",
                "--setenv",
                "LANG",
                "C.UTF-8",
                "--",
                *build_resource_limited_argv(argv, spec.limits),
            )
        )
        return command
