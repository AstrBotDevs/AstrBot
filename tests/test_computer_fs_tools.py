from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.types import CallToolResult, ImageContent
from PIL import Image

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.computer.booters.local import LocalBooter
from astrbot.core.computer.tools import fs as fs_tools
from astrbot.core.computer.tools.tool_utils import file_read as file_read_utils


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
        fs_tools,
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

    normalized_umo = fs_tools._normalize_umo_for_workspace(umo)
    workspace = workspaces_root / normalized_umo
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _make_large_text() -> str:
    return "".join(f"line-{index:05d}-{'x' * 48}\n" for index in range(6000))


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

    monkeypatch.setattr(file_read_utils, "_read_local_text_range", _unexpected_read)

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
async def test_file_read_tool_rejects_pdf_as_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    pdf_path = workspace / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n")

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="doc.pdf",
    )

    assert result == "Error reading file: binary files are not supported by this tool."


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
