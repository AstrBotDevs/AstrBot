#!/usr/bin/env python3
"""Render office documents to page PNGs through LibreOffice and Poppler."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader


def _find_soffice() -> Path | None:
    """Locate a LibreOffice command.

    Returns:
        Executable path when found, otherwise None.
    """
    for command in ("soffice", "libreoffice"):
        if executable := shutil.which(command):
            return Path(executable)
    candidates = (
        Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
        / "LibreOffice"
        / "program"
        / "soffice.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
        / "LibreOffice"
        / "program"
        / "soffice.exe",
    )
    return next((path for path in candidates if path.is_file()), None)


def render_office_document(
    input_path: Path,
    output_dir: Path,
    *,
    dpi: int,
    emit_pdf: bool,
    temp_prefix: str,
) -> list[Path]:
    """Render office document pages to PNG files.

    Args:
        input_path: Input office document.
        output_dir: Destination directory.
        dpi: Raster resolution.
        emit_pdf: Whether to retain the intermediate PDF.
        temp_prefix: Prefix identifying the document type in temporary directories.

    Returns:
        Rendered PNG paths.

    Raises:
        RuntimeError: If a required renderer is missing or conversion fails.
    """
    soffice = _find_soffice()
    if soffice is None:
        raise RuntimeError(
            "LibreOffice/soffice was not found; visual QA is unavailable."
        )
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is None:
        raise RuntimeError(
            "pdftoppm was not found; install Poppler to render page PNGs."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix=temp_prefix) as temp_name:
        temp_dir = Path(temp_name)
        profile = temp_dir / "profile"
        profile.mkdir()
        environment = os.environ.copy()
        environment["TMPDIR"] = str(temp_dir)
        if "FONTCONFIG_FILE" not in environment:
            for fontconfig_file in (
                Path("/opt/homebrew/etc/fonts/fonts.conf"),
                Path("/usr/local/etc/fonts/fonts.conf"),
                Path("/etc/fonts/fonts.conf"),
            ):
                if fontconfig_file.is_file():
                    environment["FONTCONFIG_FILE"] = str(fontconfig_file)
                    break
        converted = subprocess.run(
            [
                str(soffice),
                "--headless",
                f"-env:UserInstallation={profile.resolve().as_uri()}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp_dir),
                str(input_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        pdf_path = temp_dir / f"{input_path.stem}.pdf"
        if converted.returncode != 0 or not pdf_path.is_file():
            details = (converted.stderr or converted.stdout).strip()
            raise RuntimeError(f"LibreOffice conversion failed: {details}")
        reader = PdfReader(pdf_path)
        if not reader.pages:
            raise RuntimeError("LibreOffice produced a PDF with no pages.")

        raster_dir = temp_dir / "raster"
        raster_dir.mkdir()
        prefix = raster_dir / "page"
        rendered = subprocess.run(
            [pdftoppm, "-png", "-r", str(dpi), str(pdf_path), str(prefix)],
            check=False,
            capture_output=True,
            text=True,
        )
        if rendered.returncode != 0:
            raise RuntimeError(f"PDF rasterization failed: {rendered.stderr.strip()}")
        temporary_pages = sorted(raster_dir.glob("page-*.png"))
        if len(temporary_pages) != len(reader.pages):
            raise RuntimeError(
                "Expected "
                f"{len(reader.pages)} rendered pages, found {len(temporary_pages)}."
            )
        for old_page in output_dir.glob(f"{input_path.stem}-page-*.png"):
            old_page.unlink()
        pages = []
        for index, temporary_page in enumerate(temporary_pages, start=1):
            page = output_dir / f"{input_path.stem}-page-{index}.png"
            shutil.copy2(temporary_page, page)
            pages.append(page)
        if emit_pdf:
            shutil.copy2(pdf_path, output_dir / f"{input_path.stem}.pdf")
    return pages
