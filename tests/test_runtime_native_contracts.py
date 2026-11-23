"""Regression checks at SDK, image, and Windows native ownership boundaries."""

from __future__ import annotations

import asyncio
import base64
import ctypes
import io
import sys
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from PIL import Image
from shipyard import ShipyardClient
from shipyard.shell import ShellComponent

from astrbot.core.astr_agent_runtime.computer import (
    file_read_utils,
    local_file_security_windows,
    windows_api,
    windows_job,
)
from astrbot.core.astr_agent_runtime.computer.booters.shipyard import (
    ShipyardShellWrapper,
)


@pytest.mark.asyncio
async def test_shipyard_shell_adapts_default_session_without_forwarding_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ShipyardClient(endpoint_url="http://localhost:8123", access_token="test")
    execute = AsyncMock(return_value={"success": True, "data": {"exit_code": 0}})
    monkeypatch.setattr(client, "_exec_operation", execute)
    shell = ShipyardShellWrapper(ShellComponent(client, "ship", "session"))

    result = await shell.exec("printf ok", cwd="/workspace", timeout=7, session_id=None)

    assert result["success"] is True
    execute.assert_awaited_once_with(
        "ship",
        "shell/exec",
        {
            "command": "printf ok",
            "cwd": "/workspace",
            "env": None,
            "timeout": 7,
            "shell": True,
            "background": False,
        },
        "session",
    )
    with pytest.raises(NotImplementedError, match="session_id"):
        await shell.exec("printf forbidden", session_id="unsupported")
    assert execute.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_format,mime", [("GIF", "image/gif"), ("PNG", "image/png")]
)
async def test_image_compression_preserves_animation_or_alpha_and_cleans_staging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, image_format: str, mime: str
) -> None:
    staging = tmp_path / "image-staging"
    monkeypatch.setattr(file_read_utils, "get_astrbot_temp_path", lambda: str(staging))
    with Image.new("RGBA", (4, 4), (255, 0, 0, 80)) as first:
        buffer = io.BytesIO()
        if image_format == "GIF":
            with Image.new("RGBA", (4, 4), (0, 255, 0, 255)) as second:
                first.save(
                    buffer,
                    format="GIF",
                    save_all=True,
                    append_images=[second],
                    duration=40,
                    loop=0,
                )
        else:
            first.save(buffer, format="PNG")
        original = buffer.getvalue()

    result = await file_read_utils._compress_image_bytes_to_base64(original)

    encoded = result["base64"]
    assert isinstance(encoded, str)
    payload = base64.b64decode(encoded)
    assert result["mime_type"] == mime
    assert result["size_bytes"] == len(payload)
    if image_format == "GIF":
        assert payload == original
        with Image.open(io.BytesIO(payload)) as image:
            assert image.n_frames == 2
    else:
        with Image.open(io.BytesIO(payload)) as image:
            assert image.mode == "RGBA"
            assert image.getpixel((0, 0)) == (255, 0, 0, 80)
    assert not list(staging.iterdir())


@pytest.fixture
def native_error_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(
        ctypes, "WinError", lambda code: OSError(code, "native failure"), raising=False
    )


@pytest.mark.usefixtures("native_error_api")
@pytest.mark.parametrize("failure", [None, "configure", "assign"])
def test_windows_job_preserves_wide_handles_and_cleans_failed_ownership(
    monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    job_handle, process_handle = (1 << 48) + 17, (1 << 48) + 23
    kernel = SimpleNamespace(
        CreateJobObjectW=Mock(return_value=job_handle),
        SetInformationJobObject=Mock(return_value=failure != "configure"),
        OpenProcess=Mock(return_value=process_handle),
        AssignProcessToJobObject=Mock(return_value=failure != "assign"),
        TerminateJobObject=Mock(return_value=True),
        QueryInformationJobObject=Mock(return_value=True),
        CloseHandle=Mock(return_value=True),
    )
    monkeypatch.setattr(ctypes, "WinDLL", Mock(return_value=kernel), raising=False)
    if failure == "configure":
        with pytest.raises(OSError, match="native failure"):
            windows_job.WindowsProcessJob()
        kernel.CloseHandle.assert_called_once_with(job_handle)
        return

    job = windows_job.WindowsProcessJob()
    try:
        assert kernel.CreateJobObjectW.restype is ctypes.wintypes.HANDLE
        assert kernel.OpenProcess.restype is ctypes.wintypes.HANDLE
        assert kernel.AssignProcessToJobObject.argtypes == [
            ctypes.wintypes.HANDLE,
            ctypes.wintypes.HANDLE,
        ]
        if failure == "assign":
            with pytest.raises(OSError, match="native failure"):
                job.attach(123)
        else:
            job.attach(123)
            job.terminate()
            kernel.TerminateJobObject.assert_called_once_with(job_handle, 1)
        kernel.AssignProcessToJobObject.assert_called_once_with(
            job_handle, process_handle
        )
        kernel.CloseHandle.assert_called_once_with(process_handle)
    finally:
        job.close()
    assert kernel.CloseHandle.call_args_list == [call(process_handle), call(job_handle)]
    job.close()
    assert kernel.CloseHandle.call_count == 2


@pytest.mark.parametrize("links", [1, 2])
def test_restricted_windows_file_transfers_only_checked_terminal_handle(
    monkeypatch: pytest.MonkeyPatch, links: int
) -> None:
    handles = [(1 << 48) + number for number in range(1, 4)]
    allocated = iter(handles)

    def create_file(output, *_args) -> int:
        ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = next(
            allocated
        )
        return 0

    def file_information(_handle, output) -> int:
        info = ctypes.cast(
            output, ctypes.POINTER(local_file_security_windows._FileInformation)
        ).contents
        info.Attributes = 0
        info.NumberOfLinks = links
        return 1

    ntdll = SimpleNamespace(
        NtCreateFile=Mock(side_effect=create_file), RtlNtStatusToDosError=Mock()
    )
    kernel = SimpleNamespace(
        CloseHandle=Mock(return_value=1),
        GetFileInformationByHandle=Mock(side_effect=file_information),
        GetFileType=Mock(return_value=1),
    )
    libraries = {"ntdll": ntdll, "kernel32": kernel}
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda name, **_kwargs: libraries[name], raising=False
    )
    crt = SimpleNamespace(open_osfhandle=Mock(return_value=42))
    monkeypatch.setitem(sys.modules, "msvcrt", crt)
    monkeypatch.setattr(windows_api.windows_os, "O_BINARY", 0x8000, raising=False)
    monkeypatch.setattr(windows_api.windows_os, "O_NOINHERIT", 0x80, raising=False)
    root = PureWindowsPath("C:/workspace")
    if links == 2:
        with pytest.raises(PermissionError, match="multiple hard links"):
            local_file_security_windows.open_windows_file(
                root, ("file.txt",), access="write", create_parents=False
            )
        crt.open_osfhandle.assert_not_called()
        expected_closed = list(reversed(handles))
    else:
        result = local_file_security_windows.open_windows_file(
            root, ("file.txt",), access="write", create_parents=False
        )
        assert result == 42
        assert crt.open_osfhandle.call_args.args[0] == handles[-1]
        expected_closed = list(reversed(handles[:-1]))
    assert kernel.CloseHandle.call_args_list == [
        call(handle) for handle in expected_closed
    ]


@pytest.mark.parametrize("borrowed", [None, 0, 123])
def test_windows_cleanup_rejects_borrowed_handles(borrowed: object) -> None:
    with pytest.raises(TypeError, match="owned handle"):
        windows_api.require_owned_handle(borrowed)


@pytest.mark.asyncio
async def test_windows_proactor_rejects_incompatible_loop_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(asyncio, "ProactorEventLoop", None, raising=False)
    with pytest.raises(RuntimeError, match="ProactorEventLoop"):
        windows_api.running_windows_proactor()
