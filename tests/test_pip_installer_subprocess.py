import asyncio
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import pytest

from astrbot.core.utils import pip_installer as pip_installer_module
from astrbot.core.utils.pip_installer import (
    DependencyConflictError,
    PipInstaller,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("frozen", "packaged"), [(False, False), (True, False), (False, True)]
)
async def test_pip_execution_respects_runtime_compatibility(
    monkeypatch, frozen, packaged
):
    monkeypatch.setattr(pip_installer_module, "is_frozen_runtime", lambda: frozen)
    monkeypatch.setattr(
        pip_installer_module, "is_packaged_desktop_runtime", lambda: packaged
    )
    installer = PipInstaller("")
    in_process = AsyncMock(return_value=0)
    subprocess = AsyncMock(return_value=0)
    monkeypatch.setattr(installer, "_run_pip_in_process", in_process)
    monkeypatch.setattr(installer, "_run_pip_subprocess", subprocess)

    await installer._run_pip_with_classification(["install", "demo-package"])

    selected = in_process if frozen or packaged else subprocess
    other = subprocess if frozen or packaged else in_process
    selected.assert_awaited_once_with(["install", "demo-package"])
    other.assert_not_awaited()


@pytest.mark.asyncio
async def test_pip_subprocess_streams_utf8_with_active_interpreter(monkeypatch):
    process = MagicMock()
    process.stdout.read = AsyncMock(
        side_effect=[b"first\n\xe4\xb8", b"\xad\xe6\x96\x87\nlast", b""]
    )
    process.wait = AsyncMock(return_value=0)
    create = AsyncMock(return_value=process)
    log = MagicMock()
    monkeypatch.setattr(pip_installer_module.asyncio, "create_subprocess_exec", create)
    monkeypatch.setattr(pip_installer_module.logger, "info", log)

    assert await PipInstaller("")._run_pip_subprocess(["install", "demo-package"]) == 0

    assert create.await_args.args == (
        pip_installer_module.sys.executable,
        "-u",
        "-m",
        "pip",
        "install",
        "demo-package",
    )
    assert create.await_args.kwargs["stderr"] == asyncio.subprocess.STDOUT
    assert create.await_args.kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
    assert [call.args[0] for call in log.call_args_list] == ["first", "中文", "last"]


@pytest.mark.asyncio
async def test_pip_subprocess_preserves_dependency_conflict_diagnostics(monkeypatch):
    process = MagicMock()
    process.stdout.read = AsyncMock(
        side_effect=[
            b"Cannot install demo-package and astrbot-core because these package "
            b"versions have conflicting dependencies.\n"
            b"The conflict is caused by:\n"
            b"    demo-package depends on shared-lib>=3.0\n"
            b"    AstrBot (constraint) depends on shared-lib==2.0\n",
            b"",
        ]
    )
    process.wait = AsyncMock(return_value=1)
    monkeypatch.setattr(
        pip_installer_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )

    with pytest.raises(DependencyConflictError) as exc_info:
        await PipInstaller("")._run_pip_subprocess(["install", "demo-package"])

    assert exc_info.value.is_core_conflict is True
    assert "demo-package depends on shared-lib>=3.0" in str(exc_info.value)
    assert "AstrBot (constraint) depends on shared-lib==2.0" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cancelled_pip_subprocess_is_killed_and_reaped(monkeypatch):
    process = MagicMock()
    process.returncode = None
    process.stdout.read = AsyncMock(side_effect=asyncio.CancelledError)
    process.wait = AsyncMock(return_value=1)
    monkeypatch.setattr(
        pip_installer_module.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    )

    with pytest.raises(asyncio.CancelledError):
        await PipInstaller("")._run_pip_subprocess(["install", "demo-package"])

    process.kill.assert_called_once_with()
    process.wait.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_offline_install_does_not_invoke_pip_in_parent(monkeypatch, tmp_path):
    monkeypatch.setattr(pip_installer_module, "is_frozen_runtime", lambda: False)
    monkeypatch.setattr(
        pip_installer_module, "is_packaged_desktop_runtime", lambda: False
    )
    pip_main = MagicMock(side_effect=AssertionError("pip must not run in the parent"))
    monkeypatch.setattr(pip_installer_module, "_get_pip_main", pip_main)

    wheel = tmp_path / "astrbot_pip_isolation_test-0.0.0-py3-none-any.whl"
    dist_info = "astrbot_pip_isolation_test-0.0.0.dist-info"
    files = {
        "astrbot_pip_isolation_test.py": "VALUE = 42\n",
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.1\nName: astrbot-pip-isolation-test\nVersion: 0.0.0\n"
        ),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    files[f"{dist_info}/RECORD"] = "".join(
        f"{name},,\n" for name in [*files, f"{dist_info}/RECORD"]
    )
    with ZipFile(wheel, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    target = tmp_path / "installed"

    await PipInstaller("")._run_pip_with_classification(
        ["install", "--no-index", "--no-deps", "--target", str(target), str(wheel)]
    )

    assert (target / "astrbot_pip_isolation_test.py").read_text() == "VALUE = 42\n"
    pip_main.assert_not_called()
