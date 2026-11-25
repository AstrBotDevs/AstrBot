"""文档解析器模块"""

from typing import TYPE_CHECKING

from .base import BaseParser, MediaItem, ParseResult

if TYPE_CHECKING:
    from .epub_parser import EpubParser
    from .pdf_parser import PDFParser
    from .text_parser import TextParser

__all__ = [
    "BaseParser",
    "EpubParser",
    "MediaItem",
    "PDFParser",
    "ParseResult",
    "TextParser",
]

_LAZY_EXPORTS = {
    "EpubParser": (".epub_parser", "EpubParser"),
    "PDFParser": (".pdf_parser", "PDFParser"),
    "TextParser": (".text_parser", "TextParser"),
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        import importlib

        module_name, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_name, __name__)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
