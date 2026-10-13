from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader

PDF_SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / "astrbot"
    / "builtin_stars"
    / "astrbot"
    / "skills"
    / "pdf"
)
CONVERTER = PDF_SKILL_DIR / "scripts" / "markdown_to_pdf.py"


def test_builtin_pdf_skill_converts_limited_markdown(tmp_path: Path) -> None:
    source = tmp_path / "sample.md"
    output = tmp_path / "sample.pdf"
    source.write_text(
        "# AstrBot PDF 测试\n\n"
        "这是一个 **受限 Markdown** 转换测试，包含 `inline_code()` 和 "
        "[AstrBot](https://astrbot.app)。\n\n"
        "- 第一项\n"
        "- 第二项\n\n"
        "> 引用内容需要保持清晰。\n\n"
        "```python\n"
        "print('hello')\n"
        "```\n\n"
        "<!-- pagebreak -->\n\n"
        "## 第二页\n\n"
        "分页后的正文。\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(CONVERTER), str(source), str(output)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    reader = PdfReader(output)
    assert len(reader.pages) == 2
    assert reader.metadata is not None
    assert reader.metadata.title == "AstrBot PDF 测试"
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "AstrBot PDF" in extracted
    assert "受限 Markdown" in extracted
    assert "print('hello')" in extracted
    assert "第二页" in extracted
    assert "/OpenAction" not in reader.trailer["/Root"]


def test_builtin_pdf_skill_rejects_unsupported_default_font_character(
    tmp_path: Path,
) -> None:
    source = tmp_path / "emoji.md"
    output = tmp_path / "emoji.pdf"
    source.write_text("# Unsupported emoji 😀\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(CONVERTER), str(source), str(output)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Pass --font" in result.stderr
    assert not output.exists()


def test_builtin_pdf_skill_documents_system_and_downloaded_fonts() -> None:
    skill = (PDF_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "search common system locations" in skill
    assert "--font path/to/font.ttf" in skill
    assert "https://hyperos.mi.com/font/zh/download/" in skill
    assert "https://github.com/notofonts/noto-cjk/" in skill
    assert "https://edgeone.gh-proxy.com/https://github.com/" in skill
    assert "https://hk.gh-proxy.com/" in skill
    assert "https://gh-proxy.com/" in skill
    assert "https://gh.dpik.top/" in skill
    assert "Never send credentials" in skill
