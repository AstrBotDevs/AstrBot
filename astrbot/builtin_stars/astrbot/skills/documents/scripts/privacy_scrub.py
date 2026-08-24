#!/usr/bin/env python3
"""Remove common authoring metadata from a DOCX copy."""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree

from docx import Document

_CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_DCTERMS = "{http://purl.org/dc/terms/}"
_EP = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _scrub_xml(name: str, content: bytes) -> bytes:
    """Scrub metadata from one OOXML part.

    Args:
        name: Package member path.
        content: Original XML bytes.

    Returns:
        Scrubbed XML bytes.
    """
    root = ElementTree.fromstring(content)
    if name == "docProps/core.xml":
        for tag in (
            f"{_DC}creator",
            f"{_CP}lastModifiedBy",
            f"{_DCTERMS}created",
            f"{_DCTERMS}modified",
            f"{_CP}lastPrinted",
        ):
            element = root.find(tag)
            if element is not None:
                element.text = ""
        revision = root.find(f"{_CP}revision")
        if revision is not None:
            revision.text = "1"
    elif name == "docProps/app.xml":
        for tag in (f"{_EP}Company", f"{_EP}Manager", f"{_EP}HyperlinkBase"):
            element = root.find(tag)
            if element is not None:
                element.text = ""
    elif name == "docProps/custom.xml":
        for child in list(root):
            root.remove(child)
    elif name.startswith("word/"):
        for element in root.iter():
            for attribute in list(element.attrib):
                local_name = attribute.rsplit("}", 1)[-1]
                if local_name.startswith("rsid"):
                    del element.attrib[attribute]
                elif local_name == "author":
                    element.attrib[attribute] = "Author"
                elif local_name == "initials":
                    element.attrib[attribute] = "A"
                elif local_name == "date" and element.tag in {
                    f"{_W}comment",
                    f"{_W}ins",
                    f"{_W}del",
                    f"{_W}moveFrom",
                    f"{_W}moveTo",
                }:
                    del element.attrib[attribute]
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def scrub_docx(input_path: Path, output_path: Path) -> None:
    """Write a metadata-scrubbed DOCX copy.

    Args:
        input_path: Source DOCX.
        output_path: Destination DOCX.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        prefix="astrbot-docx-scrub-",
        suffix=".docx",
        dir=output_path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with (
            zipfile.ZipFile(input_path) as source,
            zipfile.ZipFile(temporary_path, "w") as destination,
        ):
            destination.comment = source.comment
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename.endswith(".xml"):
                    content = _scrub_xml(info.filename, content)
                destination.writestr(info, content)
        Document(temporary_path)
        shutil.move(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def main() -> int:
    """Run the metadata scrubber.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source DOCX")
    parser.add_argument("output", type=Path, help="Destination DOCX")
    args = parser.parse_args()
    input_path = args.input.expanduser().resolve(strict=False)
    output_path = args.output.expanduser().resolve(strict=False)
    if not input_path.is_file():
        parser.error(f"Input file not found: {input_path}")
    if input_path.suffix.lower() != ".docx" or output_path.suffix.lower() != ".docx":
        parser.error("Input and output paths must end with .docx")
    if input_path == output_path:
        parser.error("Input and output paths must be different.")
    try:
        scrub_docx(input_path, output_path)
    except Exception as exc:
        parser.error(str(exc))
    print(f"created: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
