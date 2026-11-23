"""File transfer tools validate inputs and preserve remote transport failures."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_runtime.tools.computer_tools import fs


@pytest.fixture
def transfer_context(monkeypatch, tmp_path):
    """Keep file I/O real and replace the remote sandbox transport."""
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:files", send=AsyncMock()
    )
    context = ContextWrapper(context=SimpleNamespace(event=event, context=object()))
    sandbox = SimpleNamespace(upload_file=AsyncMock(), download_file=AsyncMock())
    connect = AsyncMock(return_value=sandbox)
    monkeypatch.setattr(fs, "get_booter", connect)
    monkeypatch.setattr(fs, "check_admin_permission", lambda *_: None)
    monkeypatch.setattr(fs, "get_astrbot_temp_path", lambda: str(tmp_path))
    return context, sandbox, connect


@pytest.mark.asyncio
async def test_upload_preserves_basename_and_reports_remote_path(
    transfer_context, tmp_path
):
    context, sandbox, connect = transfer_context
    source = tmp_path / "report.txt"
    source.write_text("report", encoding="utf-8")
    sandbox.upload_file.return_value = {
        "success": True,
        "file_path": "/work/report.txt",
    }

    result = await fs.FileUploadTool().call(context, str(source))

    assert result == "File uploaded successfully to /work/report.txt"
    sandbox.upload_file.assert_awaited_once_with(str(source), "report.txt")
    connect.assert_awaited_once_with(
        context.context.context, context.context.event.unified_msg_origin
    )
    assert source.read_text(encoding="utf-8") == "report"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing", "directory"])
async def test_invalid_upload_never_transfers(transfer_context, tmp_path, kind):
    context, sandbox, _ = transfer_context
    source = tmp_path / kind
    if kind == "directory":
        source.mkdir()
    result = await fs.FileUploadTool().call(context, str(source))
    expected = "File does not exist" if kind == "missing" else "Path is not a file"
    assert result == f"Error: {expected}: {source}"
    sandbox.upload_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_surfaces_remote_failure(transfer_context, tmp_path):
    context, sandbox, _ = transfer_context
    source = tmp_path / "report.txt"
    source.write_text("report", encoding="utf-8")
    sandbox.upload_file.return_value = {"success": False, "message": "quota exhausted"}
    assert (
        await fs.FileUploadTool().call(context, str(source))
        == "Error uploading file: quota exhausted"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("remote_path", ["/work/report.txt", r"C:\work\report.txt"])
async def test_download_keeps_remote_name_without_sending(
    transfer_context, tmp_path, remote_path
):
    context, sandbox, _ = transfer_context

    async def download(remote, destination):
        assert remote == remote_path
        Path(destination).write_text("downloaded", encoding="utf-8")

    sandbox.download_file.side_effect = download
    result = await fs.FileDownloadTool().call(
        context, remote_path, also_send_to_user=False
    )
    sandbox.download_file.assert_awaited_once()
    target = Path(sandbox.download_file.await_args.args[1])
    assert target.parent == tmp_path
    assert target.name.endswith("_report.txt")
    assert target.read_text(encoding="utf-8") == "downloaded"
    assert result == f"File downloaded successfully to {target}"
    context.context.event.send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_type,arguments",
    [
        (fs.FileUploadTool, {"local_path": "/blocked"}),
        (fs.FileDownloadTool, {"remote_path": "/blocked"}),
    ],
)
async def test_denied_transfer_never_connects(
    transfer_context, monkeypatch, tool_type, arguments
):
    context, sandbox, connect = transfer_context
    monkeypatch.setattr(fs, "check_admin_permission", lambda *_: "permission denied")
    assert await tool_type().call(context, **arguments) == "permission denied"
    connect.assert_not_awaited()
    sandbox.upload_file.assert_not_awaited()
    sandbox.download_file.assert_not_awaited()
