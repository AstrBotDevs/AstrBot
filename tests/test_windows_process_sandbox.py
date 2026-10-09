"""Windows adapter tests and opt-in native AppContainer integration tests."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@pytest.fixture
def native_sandbox():
    """Use real startup authorization only when explicitly requested."""
    if os.environ.get("ASTRBOT_TEST_WINDOWS_SANDBOX") != "1":
        pytest.skip("Set ASTRBOT_TEST_WINDOWS_SANDBOX=1 after runtime ACL preparation")
    from astrbot.core.computer.process_sandbox.windows import AppContainerProcessSandbox
    from astrbot.core.computer.process_sandbox.windows_setup import (
        initialize_windows_sandbox,
    )

    initialize_windows_sandbox(allow_elevation=False)
    return AppContainerProcessSandbox()


def test_windows_safe_file_handles(native_sandbox, tmp_path):
    from astrbot.core.computer.local_file_security import open_file_in_allowed_roots

    target = tmp_path / "nested" / "中文.txt"
    fd = open_file_in_allowed_roots(
        str(target), (tmp_path,), access="write", create_parents=True
    )
    os.write(fd, "hello 中文".encode())
    os.close(fd)
    fd = open_file_in_allowed_roots(str(target), (tmp_path,), access="read")
    assert os.read(fd, 100).decode() == "hello 中文"
    os.close(fd)
    alias = tmp_path / "alias"
    os.link(target, alias)
    with pytest.raises(PermissionError, match="hard link"):
        open_file_in_allowed_roots(str(target), (tmp_path,), access="write")
    with pytest.raises(PermissionError):
        open_file_in_allowed_roots(
            str(tmp_path.parent / "outside"), (tmp_path,), access="read"
        )
    for suffix in (".. \\outside", "nested\\中文.txt:stream", "nested\\中文.txt."):
        with pytest.raises(PermissionError):
            open_file_in_allowed_roots(
                str(tmp_path / suffix), (tmp_path,), access="write"
            )


def test_native_python_runtime(native_sandbox, tmp_path):
    from astrbot.core.computer.process_sandbox import SandboxSpec

    code = """
from pathlib import Path
import numpy
assert numpy.arange(3).sum() == 3
Path('result.txt').write_text('hello')
"""
    result = native_sandbox.run(
        [sys.executable, "-c", code], SandboxSpec(tmp_path), timeout=25
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert (tmp_path / "result.txt").read_text() == "hello"


def test_native_read_only_and_network_denied(native_sandbox, tmp_path):
    from astrbot.core.computer.process_sandbox import SandboxSpec

    code = """
import socket
from pathlib import Path
try:
    Path('forbidden.txt').write_text('no')
except PermissionError:
    print('write denied')
else:
    raise AssertionError('workspace writable')
s = socket.socket()
s.settimeout(3)
try:
    s.connect(('1.1.1.1', 443))
except OSError as exc:
    assert exc.winerror == 10013, repr(exc)
    print('network denied')
else:
    raise AssertionError('network allowed')
"""
    result = native_sandbox.run(
        [sys.executable, "-c", code],
        SandboxSpec(tmp_path, workspace_writable=False),
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"network denied" in result.stdout


def test_native_output_cap(native_sandbox, tmp_path):
    from astrbot.core.computer.process_sandbox import SandboxSpec

    result = native_sandbox.run(
        [sys.executable, "-c", "print('a' * 1000000)"],
        SandboxSpec(tmp_path),
        timeout=10,
        output_limit=100,
    )
    assert len(result.stdout) == 100
    assert result.stdout_limited


def test_native_job_limits(native_sandbox, tmp_path):
    from astrbot.core.computer.process_sandbox import SandboxLimits, SandboxSpec

    # A Windows venv launcher starts a second process. Use the base interpreter
    # to test a one-process ceiling without counting that launcher.
    result = native_sandbox.run(
        [
            sys._base_executable,
            "-c",
            """
import subprocess, sys
try:
    subprocess.Popen([sys.executable, '-c', 'pass'])
except OSError:
    print('process limit enforced')
else:
    raise AssertionError('child escaped active process limit')
try:
    bytearray(300 * 1024 * 1024)
except MemoryError:
    print('memory limit enforced')
else:
    raise AssertionError('allocation exceeded job memory limit')
""",
        ],
        SandboxSpec(
            tmp_path, limits=SandboxLimits(processes=1, memory_bytes=128 * 1024 * 1024)
        ),
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert b"process limit enforced" in result.stdout
    assert b"memory limit enforced" in result.stdout
    result = native_sandbox.run(
        [sys.executable, "-c", "while True: pass"],
        SandboxSpec(tmp_path, limits=SandboxLimits(cpu_seconds=1)),
        timeout=10,
    )
    assert result.returncode != 0


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_native_managed_shell(native_sandbox, tmp_path, monkeypatch, legacy):
    from astrbot.core.computer.booters.local import LocalShellComponent
    from astrbot.core.computer.process_sandbox import windows_setup

    if legacy:
        monkeypatch.setattr(
            windows_setup,
            "shell_path",
            lambda: (
                Path(os.environ["SystemRoot"])
                / "System32/WindowsPowerShell/v1.0/powershell.exe"
            ),
        )

    component = LocalShellComponent()
    result = await component.exec_managed(
        "Set-Content -LiteralPath '中文.txt' -Value 'PowerShell 中文' -Encoding UTF8; "
        "Get-Content -LiteralPath '中文.txt'; "
        "python -u -c \"print('ready'); print(input())\"",
        owner_id="windows-test",
        creator_id="tester",
        creator_is_admin=False,
        sandboxed=True,
        permission_check=lambda: True,
        cwd=str(tmp_path),
        yield_time_ms=0,
        timeout=20,
    )
    identity = dict(
        owner_id="windows-test",
        requester_id="tester",
        requester_is_admin=False,
        session_id=result["session_id"],
    )
    try:
        await component.write_session(**identity, chars="hello\n")
        output = result["stdout"]
        while not result.get("session_closed"):
            result = await component.poll_session(**identity, yield_time_ms=5000)
            output += result["stdout"]
        assert result["exit_code"] == 0, output
        assert "ready" in output and "hello" in output
        assert "PowerShell 中文" in output
        assert (tmp_path / "中文.txt").read_text(
            encoding="utf-8-sig"
        ).strip() == "PowerShell 中文"
    finally:
        await component.shutdown_sessions()


@pytest.mark.asyncio
async def test_native_file_search(native_sandbox, tmp_path):
    from astrbot.core.computer.booters.local import LocalFileSystemComponent

    (tmp_path / "example.txt").write_text("isolated search needle", encoding="utf-8")
    result = await LocalFileSystemComponent().search_files(
        "needle",
        path=str(tmp_path),
        sandboxed=True,
        sandbox_root=str(tmp_path),
    )
    assert result["success"], result
    assert "isolated search needle" in result["content"]


def test_native_child_cleanup(native_sandbox, tmp_path):
    import psutil

    from astrbot.core.computer.process_sandbox import SandboxSpec, SandboxTimeoutError

    code = """
import subprocess, sys, time
from pathlib import Path
p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
Path('child.pid').write_text(str(p.pid))
time.sleep(60)
"""
    with pytest.raises(SandboxTimeoutError):
        native_sandbox.run(
            [sys.executable, "-c", code], SandboxSpec(tmp_path), timeout=3
        )
    pid = int((tmp_path / "child.pid").read_text())
    assert not psutil.pid_exists(pid)


def test_native_failed_launch_releases_process_and_acl(
    native_sandbox, tmp_path, monkeypatch
):
    import psutil
    import win32security

    from astrbot.core.computer.process_sandbox import SandboxSpec, windows

    acl = win32security.GetNamedSecurityInfo(
        str(tmp_path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
    ).GetSecurityDescriptorDacl()
    original_aces = [acl.GetAce(i) for i in range(acl.GetAceCount())]
    process_ids = []

    def reject_assignment(job, process):
        process_ids.append(windows.win32process.GetProcessId(process))
        raise OSError("Job assignment rejected")

    monkeypatch.setattr(windows.win32job, "AssignProcessToJobObject", reject_assignment)
    with pytest.raises(OSError, match="Job assignment rejected"):
        native_sandbox.run(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            SandboxSpec(tmp_path),
            timeout=5,
        )
    assert len(process_ids) == 1
    assert not psutil.pid_exists(process_ids[0])
    acl = win32security.GetNamedSecurityInfo(
        str(tmp_path),
        win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
    ).GetSecurityDescriptorDacl()
    assert [acl.GetAce(i) for i in range(acl.GetAceCount())] == original_aces


def test_native_external_roots_and_junction(native_sandbox, tmp_path):
    from astrbot.core.computer.local_file_security import open_file_in_allowed_roots
    from astrbot.core.computer.process_sandbox import SandboxSpec

    workspace, readable, writable, secret = (
        tmp_path / name for name in ("work", "read", "write", "secret")
    )
    for directory in (workspace, readable, writable, secret):
        directory.mkdir()
        (directory / "sentinel.txt").write_text("original")
    junction = workspace / "escape"
    subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(secret)],
        check=True,
        capture_output=True,
    )
    try:
        with pytest.raises(PermissionError, match="reparse"):
            open_file_in_allowed_roots(
                str(junction / "sentinel.txt"), (workspace,), access="write"
            )
        code = f"""
from pathlib import Path
import win32security
readable, writable, secret = map(Path, {list(map(str, (readable, writable, secret)))!r})
assert (readable / 'sentinel.txt').read_text() == 'original'
(writable / 'sentinel.txt').write_text('allowed')
for target in [secret / 'sentinel.txt', Path('escape/sentinel.txt')]:
    for action in [lambda: target.read_text(), lambda: target.write_text('escaped')]:
        try:
            action()
        except PermissionError:
            pass
        else:
            raise AssertionError(f'outside access allowed: {{target}}')
try:
    (readable / 'sentinel.txt').write_text('escaped')
except PermissionError:
    pass
else:
    raise AssertionError('read-only root writable')
try:
    win32security.SetNamedSecurityInfo(str(secret), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION, None, None, None, None)
except Exception as exc:
    assert exc.winerror == 5, repr(exc)
else:
    raise AssertionError('outside ACL writable')
print('external boundaries enforced')
"""
        result = native_sandbox.run(
            [sys.executable, "-c", code],
            SandboxSpec(
                workspace, readable_roots=(readable,), writable_roots=(writable,)
            ),
            timeout=15,
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert (secret / "sentinel.txt").read_text() == "original"
        assert (readable / "sentinel.txt").read_text() == "original"
        assert (writable / "sentinel.txt").read_text() == "allowed"
    finally:
        # Removing the junction itself never traverses or removes its target.
        junction.rmdir()


def test_native_concurrent_identity_isolation(native_sandbox, tmp_path):
    from astrbot.core.computer.process_sandbox import SandboxSpec

    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    secret = first / "secret.txt"
    secret.write_text("private")
    process = native_sandbox._spawn(
        [sys.executable, "-c", "import time; time.sleep(30)"], SandboxSpec(first)
    )
    try:
        code = f"""
from pathlib import Path
try:
    Path({str(secret)!r}).read_text()
except PermissionError:
    print('other sandbox denied')
else:
    raise AssertionError('another execution shared filesystem grants')
"""
        result = native_sandbox.run(
            [sys.executable, "-c", code], SandboxSpec(second), timeout=10
        )
        assert result.returncode == 0, result.stderr.decode(errors="replace")
    finally:
        process.close()


def test_native_network_enabled(native_sandbox, tmp_path):
    import socket

    from astrbot.core.computer.process_sandbox import SandboxSpec

    host = os.environ.get("ASTRBOT_TEST_NETWORK_HOST", "www.baidu.com")
    try:
        socket.create_connection((host, 443), timeout=5).close()
    except OSError:
        pytest.skip("Host cannot reach the TCP test endpoint")
    result = native_sandbox.run(
        [
            sys.executable,
            "-c",
            f"import socket; socket.create_connection(({host!r}, 443), timeout=5).close()",
        ],
        SandboxSpec(tmp_path, allow_network=True),
        timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


def test_runtime_subdirectory_cannot_be_writable(native_sandbox, tmp_path, monkeypatch):
    from astrbot.core.computer.process_sandbox import SandboxSpec, windows_setup

    monkeypatch.setattr(windows_setup, "runtime_paths", lambda: (tmp_path,))
    with pytest.raises(RuntimeError, match="inside a runtime"):
        native_sandbox.run(
            [sys.executable, "-c", "pass"], SandboxSpec(tmp_path), timeout=5
        )


def test_uac_cancellation_is_not_retried(tmp_path, monkeypatch):
    import pywintypes

    from astrbot.core.computer.process_sandbox import windows, windows_setup

    monkeypatch.setattr(windows_setup, "_attempted", False)
    monkeypatch.setattr(windows_setup, "_ready", False)
    monkeypatch.setattr(windows_setup, "_error", "not prepared")
    monkeypatch.setattr(windows_setup, "runtime_paths", lambda: (tmp_path,))

    def deny(*args):
        raise pywintypes.error(5, "SetNamedSecurityInfo", "Access denied")

    monkeypatch.setattr(windows, "set_directory_access", deny)
    calls = []

    def cancel(**kwargs):
        calls.append(kwargs)
        raise pywintypes.error(1223, "ShellExecuteEx", "Cancelled")

    monkeypatch.setattr(windows_setup.shell, "ShellExecuteEx", cancel)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="Cancelled"):
            windows_setup.initialize_windows_sandbox()
    assert len(calls) == 1
    assert calls[0]["lpVerb"] == "runas"
    assert calls[0]["nShow"] == 0
