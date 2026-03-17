from .base import BaseParser


async def select_parser(ext: str) -> BaseParser:
    if ext in {".md", ".txt", ".markdown", ".xlsx", ".docx", ".xls"}:
        from .markitdown_parser import MarkitdownParser

        return MarkitdownParser()
    if ext == ".pdf":
        from .pdf_parser import PDFParser

        return PDFParser()
    raise ValueError(f"暂时不支持的文件格式: {ext}")
