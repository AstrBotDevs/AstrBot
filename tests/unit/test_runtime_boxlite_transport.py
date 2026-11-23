"""Boxlite uses SDK serialization with its direct, unauthenticated transport."""

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from shipyard import ShipyardClient
from shipyard.filesystem import FileSystemComponent
from shipyard.python import PythonComponent
from shipyard.shell import ShellComponent


@pytest.fixture
def boxlite_module(monkeypatch):
    # The HTTP transport needs no native engine; these tests never start a VM.
    if importlib.util.find_spec("boxlite") is None:
        monkeypatch.setitem(sys.modules, "boxlite", ModuleType("boxlite"))
    return importlib.import_module(
        "astrbot.core.astr_agent_runtime.computer.booters.boxlite"
    )


@pytest.mark.asyncio
async def test_direct_sdk_adapter_preserves_operation_arguments(boxlite_module):
    transport = boxlite_module.MockShipyardSandboxClient("http://127.0.0.1:8123/")
    transport._exec_operation = AsyncMock(return_value={"success": True})
    transport.upload_file = AsyncMock(return_value={"success": True})
    client = boxlite_module._BoxliteShipyardClient(transport)
    assert isinstance(client, ShipyardClient)
    await PythonComponent(client, "ship", "session").exec("print(1)", timeout=7)
    await ShellComponent(client, "ship", "session").exec("printf x", cwd="/work")
    await FileSystemComponent(client, "ship", "session").read_file(
        "/work/file", offset=3, limit=2
    )
    operations = transport._exec_operation.await_args_list
    assert [operation.args[1] for operation in operations] == [
        "ipython/exec",
        "shell/exec",
        "fs/read_file",
    ]
    assert all(
        operation.args[0] == "ship" and operation.args[3] == "session"
        for operation in operations
    )
    assert operations[0].args[2]["timeout"] == 7
    assert operations[1].args[2]["cwd"] == "/work"
    assert operations[2].args[2] == {
        "path": "/work/file",
        "encoding": "utf-8",
        "offset": 3,
        "limit": 2,
    }
    await client.upload_file("ship", "/local/file", "session", "/remote/file")
    transport.upload_file.assert_awaited_once_with("/local/file", "/remote/file")
    await client.close()


@pytest.mark.asyncio
async def test_direct_upload_url_contains_exactly_one_scheme(
    boxlite_module, monkeypatch, tmp_path: Path
):
    source = tmp_path / "source.txt"
    source.write_text("payload")
    posted = []

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class Session(Response):
        def post(self, url, **kwargs):
            posted.append((url, kwargs))
            return Response()

    monkeypatch.setattr(
        boxlite_module.aiohttp, "ClientSession", lambda **_kwargs: Session()
    )
    transport = boxlite_module.MockShipyardSandboxClient("http://127.0.0.1:8123/")
    result = await transport.upload_file(str(source), "/remote/source.txt")
    assert result["success"] is True
    assert posted[0][0] == "http://127.0.0.1:8123/upload"
    assert "data" in posted[0][1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stderr", [b"", b"bwrap: unable to create network namespace\n"]
)
async def test_search_exit_one_distinguishes_no_matches_from_startup_failure(
    monkeypatch, tmp_path: Path, stderr: bytes
):
    from astrbot.core.astr_agent_runtime.computer.booters import local

    sandbox = SimpleNamespace(
        run=lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stdout=b"", stderr=stderr
        )
    )
    monkeypatch.setattr(local.sys, "version_info", (3, 14))
    monkeypatch.setattr(local.shutil, "which", lambda _name: "/usr/bin/rg")
    monkeypatch.setattr(local, "create_process_sandbox", lambda: sandbox)
    result = await local.LocalFileSystemComponent().search_files(
        "needle", sandboxed=True, sandbox_root=str(tmp_path)
    )
    if stderr:
        assert result == {
            "success": False,
            "content": "",
            "error": stderr.decode().strip(),
            "exit_code": 1,
        }
    else:
        assert result == {"success": True, "content": ""}
