from .base import BaseParser


async def select_parser(ext: str) -> BaseParser:
    # Markdown variants that the MarkdownChunker whitelist in kb_helper
    # already accepts; parse them as plain text without extra dependencies.
    if ext in {".mdx", ".mkd"}:
        from .text_parser import TextParser

        return TextParser()
    # Formats supported by markitdown-no-magika (verified converters:
    # HtmlConverter, CsvConverter, PlainTextConverter; note it has no
    # RTF converter, so .rtf stays unsupported).
    if ext in {
        ".csv",
        ".html",
        ".htm",
        ".md",
        ".txt",
        ".markdown",
        ".rst",
        ".adoc",
        ".xlsx",
        ".docx",
        ".xls",
    }:
        from .markitdown_parser import MarkitdownParser

        return MarkitdownParser()
    if ext == ".epub":
        from .epub_parser import EpubParser

        return EpubParser()
    if ext == ".pdf":
        from .pdf_parser import PDFParser

        return PDFParser()
    raise ValueError(f"暂时不支持的文件格式: {ext}")
