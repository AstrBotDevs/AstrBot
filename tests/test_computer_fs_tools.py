from __future__ import annotations

import base64
import io
import os
import re
import zipfile
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

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


def _make_sandbox_context(
    *,
    role: str = "admin",
    umo: str = "qq:friend:user-1",
):
    config_holder = SimpleNamespace(
        get_config=lambda umo=None: {
            "provider_settings": {
                "computer_use_require_admin": True,
                "computer_use_runtime": "sandbox",
            }
        }
    )
    event = SimpleNamespace(
        role=role,
        unified_msg_origin=umo,
        send=AsyncMock(),
    )
    astr_ctx = SimpleNamespace(context=config_holder, event=event)
    return ContextWrapper(context=astr_ctx)


@pytest.mark.asyncio
async def test_sandbox_file_download_handles_windows_remote_filename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    temp_root = tmp_path / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        fs_tools,
        "get_astrbot_temp_path",
        lambda: str(temp_root),
    )

    async def _download_file(_remote_path, local_path):
        assert local_path.endswith("report.txt")
        assert "\\" not in local_path

    booter = SimpleNamespace(download_file=AsyncMock(side_effect=_download_file))

    async def _fake_get_booter(_ctx, _umo):
        return booter

    monkeypatch.setattr(fs_tools, "get_booter", _fake_get_booter)

    context = _make_sandbox_context()
    result = await fs_tools.FileDownloadTool().call(
        context,
        remote_path=r"C:\Users\AstrBot\report.txt",
        also_send_to_user=True,
    )

    assert "report.txt" in result
    sent_chain = context.context.event.send.await_args.args[0]
    sent_file = sent_chain.chain[0]
    assert sent_file.name == "report.txt"


@pytest.mark.asyncio
async def test_sandbox_file_download_strips_trailing_remote_slash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    temp_root = tmp_path / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        fs_tools,
        "get_astrbot_temp_path",
        lambda: str(temp_root),
    )

    booter = SimpleNamespace(download_file=AsyncMock())

    async def _fake_get_booter(_ctx, _umo):
        return booter

    monkeypatch.setattr(fs_tools, "get_booter", _fake_get_booter)

    context = _make_sandbox_context()
    result = await fs_tools.FileDownloadTool().call(
        context,
        remote_path="reports/export/",
        also_send_to_user=True,
    )

    assert "export" in result
    sent_chain = context.context.event.send.await_args.args[0]
    sent_file = sent_chain.chain[0]
    assert sent_file.name == "export"


def _setup_local_fs_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    umo: str = "qq:friend:user-1",
) -> Any:
    workspaces_root = tmp_path / "workspaces"
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    temp_root = tmp_path / "temp"
    workspaces_root.mkdir()
    skills_root.mkdir()
    plugins_root.mkdir()
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
        "get_astrbot_plugin_path",
        lambda: str(plugins_root),
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


def _make_hardlink_or_skip(source, link) -> None:
    try:
        os.link(source, link)
    except (AttributeError, OSError) as exc:
        pytest.skip(f"hard links are unavailable on this filesystem: {exc}")


def _make_epub_bytes(*, chapter_count: int = 1) -> bytes:
    manifest_items = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
    ]
    spine_items = ['<itemref idref="nav"/>']
    nav_links = []

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )

        for index in range(1, chapter_count + 1):
            manifest_items.append(
                f'<item id="chapter{index}" href="chapter{index}.xhtml" '
                'media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="chapter{index}"/>')
            nav_links.append(
                f'<li><a href="chapter{index}.xhtml">Chapter {index}</a></li>'
            )
            archive.writestr(
                f"OEBPS/chapter{index}.xhtml",
                f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Chapter {index}</title>
  </head>
  <body>
    <h1>Chapter {index}</h1>
    <p>Paragraph {index}</p>
  </body>
</html>
""",
            )

        archive.writestr(
            "OEBPS/nav.xhtml",
            """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Navigation</title>
  </head>
  <body>
    <nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops">
      <ol>
        {links}
      </ol>
    </nav>
  </body>
</html>
""".format(links="".join(nav_links)),
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">test-book</dc:identifier>
    <dc:title>Test Book</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    {manifest}
  </manifest>
  <spine>
    {spine}
  </spine>
</package>
""".format(
                manifest="".join(manifest_items),
                spine="".join(spine_items),
            ),
        )

    return buffer.getvalue()


@pytest.mark.asyncio
async def test_restricted_local_member_can_read_plugin_provided_skill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    _setup_local_fs_tools(monkeypatch, tmp_path)
    plugin_skill = (
        tmp_path
        / "plugins"
        / "astrbot_plugin_demo"
        / "skills"
        / "demo-skill"
        / "SKILL.md"
    )
    plugin_skill.parent.mkdir(parents=True)
    plugin_skill.write_text("# Demo Skill\n\nRead plugin docs.", encoding="utf-8")

    result = await fs_tools.FileReadTool().call(
        _make_context(role="member"),
        path=str(plugin_skill),
    )

    assert result == "# Demo Skill\n\nRead plugin docs."


@pytest.mark.asyncio
async def test_restricted_local_member_can_read_plugin_skill_inventory_even_if_plugin_inactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    _setup_local_fs_tools(monkeypatch, tmp_path)
    plugin_skill = (
        tmp_path
        / "plugins"
        / "astrbot_plugin_demo"
        / "skills"
        / "demo-skill"
        / "SKILL.md"
    )
    plugin_skill.parent.mkdir(parents=True)
    plugin_skill.write_text("# Demo Skill\n", encoding="utf-8")

    result = await fs_tools.FileReadTool().call(
        _make_context(role="member"),
        path=str(plugin_skill),
    )

    assert result == "# Demo Skill\n"


@pytest.mark.asyncio
async def test_restricted_local_member_cannot_write_plugin_provided_skill(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    _setup_local_fs_tools(monkeypatch, tmp_path)
    plugin_skill = (
        tmp_path
        / "plugins"
        / "astrbot_plugin_demo"
        / "skills"
        / "demo-skill"
        / "SKILL.md"
    )
    plugin_skill.parent.mkdir(parents=True)
    plugin_skill.write_text("# Demo Skill\n", encoding="utf-8")

    result = await fs_tools.FileWriteTool().call(
        _make_context(role="member"),
        path=str(plugin_skill),
        content="# Changed\n",
    )

    assert "Write access is restricted for this user." in result
    assert "data/plugins/*/skills" not in result
    assert plugin_skill.read_text(encoding="utf-8") == "# Demo Skill\n"


@pytest.mark.asyncio
async def test_restricted_local_member_rejects_workspace_hardlink_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "secret.txt"
    outside_file.write_text("outside-secret\n", encoding="utf-8")
    hardlink_path = workspace / "linked.txt"
    _make_hardlink_or_skip(outside_file, hardlink_path)

    read_result = await fs_tools.FileReadTool().call(
        _make_context(role="member"),
        path="linked.txt",
    )
    write_result = await fs_tools.FileWriteTool().call(
        _make_context(role="member"),
        path="linked.txt",
        content="changed\n",
    )

    assert "multiple hard links" in read_result
    assert "may alias content outside allowed directories" in read_result
    assert "multiple hard links" in write_result
    assert "may alias content outside allowed directories" in write_result
    assert outside_file.read_text(encoding="utf-8") == "outside-secret\n"


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


def test_is_epub_bytes_rejects_plain_zip_archive():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr("README.txt", "hello")

    assert file_read_utils._is_epub_bytes(buffer.getvalue()) is False


@pytest.mark.asyncio
async def test_file_read_tool_reads_epub_via_parser_and_magic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    workspace = _setup_local_fs_tools(monkeypatch, tmp_path)
    epub_path = workspace / "novel.bin"
    epub_path.write_bytes(_make_epub_bytes(chapter_count=2))

    async def _fake_parse_epub(_file_bytes: bytes, _file_name: str) -> str:
        return "# Chapter 1\n\nParagraph 1\n"

    monkeypatch.setattr(file_read_utils, "_parse_local_epub_text", _fake_parse_epub)

    result = await fs_tools.FileReadTool().call(
        _make_context(),
        path="novel.bin",
    )

    assert result == "# Chapter 1\n\nParagraph 1\n"


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


# ---------------------------------------------------------------------------
# Python AST safety net for astrbot_file_edit_tool
# ---------------------------------------------------------------------------


class _StubHistoryManager:
    """No-op history manager for tests (no backup persistence)."""

    def save_backup(self, *_args, **_kwargs):
        return None


def _setup_local_edit_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    workspace_subdir: str = "",
):
    """Patch workspace/temp paths so FileEditTool operates inside tmp_path.

    Returns the actual workspace root the tool will use. The tool itself
    appends the UMO-derived subdirectory (``qq_friend_user-1`` for the
    default test UMO ``qq:friend:user-1``) to whatever base path this
    function provides to ``get_astrbot_workspaces_path``.
    """
    workspace_base = tmp_path / "workspaces"
    workspace_base.mkdir(parents=True, exist_ok=True)
    temp_root = tmp_path / "temp"
    temp_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        fs_tools, "get_astrbot_workspaces_path", lambda: str(workspace_base)
    )
    monkeypatch.setattr(fs_tools, "get_astrbot_temp_path", lambda: str(temp_root))

    actual_root = workspace_base / "qq_friend_user-1"
    if workspace_subdir:
        actual_root = actual_root / workspace_subdir
    actual_root.mkdir(parents=True, exist_ok=True)
    return actual_root


def test_is_python_file_matches_py_suffix_case_insensitive():
    assert fs_tools._is_python_file("foo.py") is True
    assert fs_tools._is_python_file("foo.PY") is True
    assert fs_tools._is_python_file("path/to/foo.Py") is True
    assert fs_tools._is_python_file("foo.txt") is False
    assert fs_tools._is_python_file("foo.py.bak") is False
    assert fs_tools._is_python_file("foo") is False


# ---------------------------------------------------------------------------
# Path-display regex contract (frontend ↔ backend)
# ---------------------------------------------------------------------------
#
# The frontend's `editToolFilePath` (in ToolCallCard.vue) extracts the file
# path from the tool's result string. The regex used there is mirrored here
# in Python so we can lock down the contract that both sides depend on. If
# the backend format or the frontend regex changes, this test must be
# updated in lockstep.


# Frontend regex (mirrored in Python for testing).
# The JavaScript source is in ToolCallCard.vue → editToolFilePath computed.
_FRONTEND_SUCCESS_REGEX = re.compile(r"^Edited\s+(.+?)\.\s+Replaced", re.MULTILINE)
_FRONTEND_ERROR_REGEX = re.compile(r"^Error editing file:\s*\[(.+?)\]:")

# The previously broken regexes — kept here as a regression guard so we can
# prove the old behavior would have failed.
_OLD_BROKEN_SUCCESS_REGEX = re.compile(r"^Edited\s+(.+?)\.", re.MULTILINE)
_OLD_BROKEN_ERROR_REGEX = re.compile(r"^Error editing file:\s*(.+?):", re.MULTILINE)


def test_edit_tool_error_regex_extracts_windows_style_path():
    """The error message wraps the path in `[...]` so the frontend regex
    can extract it even when the path contains colons (Windows drive
    letters, e.g. ``D:\\AstrbotWorkSpace\\test.py``).

    The old format (``Error editing file: {path}: ...``) + old regex
    (``(.+?):``) is also exercised here to prove that the fix was
    necessary — without brackets, the regex truncates the path at the
    colon in the drive letter.
    """
    new_format = (
        "Error editing file: [D:\\AstrbotWorkSpace\\test.py]: "
        "Python syntax validation failed after edit. "
        "No changes were written. "
        "IndentationError at line 3, column 12: unexpected indent."
    )

    # New format + new regex extracts the full path
    match = _FRONTEND_ERROR_REGEX.match(new_format)
    assert match is not None
    assert match.group(1) == "D:\\AstrbotWorkSpace\\test.py"

    # Old format + old regex truncates at the drive-letter colon — this
    # is the exact bug the user reported. Keeping this assertion as a
    # regression guard so a future refactor cannot silently reintroduce
    # the issue.
    old_format = (
        "Error editing file: D:\\AstrbotWorkSpace\\test.py: "
        "Python syntax validation failed after edit."
    )
    broken = _OLD_BROKEN_ERROR_REGEX.match(old_format)
    assert broken is not None
    assert broken.group(1) == "D", (
        "Regression guard: the old regex + old format must still "
        "truncate the path to 'D' for this test to prove the fix is "
        "necessary."
    )


def test_edit_tool_error_regex_extracts_posix_style_path():
    """POSIX-style paths (no colons) must continue to work."""
    error_msg = (
        "Error editing file: [/home/user/test.py]: "
        "Python syntax validation failed after edit."
    )
    match = _FRONTEND_ERROR_REGEX.match(error_msg)
    assert match is not None
    assert match.group(1) == "/home/user/test.py"


def test_edit_tool_success_regex_extracts_windows_style_path():
    """The success message ends with ``Replaced {N} occurrence(s)...``,
    which the regex anchors on so it is not truncated by a period inside
    the path (e.g. ``.py`` on ``D:\\...\\test.py``).

    The old regex (``(.+?)\\.``) is exercised here against a path
    containing ``.py`` to prove the bug it would have caused: the
    captured group would be the path with ``.py`` stripped off.
    """
    success_msg = (
        "Edited D:\\AstrbotWorkSpace\\test.py.\n"
        "Replaced 1 occurrence(s) using first match mode."
    )

    # New (fixed) regex extracts the full path
    match = _FRONTEND_SUCCESS_REGEX.match(success_msg)
    assert match is not None
    assert match.group(1) == "D:\\AstrbotWorkSpace\\test.py"

    # Old (broken) regex truncates at the first period inside the path
    # — this is the bug the new regex fixes. Keeping it as a regression
    # guard.
    broken = _OLD_BROKEN_SUCCESS_REGEX.match(success_msg)
    assert broken is not None
    assert broken.group(1) == "D:\\AstrbotWorkSpace\\test", (
        "Regression guard: the old regex must still drop '.py' for this "
        "test to prove the fix is necessary."
    )


def test_edit_tool_success_regex_extracts_posix_style_path():
    """POSIX-style paths must continue to work."""
    success_msg = (
        "Edited /home/user/test.py.\nReplaced 1 occurrence(s) using first match mode."
    )
    match = _FRONTEND_SUCCESS_REGEX.match(success_msg)
    assert match is not None
    assert match.group(1) == "/home/user/test.py"


def test_edit_tool_error_regex_returns_none_for_unrecognized_format():
    """Both regexes must return None (frontend falls back to empty path)
    when the result doesn't match the expected format."""
    assert _FRONTEND_SUCCESS_REGEX.match("Some other output") is None
    assert _FRONTEND_ERROR_REGEX.match("Some other output") is None
    # Old format (no brackets) is not matched by the new error regex
    assert _FRONTEND_ERROR_REGEX.match("Error editing file: foo.py: bar") is None


def test_validate_python_ast_returns_none_for_valid_code():
    assert fs_tools._validate_python_ast("def foo():\n    return 1\n") is None
    assert fs_tools._validate_python_ast("") is None
    assert fs_tools._validate_python_ast("x = 1\n") is None


def test_validate_python_ast_returns_syntax_error_for_invalid_code():
    # Missing closing paren: SyntaxError
    err = fs_tools._validate_python_ast("def foo(:\n")
    assert isinstance(err, SyntaxError)

    # Missing indentation of the function body: IndentationError
    # (note: IndentationError is a subclass of SyntaxError, so isinstance
    # checks against SyntaxError succeed for both)
    err_indent = fs_tools._validate_python_ast("def foo():\nreturn 1\n")
    assert isinstance(err_indent, IndentationError)
    assert isinstance(err_indent, SyntaxError)


@pytest.mark.asyncio
async def test_edit_tool_rejects_indentation_introduced_by_edit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """When a previously valid .py file becomes invalid after the edit, the
    tool must reject the edit and leave the file unchanged."""
    workspace_root = _setup_local_edit_env(monkeypatch, tmp_path)
    target = workspace_root / "module.py"
    original = (
        "class A:\n"
        "    async def initialize(self) -> None:\n"
        '        """Plugin activation."""\n'
        "        self.ready = True\n"
    )
    target.write_text(original, encoding="utf-8")

    old = '    async def initialize(self) -> None:\n        """Plugin activation."""\n'
    # Bad `new` adds 4 extra spaces of indentation, making it invalid.
    new = (
        "    async def initialize(self) -> None:\n"
        '            """Plugin activation."""\n'
    )

    context = _make_context(require_admin=True, role="admin", runtime="local")
    result = await fs_tools.FileEditTool().call(
        context,
        path="module.py",
        old=old,
        new=new,
    )

    # Error message checks
    assert "Python syntax validation failed after edit" in result
    assert "No changes were written" in result
    assert "PREVIEW ONLY" in result
    assert "file was NOT modified" in result
    # The diff block should be present so the LLM can see the rejected diff
    assert "```diff" in result
    # The path should be wrapped in [...] in the error so the frontend
    # regex can extract it even when the path itself contains colons
    # (e.g. Windows drive letters like "D:\...").
    assert f"[{target}]:" in result
    # File must be byte-for-byte unchanged
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_edit_tool_applies_valid_python_edit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """A correct edit on a valid .py file must succeed and update the file."""
    workspace_root = _setup_local_edit_env(monkeypatch, tmp_path)
    target = workspace_root / "module.py"
    target.write_text(
        "class A:\n"
        "    async def initialize(self) -> None:\n"
        "        self.ready = False\n",
        encoding="utf-8",
    )

    old = "        self.ready = False\n"
    new = "        self.ready = True\n"

    context = _make_context(require_admin=True, role="admin", runtime="local")
    result = await fs_tools.FileEditTool().call(
        context,
        path="module.py",
        old=old,
        new=new,
    )

    # Successful path produces the standard "Edited" header
    assert "Edited" in result
    assert "Replaced 1 occurrence" in result
    # File should now have the new content
    assert "self.ready = True" in target.read_text(encoding="utf-8")
    assert "self.ready = False" not in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_edit_tool_allows_repair_of_already_invalid_python_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """If the original .py file is already invalid, the edit should be allowed
    so the tool can be used to repair it. The AST gate only blocks edits that
    would make a *previously valid* file invalid."""
    workspace_root = _setup_local_edit_env(monkeypatch, tmp_path)
    target = workspace_root / "broken.py"
    # Already invalid: bad indent in `def`
    target.write_text(
        "def foo(:\n    return 1\n",
        encoding="utf-8",
    )

    old = "def foo(:\n"
    new = "def foo():\n"

    context = _make_context(require_admin=True, role="admin", runtime="local")
    result = await fs_tools.FileEditTool().call(
        context,
        path="broken.py",
        old=old,
        new=new,
    )

    # Repair must succeed — no AST rejection
    assert "Python syntax validation failed" not in result
    assert "Edited" in result
    assert "def foo():" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_edit_tool_skips_ast_check_for_non_python_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """Non-.py files must not be AST-validated, even if the resulting content
    would not be valid Python."""
    workspace_root = _setup_local_edit_env(monkeypatch, tmp_path)
    target = workspace_root / "config.json"
    target.write_text('{"k": 1}\n', encoding="utf-8")

    # Content here is not valid Python (JSON), but we don't care because the
    # file is not .py — the AST gate must not trigger.
    old = '{"k": 1}\n'
    new = '{"k": 2}\n'

    context = _make_context(require_admin=True, role="admin", runtime="local")
    result = await fs_tools.FileEditTool().call(
        context,
        path="config.json",
        old=old,
        new=new,
    )

    assert "Python syntax validation failed" not in result
    assert "Edited" in result
    assert '{"k": 2}' in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_edit_tool_ast_error_truncates_large_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """The embedded rejected diff must be truncated to keep the error
    message short and avoid blowing the LLM's context window.

    We use very long lines (200+ chars) so that even a single-line edit
    produces a diff of well over 800 characters and the truncation cap
    is actually exercised.
    """
    workspace_root = _setup_local_edit_env(monkeypatch, tmp_path)
    target = workspace_root / "big.py"

    # Build a file with very long lines so the diff exceeds 800 chars.
    padding = "x" * 200
    lines = ["def f():\n", f"    {padding} = 1\n"]
    for i in range(50):
        lines.append(f"    {padding}_{i} = {i}\n")
    target.write_text("".join(lines), encoding="utf-8")

    # Inject a single wrong line near the middle — diff will be ~7 lines
    # of ~200 chars each, well over 800.
    old = f"    {padding}_25 = 25\n"
    new = f"        {padding}_25 = 25\n"

    context = _make_context(require_admin=True, role="admin", runtime="local")
    result = await fs_tools.FileEditTool().call(
        context,
        path="big.py",
        old=old,
        new=new,
    )

    # Truncation marker must appear because the diff exceeds 800 chars
    assert "Python syntax validation failed" in result
    assert "(diff truncated)" in result
    # File must remain unchanged
    assert f"        {padding}_25" not in target.read_text(encoding="utf-8")
    assert f"    {padding}_25 = 25" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_edit_tool_ast_error_message_contains_line_and_column(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """The error message should pinpoint the line/column of the syntax issue
    so the LLM can locate the problem quickly."""
    workspace_root = _setup_local_edit_env(monkeypatch, tmp_path)
    target = workspace_root / "module.py"
    target.write_text(
        "class A:\n"
        "    async def initialize(self) -> None:\n"
        '        """Plugin activation."""\n'
        "        self.ready = True\n",
        encoding="utf-8",
    )

    old = '    async def initialize(self) -> None:\n        """Plugin activation."""\n'
    new = (
        "    async def initialize(self) -> None:\n"
        '            """Plugin activation."""\n'
    )

    context = _make_context(require_admin=True, role="admin", runtime="local")
    result = await fs_tools.FileEditTool().call(
        context,
        path="module.py",
        old=old,
        new=new,
    )

    # The error type and a line/column location must be present
    assert "IndentationError" in result or "SyntaxError" in result
    assert "line " in result
