#!/usr/bin/env python3
"""Render a DOCX to page PNGs through LibreOffice and Poppler."""

from __future__ import annotations

from pathlib import Path

if __package__:
    from astrbot.builtin_stars.astrbot.skills._astrbot_skill_support.cli import (
        run_renderer,
    )
    from astrbot.builtin_stars.astrbot.skills._astrbot_skill_support.office import (
        render_office_document,
    )
else:
    from _astrbot_skill_support.cli import run_renderer
    from _astrbot_skill_support.office import render_office_document


def render_docx(
    input_path: Path, output_dir: Path, *, dpi: int, emit_pdf: bool
) -> list[Path]:
    """Render page images while preserving the document-specific temporary prefix."""
    return render_office_document(
        input_path,
        output_dir,
        dpi=dpi,
        emit_pdf=emit_pdf,
        temp_prefix="astrbot-docx-render-",
    )


def main() -> int:
    """Validate command-line options and render the requested document."""
    return run_renderer(
        render_docx,
        description=__doc__ or "",
        input_help="DOCX input",
        input_suffix=".docx",
    )


if __name__ == "__main__":
    raise SystemExit(main())
