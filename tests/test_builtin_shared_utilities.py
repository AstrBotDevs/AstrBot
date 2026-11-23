"""Shared skill helpers preserve standalone execution and conversion boundaries."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader, PdfWriter

from astrbot.builtin_stars.astrbot.skills._astrbot_skill_support import office
from astrbot.builtin_stars.astrbot.skills._astrbot_skill_support.csv_data import (
    parse_delimited_rows,
)
from astrbot.builtin_stars.astrbot.skills.documents.scripts.render_docx import (
    render_docx,
)
from astrbot.builtin_stars.astrbot.skills.spreadsheets.scripts.render_workbook import (
    render_workbook,
)

SKILLS_ROOT = (
    Path(__file__).resolve().parents[1] / "astrbot/builtin_stars/astrbot/skills"
)


@pytest.fixture
def standalone_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "uploaded-skills"
    for name in ("_astrbot_skill_support", "documents", "spreadsheets", "pdf"):
        shutil.copytree(
            SKILLS_ROOT / name,
            bundle / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    return bundle


def _run_script(bundle: Path, relative: str, *arguments: Path | str):
    return subprocess.run(
        [
            sys.executable,
            "-E",
            "-X",
            "utf8",
            str(bundle / relative),
            *(str(argument) for argument in arguments),
        ],
        cwd=bundle,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def test_uploaded_skills_run_from_an_unrelated_directory(standalone_bundle: Path):
    bundle = standalone_bundle
    document = Document()
    document.add_paragraph("Standalone 文档")
    source_docx = bundle / "sample.docx"
    document.save(source_docx)
    inspected = _run_script(bundle, "documents/scripts/inspect_docx.py", source_docx)
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)["paragraph_sample"] == [
        {"style": "Normal", "text": "Standalone 文档"}
    ]

    source_csv = bundle / "sample.tsv"
    source_csv.write_text("ID\tAmount\n001\t23.5\n", encoding="utf-8")
    output_xlsx = bundle / "sample.xlsx"
    converted = _run_script(
        bundle, "spreadsheets/scripts/csv_to_xlsx.py", source_csv, output_xlsx
    )
    assert converted.returncode == 0, converted.stderr
    workbook = load_workbook(output_xlsx)
    try:
        assert workbook.active["A2"].value == "001"
        assert workbook.active["B2"].value == 23.5
    finally:
        workbook.close()

    markdown = bundle / "sample.md"
    markdown.write_text(
        "# Standalone PDF\n\nContent survives upload.\n", encoding="utf-8"
    )
    output_pdf = bundle / "sample.pdf"
    converted = _run_script(
        bundle, "pdf/scripts/markdown_to_pdf.py", markdown, output_pdf
    )
    assert converted.returncode == 0, converted.stderr
    assert "Content survives upload." in PdfReader(output_pdf).pages[0].extract_text()


@pytest.mark.parametrize(
    ("script", "suffix"),
    [
        ("documents/scripts/render_docx.py", ".docx"),
        ("spreadsheets/scripts/render_workbook.py", ".xlsx"),
    ],
)
def test_standalone_renderers_validate_dpi_before_conversion(
    standalone_bundle: Path, script: str, suffix: str
):
    source = standalone_bundle / f"input{suffix}"
    source.write_bytes(b"Not an office document; validation must precede rendering.")
    destination = standalone_bundle / "pages"
    result = _run_script(standalone_bundle, script, source, destination, "--dpi", "71")
    assert result.returncode == 2
    assert "DPI must be between 72 and 600." in result.stderr
    assert not destination.exists()


@pytest.mark.parametrize("renderer", [render_docx, render_workbook])
@pytest.mark.parametrize("complete", [True, False])
def test_rendering_replaces_old_pages_only_after_all_pages_are_available(
    monkeypatch, tmp_path: Path, renderer, complete: bool
):
    source = tmp_path / "source.office"
    source.write_bytes(b"original document")
    destination = tmp_path / "pages"
    destination.mkdir()
    old_page = destination / "source-page-9.png"
    old_page.write_bytes(b"previous successful output")
    monkeypatch.setattr(office, "_find_soffice", lambda: Path("/tools/soffice"))
    monkeypatch.setattr(
        office,
        "shutil",
        SimpleNamespace(which=lambda command: "/tools/pdftoppm", copy2=shutil.copy2),
    )

    def run_tool(command, **options):
        if command[0] == "/tools/soffice":
            temporary = Path(command[command.index("--outdir") + 1])
            assert Path(options["env"]["TMPDIR"]) == temporary
            writer = PdfWriter()
            for _ in range(2):
                writer.add_blank_page(width=100, height=100)
            writer.write(temporary / "source.pdf")
        else:
            prefix = Path(command[-1])
            for page in range(1, 3 if complete else 2):
                prefix.with_name(f"page-{page}.png").write_bytes(
                    f"image {page}".encode()
                )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(office, "subprocess", SimpleNamespace(run=run_tool))
    if complete:
        pages = renderer(source, destination, dpi=144, emit_pdf=True)
        assert [page.name for page in pages] == [
            "source-page-1.png",
            "source-page-2.png",
        ]
        assert [page.read_bytes() for page in pages] == [b"image 1", b"image 2"]
        assert len(PdfReader(destination / "source.pdf").pages) == 2
        assert not old_page.exists()
    else:
        with pytest.raises(RuntimeError, match="Expected 2 rendered pages, found 1"):
            renderer(source, destination, dpi=144, emit_pdf=True)
        assert list(destination.iterdir()) == [old_page]
        assert old_page.read_bytes() == b"previous successful output"
    assert source.read_bytes() == b"original document"


@pytest.mark.parametrize(
    ("text", "suffix", "override", "delimiter", "rows"),
    [
        ('name|value\n"a|b"|5\n', ".csv", None, "|", [["name", "value"], ["a|b", "5"]]),
        ("a,b;c,d\n", ".csv", ";", ";", [["a,b", "c,d"]]),
        ("column\nrow\n", ".TSV", None, "\t", [["column"], ["row"]]),
        ("", ".csv", None, ",", []),
    ],
)
def test_delimited_data_preserves_quoting_overrides_and_extension_fallback(
    text, suffix, override, delimiter, rows
):
    assert parse_delimited_rows(text, suffix=suffix, delimiter=override) == (
        delimiter,
        rows,
    )
