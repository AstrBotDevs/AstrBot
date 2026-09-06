"""Import smoke tests for the PDF parser module."""

from __future__ import annotations

from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser


class TestPDFParserImports:
    """Verify that the main class from pdf_parser can be imported."""

    def test_import_pdf_parser(self):
        assert PDFParser is not None
        assert hasattr(PDFParser, "parse")
