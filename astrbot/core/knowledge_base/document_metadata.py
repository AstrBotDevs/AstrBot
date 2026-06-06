"""Helpers for knowledge-base document governance metadata."""

import hashlib
import re
import uuid
from pathlib import Path

from .chunking.base import BaseChunker
from .parsers.base import BaseParser

DEFAULT_PARSER_VERSION = "1"
DEFAULT_CHUNKER_VERSION = "1"


def build_content_hash(content: bytes | str | list[str]) -> str:
    """Return a stable SHA256 hash for source content."""
    digest = hashlib.sha256()
    if isinstance(content, bytes):
        digest.update(content)
    elif isinstance(content, str):
        digest.update(content.encode("utf-8"))
    else:
        for chunk in content:
            digest.update(chunk.encode("utf-8"))
            digest.update(b"\x00")
    return digest.hexdigest()


def get_parser_name(parser: BaseParser | None) -> str | None:
    if parser is None:
        return None
    return parser.__class__.__name__


def get_chunker_name(chunker: BaseChunker | None) -> str | None:
    if chunker is None:
        return None
    return chunker.__class__.__name__


def sanitize_source_filename(file_name: str | None, fallback_suffix: str = "") -> str:
    """Return a filename safe for storage inside a KB-owned directory."""
    raw = (file_name or "").replace("\\", "/").split("/")[-1].replace("\x00", "")
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", raw).strip(" .")
    if not safe:
        safe = f"document_{uuid.uuid4().hex[:8]}{fallback_suffix}"
    return safe[:255]


def build_stored_source_path(
    files_dir: Path,
    *,
    doc_id: str,
    file_name: str,
    file_type: str,
) -> Path:
    suffix = Path(file_name).suffix
    if not suffix and file_type:
        suffix = f".{file_type}"
    safe_name = sanitize_source_filename(file_name, fallback_suffix=suffix)
    return files_dir / doc_id / safe_name
