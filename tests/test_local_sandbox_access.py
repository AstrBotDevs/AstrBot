"""Regression coverage for Local execution network and filesystem access."""

from __future__ import annotations

import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.computer.booters import local
from astrbot.core.computer.process_sandbox import (
    SandboxSpec,
    bubblewrap,
    create_process_sandbox,
    seatbelt,
    unix,
)
from astrbot.core.tools.computer_tools import fs, python, shell
from astrbot.dashboard.services import stat_service

requires_local_sandbox = pytest.mark.skipif(
    not (
        (sys.platform.startswith("linux") and shutil.which("bwrap"))
        or (sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists())
    ),
    reason="Requires a supported Local process sandbox.",
)


@requires_local_sandbox
@pytest.mark.asyncio
async def test_managed_shell_output_cannot_be_redirected_outside_sandbox(
    monkeypatch, tmp_path
):
    """Keep host output reads on the original handle after shared-path attacks."""
    workspace = tmp_path / "workspace"
    shared_temp = tmp_path / "shared-temp"
    workspace.mkdir()
    shared_temp.mkdir()
    secret = tmp_path / "host-only.txt"
    secret.write_text("host-only marker", encoding="utf-8")
    monkeypatch.setattr(local, "get_astrbot_system_tmp_path", lambda: str(shared_temp))
    code = f"""
from pathlib import Path

secret = Path({str(secret)!r})
assert not secret.exists(), "The host file must be outside the sandbox."
for log in Path({str(shared_temp)!r}).rglob("sh_*.log"):
    log.unlink()
    log.symlink_to(secret)
print("original process output")
"""
    component = local.LocalShellComponent()
    try:
        result = await component.exec_managed(
            shlex.join(["python", "-c", code]),
            owner_id="test:GroupMessage:output",
            creator_id="member",
            creator_is_admin=False,
            sandboxed=True,
            permission_check=lambda: True,
            cwd=str(workspace),
            writable_roots=(shared_temp,),
            timeout=10,
        )
        assert result["exit_code"] == 0, result
        assert result["stdout"] == "original process output\n"
        assert result["session_closed"] is True
        assert secret.read_text(encoding="utf-8") == "host-only marker"
    finally:
        await component.shutdown_sessions()


@requires_local_sandbox
def test_runtime_probe_launches_native_sandbox(monkeypatch, tmp_path):
    """Verify the dashboard startup check against each platform's real backend."""
    monkeypatch.setattr(stat_service, "get_astrbot_temp_path", lambda: str(tmp_path))

    service = stat_service.StatService(MagicMock(), MagicMock(), {})

    assert service.runtime["sandbox"]["status"] == "detected", service.runtime
    assert not list(tmp_path.iterdir())


@requires_local_sandbox
@pytest.mark.parametrize("entry", ["python", "shell"])
def test_local_sandbox_reads_existing_python_dependencies(tmp_path, entry):
    """Reuse installed dependencies while denying write access to the real runtime."""
    code = f"""
import errno
import os
import sys
from pathlib import Path
import aiohttp
import pydantic

assert sys.prefix == {sys.prefix!r}, sys.prefix
assert Path(sys.executable).parent == Path({sys.executable!r}).parent
for path in (sys.executable, os.__file__, aiohttp.__file__, pydantic.__file__):
    try:
        fd = os.open(path, os.O_WRONLY)
    except OSError as exc:
        assert exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS, errno.ETXTBSY), exc
    else:
        os.close(fd)
        raise AssertionError("Python environment is writable: " + path)
Path("output.txt").write_text("workspace remains writable")
print("existing dependencies are read-only")
"""
    argv = [sys.executable, "-c", code]
    if entry == "shell":
        argv = ["/bin/sh", "-c", shlex.join(["python", "-c", code])]

    result = create_process_sandbox().run(
        argv, SandboxSpec(workspace=tmp_path), timeout=15
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.strip() == b"existing dependencies are read-only"
    assert (tmp_path / "output.txt").read_text() == "workspace remains writable"


@requires_local_sandbox
@pytest.mark.parametrize(
    "location", ["outside", "workspace", "writable_root", "writable_packages"]
)
def test_local_sandbox_protects_venv_inside_writable_roots(
    monkeypatch, tmp_path, location
):
    """Deny package changes even when a writable root contains the virtualenv."""
    workspace = tmp_path / "workspace"
    attachments = tmp_path / "attachments"
    workspace.mkdir()
    attachments.mkdir()
    parent = {"workspace": workspace, "writable_root": attachments}.get(
        location, tmp_path
    )
    prefix = parent / ".venv"
    base_python = Path(sys._base_executable)
    subprocess.run(
        [str(base_python), "-m", "venv", "--without-pip", "--symlinks", str(prefix)],
        check=True,
        capture_output=True,
        timeout=20,
    )
    # Exercise an interpreter directory alias, as used by uv installations.
    alias = tmp_path / "python alias"
    alias.symlink_to(base_python.parent, target_is_directory=True)
    executable = prefix / "bin" / "python"
    executable.unlink()
    executable.symlink_to(alias / base_python.name)
    package = (
        prefix
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
        / "sandbox_dependency.py"
    )
    package.write_text("VALUE = 'original'\n", encoding="utf-8")
    config = prefix / "pyvenv.cfg"
    original_config = config.read_bytes()
    runtime_sys = SimpleNamespace(
        executable=str(executable),
        prefix=str(prefix),
        base_prefix=sys.base_prefix,
        platform=sys.platform,
    )
    for module in (bubblewrap, seatbelt, unix):
        monkeypatch.setattr(module, "sys", runtime_sys)
    code = f"""
import errno
import os
import sys
from pathlib import Path
import sandbox_dependency

assert sys.prefix == {str(prefix)!r}, sys.prefix
assert sandbox_dependency.VALUE == "original"
package = Path(sandbox_dependency.__file__)
for path in (Path(sys.executable), Path(sys.prefix) / "pyvenv.cfg", package):
    try:
        fd = os.open(path, os.O_WRONLY)
    except OSError as exc:
        assert exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS, errno.ETXTBSY), exc
    else:
        os.close(fd)
        raise AssertionError("Python environment is writable: " + str(path))
for operation in ("install", "uninstall", "replace"):
    try:
        if operation == "install":
            package.with_name("new_dependency.py").write_text("changed")
        elif operation == "uninstall":
            package.unlink()
        else:
            package.rename(package.with_suffix(".backup"))
    except OSError as exc:
        assert exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS), exc
    else:
        raise AssertionError("Package modification succeeded: " + operation)
Path("output.txt").write_text("workspace remains writable")
print("virtualenv is read-only")
"""
    result = create_process_sandbox().run(
        [str(executable), "-c", code],
        SandboxSpec(
            workspace=workspace,
            writable_roots=(
                package.parent if location == "writable_packages" else attachments,
            ),
        ),
        timeout=15,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.strip() == b"virtualenv is read-only"
    assert package.read_text() == "VALUE = 'original'\n"
    assert config.read_bytes() == original_config
    assert not package.with_name("new_dependency.py").exists()
    assert (workspace / "output.txt").read_text() == "workspace remains writable"


@requires_local_sandbox
@pytest.mark.parametrize("filesystem_scope", ["workspace", "host"])
def test_local_sandbox_resolves_dns_with_network_enabled(tmp_path, filesystem_scope):
    """Resolve a public hostname through the operating system's real DNS resolver."""
    result = create_process_sandbox().run(
        [
            sys.executable,
            "-c",
            "import socket; "
            "assert socket.getaddrinfo('example.com', 443, type=socket.SOCK_STREAM); "
            "print('DNS resolution succeeded')",
        ],
        SandboxSpec(
            workspace=tmp_path,
            allow_network=True,
            filesystem_scope=filesystem_scope,
        ),
        timeout=20,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.strip() == b"DNS resolution succeeded"


@requires_local_sandbox
@pytest.mark.parametrize("filesystem_scope", ["workspace", "host"])
def test_local_sandbox_cannot_connect_when_network_disabled(tmp_path, filesystem_scope):
    """Reject a reachable host connection even after enabling filesystem access."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        code = f"""
import socket

try:
    with socket.create_connection({listener.getsockname()!r}, timeout=1):
        pass
except OSError:
    print("Network access denied")
else:
    raise AssertionError("Network access unexpectedly succeeded")
"""
        result = create_process_sandbox().run(
            [sys.executable, "-c", code],
            SandboxSpec(
                workspace=tmp_path,
                allow_network=False,
                filesystem_scope=filesystem_scope,
            ),
            timeout=10,
        )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.strip() == b"Network access denied"


@pytest.mark.skipif(
    not sys.platform.startswith("linux") or not shutil.which("bwrap"),
    reason="Requires Linux and bubblewrap.",
)
@pytest.mark.parametrize("allow_network", [False, True])
def test_bubblewrap_exposes_symlinked_dns_config_only_with_network(
    monkeypatch, tmp_path, allow_network
):
    """Expose resolver contents without granting access to their host directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    resolver = tmp_path / "run" / "resolved.conf"
    resolver.parent.mkdir()
    resolver.write_text("nameserver 192.0.2.1\n", encoding="utf-8")
    config = tmp_path / "etc" / "resolv.conf"
    config.parent.mkdir()
    config.symlink_to(resolver)
    monkeypatch.setattr(bubblewrap, "_NETWORK_CONFIG_PATHS", {config})

    code = f"""
from pathlib import Path

config = Path({str(config)!r})
assert config.exists() is {allow_network!r}
if config.exists():
    assert config.read_text() == "nameserver 192.0.2.1\\n"
    try:
        config.write_text("changed")
    except OSError:
        pass
    else:
        raise AssertionError("Resolver configuration is writable")
assert not Path({str(resolver)!r}).exists()
print("resolver access verified")
"""
    result = bubblewrap.BubblewrapProcessSandbox().run(
        [sys.executable, "-c", code],
        SandboxSpec(workspace=workspace, allow_network=allow_network),
        timeout=10,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.strip() == b"resolver access verified"


@pytest.mark.skipif(sys.platform == "win32", reason="Requires Unix paths.")
def test_bubblewrap_includes_host_resolver_configuration(monkeypatch, tmp_path):
    """Include available host resolver and hosts files when network is enabled."""
    monkeypatch.setattr(bubblewrap.shutil, "which", lambda name: f"/usr/bin/{name}")
    command = bubblewrap.BubblewrapProcessSandbox().build_command(
        [sys.executable, "-c", "pass"],
        SandboxSpec(workspace=tmp_path, allow_network=True),
    )

    for path in (Path("/etc/resolv.conf"), Path("/etc/hosts")):
        if path.exists():
            assert any(
                command[index : index + 3] == ["--ro-bind", str(path), str(path)]
                for index in range(len(command) - 2)
            )


def test_seatbelt_grants_additional_roots_with_separate_write_access(
    monkeypatch, tmp_path
):
    """Keep Skill roots read-only while permitting new temporary directories."""
    monkeypatch.setattr(
        seatbelt.shutil, "which", lambda name, **kwargs: f"/usr/bin/{name}"
    )
    skills = tmp_path / "skills"
    skills.mkdir()
    temporary = tmp_path / "temp"
    missing = tmp_path / "missing-skill"
    command = seatbelt.SeatbeltProcessSandbox().build_command(
        [sys.executable, "-c", "pass"],
        SandboxSpec(
            workspace=tmp_path,
            readable_roots=(skills, missing),
            writable_roots=(temporary,),
        ),
    )
    profile = command[command.index("-p") + 1]

    for root, writable in ((skills, False), (temporary, True)):
        definition = next(arg for arg in command if arg.endswith(f"={root.resolve()}"))
        parameter = definition.split("=", 1)[0]
        rule = next(line for line in profile.splitlines() if f'"{parameter}"' in line)
        assert "file-read* file-map-executable" in rule
        assert ("file-write*" in rule) is writable
    assert temporary.is_dir()
    assert not missing.exists()
    assert not any(arg.endswith(f"={missing}") for arg in command)
    assert "(deny network*)" in profile


@requires_local_sandbox
@pytest.mark.parametrize("tool_kind", ["shell", "python"])
@pytest.mark.parametrize("role", ["member", "admin"])
@pytest.mark.asyncio
async def test_local_execution_obeys_file_tool_roots(
    monkeypatch, tmp_path, role, tool_kind
):
    """Run Skill scripts and process attachments under the caller's file policy."""
    tmp_path = tmp_path.resolve()
    workspace = tmp_path / "work area"
    installed = tmp_path / "data" / "skills"
    plugin = tmp_path / "plugins" / "example" / "skills"
    builtin = tmp_path / "builtins" / "example" / "skills"
    temporary = tmp_path / "data" / "temp"
    system_temp = tmp_path / "system temp"
    for root in (workspace, installed, plugin, builtin, temporary, system_temp):
        root.mkdir(parents=True)
        (root / "sample.txt").write_text("approved content", encoding="utf-8")
    for root in (installed, plugin, builtin):
        (root / "script.py").write_text("print('skill executed')", encoding="utf-8")
    secret = tmp_path / "data" / "private.txt"
    secret.write_text("outside content", encoding="utf-8")
    (workspace / "outside-link").symlink_to(secret)
    monkeypatch.setattr(fs, "get_astrbot_skills_path", lambda: str(installed))
    monkeypatch.setattr(
        fs, "get_astrbot_plugin_path", lambda: str(plugin.parent.parent)
    )
    monkeypatch.setattr(
        fs, "get_astrbot_builtin_plugin_path", lambda: str(builtin.parent.parent)
    )
    monkeypatch.setattr(fs, "get_astrbot_temp_path", lambda: str(temporary))
    monkeypatch.setattr(fs, "get_astrbot_system_tmp_path", lambda: str(system_temp))
    monkeypatch.setattr(local, "get_astrbot_system_tmp_path", lambda: str(system_temp))
    monkeypatch.setattr(
        shell, "workspace_root_for_context", AsyncMock(return_value=workspace)
    )
    monkeypatch.setattr(
        python, "workspace_root_for_context", AsyncMock(return_value=workspace)
    )
    booter = local.LocalBooter()
    monkeypatch.setattr(shell, "get_booter", AsyncMock(return_value=booter))
    monkeypatch.setattr(python, "get_local_booter", lambda: booter)
    config = {
        "admins_id": ["test-user"] if role == "admin" else [],
        "provider_settings": {
            "computer_use_runtime": "local",
            "computer_use_local_permissions": {
                role: {
                    "filesystem_scope": "workspace",
                    "allow_execution": True,
                    "allow_network": False,
                }
            },
        }
    }
    event = SimpleNamespace(
        role=role,
        unified_msg_origin="test:friend:sandbox-roots",
        get_sender_id=lambda: "test-user",
    )
    context = ContextWrapper(
        context=SimpleNamespace(
            context=SimpleNamespace(get_config=lambda umo: config), event=event
        ),
        tool_call_timeout=20,
    )
    readable = fs._read_allowed_roots(event.unified_msg_origin, workspace)
    writable = fs._write_allowed_roots(
        event.unified_msg_origin, workspace, include_installed_skills=role == "admin"
    )
    code = f"""
import runpy
from pathlib import Path

for root in {list(map(str, readable))!r}:
    assert (Path(root) / "sample.txt").read_text() == "approved content"
for root in {list(map(str, (installed, plugin, builtin)))!r}:
    runpy.run_path(str(Path(root) / "script.py"))
for root in {list(map(str, writable))!r}:
    (Path(root) / "output.txt").write_text("created")
for root in {list(map(str, set(readable) - set(writable)))!r}:
    try:
        (Path(root) / "sample.txt").write_text("changed")
    except OSError:
        pass
    else:
        raise AssertionError("Skill directory is writable: " + root)
for path in {[str(secret), str(workspace / "outside-link")]!r}:
    try:
        Path(path).read_text()
    except OSError:
        pass
    else:
        raise AssertionError("Host content is readable: " + path)
print("file policy verified")
"""
    try:
        if tool_kind == "shell":
            result = await shell.LocalExecuteShellTool().call(
                context,
                command=shlex.join([sys.executable, "-c", code]),
                timeout=15,
            )
            assert "exit code 0" in result, result
            output = result
        else:
            result = await python.LocalPythonTool().call(context, code=code, timeout=15)
            assert not isinstance(result, str), result
            output = "".join(part.text for part in result.content)
            assert "error:" not in output, output
        assert output.count("skill executed") == 3
        assert "file policy verified" in output
        for root in writable:
            assert (root / "output.txt").read_text() == "created"
    finally:
        await booter.shell.shutdown_sessions()
