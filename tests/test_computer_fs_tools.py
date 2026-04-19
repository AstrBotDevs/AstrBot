from __future__ import annotations

import base64
import io
import zipfile
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.types import CallToolResult, ImageContent
from PIL import Image

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.computer import file_read_utils
from astrbot.core.computer.booters.local import LocalBooter
from astrbot.core.tools.computer_tools import fs as fs_tools
from astrbot.core.tools.computer_tools import util as computer_util


def _make_context(
    *,
    require_admin: bool = True,
    role: str = "admin",
    runtime: str = "local",
    umo: str = "qq:friend:user-1",
) -> ContextWrapper:
    config_holder = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {
                "computer_use_require_admin": require_admin,
                "computer_use_runtime": runtime,
            }
        }
    )
    event = SimpleNamespace(
        role=role,
        unified_msg_origin=umo,
        get_sender_id=lambda: "user-1",
    )
    astr_ctx = SimpleNamespace(context=config_holder, event=event)
    return ContextWrapper(context=astr_ctx)


def _setup_local_fs_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    umo: str = "qq:friend:user-1",
) -> Any:
    workspaces_root = tmp_path / "workspaces"
    skills_root = tmp_path / "skills"
    temp_root = tmp_path / "temp"
    workspaces_root.mkdir()
    skills_root.mkdir()
    temp_root.mkdir()

    monkeypatch.setattr(
        computer_util,
        "get_astrbot_workspaces_path",
        lambda: str(workspaces_root),
    )
    monkeypatch.setattr(
        fs_tools,
        "get_astrbot_skills_path",
        lambda: str(skills_root),
    )
    monkeypatch.setattr(
        fs_tools,
        "get_astrbot_temp_path",
        lambda: str(temp_root),
    )
    monkeypatch.setattr(
        file_read_utils,
        "get_astrbot_temp_path",
        lambda: str(temp_root),
    )

    booter = LocalBooter()

    async def _fake_get_booter(_ctx, _umo):
        return booter

    monkeypatch.setattr(fs_tools, "get_booter", _fake_get_booter)

    normalized_umo = computer_util.normalize_umo_for_workspace(umo)
    workspace = workspaces_root / normalized_umo
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _make_large_text() -> str:
    return "".join(f"line-{index:05d}-{'x' * 48}\n" for index in range(6000))


def test_detect_text_encoding_allows_utf8_probe_cut_mid_character():
    sample = '{"results": ["中文内容"]}'.encode()[:-1]

    assert file_read_utils.detect_text_encoding(sample) in {"utf-8", "utf-8-sig"}


@pytest.mark.asyncio
async def test_file_read_tool_rejects_large_full_text_read_before_local_stream_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    large_file = workspace / "large.txt"
    large_file.write_text(_make_large_text(), encoding="utf-8")

    async def _unexpected_read(*args, **kwargs):
        raise AssertionError("full file read should be rejected before streaming")

    monkeypatch.setattr(file_read_utils, "read_local_text_range", _unexpected_read)

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="large.txt",
    )

    assert "text file exceeds 262144 bytes" in result
    assert "Use `offset` and `limit`" in result


@pytest.mark.asyncio
async def test_file_read_tool_allows_partial_read_for_large_text_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    large_file = workspace / "large.txt"
    lines = [f"line-{index:05d}\n" for index in range(50000)]
    large_file.write_text("".join(lines), encoding="utf-8")

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="large.txt",
        offset=1000,
        limit=3,
    )

    assert result == "".join(lines[1000:1003])


@pytest.mark.asyncio
async def test_file_read_tool_returns_image_call_tool_result_for_images(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    image_path = workspace / "sample.png"
    Image.new("RGB", (32, 16), color=(255, 0, 0)).save(image_path, format="PNG")

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="sample.png",
    )

    assert isinstance(result, CallToolResult)
    assert len(result.content) == 1
    assert isinstance(result.content[0], ImageContent)
    assert result.content[0].mimeType == "image/jpeg"
    assert base64.b64decode(result.content[0].data).startswith(b"\xff\xd8\xff")


@pytest.mark.asyncio
async def test_file_read_tool_treats_svg_as_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    svg_path = workspace / "shape.svg"
    svg_text = (
        "<svg xmlns='http://www.w3.org/2000/svg'><rect width='10' height='10'/></svg>"
    )
    svg_path.write_text(svg_text, encoding="utf-8")

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="shape.svg",
    )

    assert result == svg_text


@pytest.mark.asyncio
async def test_file_read_tool_reads_pdf_via_parser(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    pdf_path = workspace / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n")

    async def _fake_parse_pdf(_file_bytes: bytes, _file_name: str) -> str:
        return "page-1\npage-2\n"

    monkeypatch.setattr(file_read_utils, "_parse_local_pdf_text", _fake_parse_pdf)

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="doc.pdf",
    )

    assert result == "page-1\npage-2\n"


@pytest.mark.asyncio
async def test_file_read_tool_reads_docx_via_parser_and_magic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    docx_path = workspace / "report.bin"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    docx_path.write_bytes(buffer.getvalue())

    async def _fake_parse_docx(_file_bytes: bytes, _file_name: str) -> str:
        return "doc-line-1\ndoc-line-2\n"

    monkeypatch.setattr(file_read_utils, "_parse_local_docx_text", _fake_parse_docx)

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="report.bin",
    )

    assert result == "doc-line-1\ndoc-line-2\n"


@pytest.mark.asyncio
async def test_file_read_tool_stores_long_converted_document_in_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    pdf_path = workspace / "manual.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nfake\n")
    long_text = _make_large_text()

    async def _fake_parse_pdf(_file_bytes: bytes, _file_name: str) -> str:
        return long_text

    monkeypatch.setattr(file_read_utils, "_parse_local_pdf_text", _fake_parse_pdf)

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="manual.pdf",
    )

    converted_root = workspace / "converted_files"
    converted_files = list(converted_root.glob("manual.pdf_*/text.txt"))
    assert len(converted_files) == 1
    assert converted_files[0].read_text(encoding="utf-8") == long_text
    assert str(converted_files[0]) in result
    assert "Read or grep that file with a narrow window." in result


@pytest.mark.asyncio
async def test_grep_tool_applies_result_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    text_path = workspace / "grep.txt"
    text_path.write_text(
        "match-1\nmatch-2\nmatch-3\nmatch-4\n",
        encoding="utf-8",
    )

    result = await fs_tools.GrepTool().call(
        _make_context(),
        pattern="match",
        path="grep.txt",
        result_limit=2,
    )

    assert "match-1" in result
    assert "match-2" in result
    assert "match-3" not in result
    assert "[Truncated to first 2 result groups.]" in result
