import re
from pathlib import Path


def normalize_provider_id(provider_id: str) -> str:
    """Normalize provider id to a file-system-safe token."""
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", provider_id)


def build_index_filename(provider_id: str) -> str:
    return f"index.{normalize_provider_id(provider_id)}.faiss"


def build_index_path(kb_dir: Path, provider_id: str) -> Path:
    return kb_dir / build_index_filename(provider_id)
