from astrbot.core.exceptions import KnowledgeBaseUploadError

from .base import BaseParser

# Formats that are plain text by nature and need no external dependency.
_TEXT_PARSER_EXTS = {".md", ".txt", ".markdown"}
# Formats handled by markitdown-no-magika (an optional heavy dependency).
_MARKITDOWN_EXTS = {".rst", ".adoc", ".xlsx", ".docx", ".xls"}

_MARKITDOWN_MISSING_HINT = (
    "文档解析失败：处理该格式需要 markitdown-no-magika 依赖，"
    "请先安装：pip install 'markitdown-no-magika[docx,xls,xlsx]'"
)


async def select_parser(ext: str) -> BaseParser:
    if ext in _TEXT_PARSER_EXTS:
        from .text_parser import TextParser

        return TextParser()
    if ext in _MARKITDOWN_EXTS:
        try:
            from .markitdown_parser import MarkitdownParser
        except ImportError as exc:
            raise KnowledgeBaseUploadError(
                stage="parsing",
                user_message=_MARKITDOWN_MISSING_HINT,
                details={"file_ext": ext},
            ) from exc
        return MarkitdownParser()
    if ext == ".epub":
        from .epub_parser import EpubParser

        return EpubParser()
    if ext == ".pdf":
        from .pdf_parser import PDFParser

        return PDFParser()
    raise ValueError(f"暂时不支持的文件格式: {ext}")
