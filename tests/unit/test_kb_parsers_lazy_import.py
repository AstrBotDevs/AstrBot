from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_importing_parsers_submodules_does_not_eagerly_import_pypdf() -> None:
    script = (
        "import sys\n"
        "import astrbot.core.knowledge_base.parsers\n"
        "import astrbot.core.knowledge_base.parsers.util\n"
        "import astrbot.core.knowledge_base.parsers.url_parser\n"
        "for mod in (\n"
        "    'pypdf',\n"
        "    'astrbot.core.knowledge_base.parsers.pdf_parser',\n"
        "    'astrbot.core.knowledge_base.parsers.epub_parser',\n"
        "    'astrbot.core.knowledge_base.parsers.text_parser',\n"
        "):\n"
        "    assert mod not in sys.modules, f'unexpected eager import: {mod}'\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr or res.stdout


def test_lazy_exports_remain_accessible_and_cached() -> None:
    import astrbot.core.knowledge_base.parsers as parsers
    from astrbot.core.knowledge_base.parsers.base import (
        BaseParser,
        MediaItem,
        ParseResult,
    )
    from astrbot.core.knowledge_base.parsers.epub_parser import EpubParser
    from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser
    from astrbot.core.knowledge_base.parsers.text_parser import TextParser

    assert parsers.BaseParser is BaseParser
    assert parsers.MediaItem is MediaItem
    assert parsers.ParseResult is ParseResult
    assert parsers.PDFParser is PDFParser
    assert parsers.EpubParser is EpubParser
    assert parsers.TextParser is TextParser
    assert "PDFParser" in vars(parsers)
    assert "EpubParser" in vars(parsers)
    assert "TextParser" in vars(parsers)

    with pytest.raises(AttributeError):
        getattr(parsers, "DoesNotExist")
