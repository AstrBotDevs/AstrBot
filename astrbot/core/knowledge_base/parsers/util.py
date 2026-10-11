from .base import BaseParser


async def select_parser(ext: str) -> BaseParser:
    if ext in {".md", ".txt", ".markdown"}:
        # Plain text formats are decoded directly by TextParser and do not
        # require the optional markitdown dependency. Routing them here keeps
        # txt/md uploads working even when markitdown-no-magika is missing
        # (see https://github.com/AstrBotDevs/AstrBot/issues/9598).
        from .text_parser import TextParser

        return TextParser()
    if ext in {".rst", ".adoc", ".xlsx", ".docx", ".xls"}:
        from .markitdown_parser import MarkitdownParser

        return MarkitdownParser()
    if ext == ".epub":
        from .epub_parser import EpubParser

        return EpubParser()
    if ext == ".pdf":
        from .pdf_parser import PDFParser

        return PDFParser()
    raise ValueError(f"暂时不支持的文件格式: {ext}")
