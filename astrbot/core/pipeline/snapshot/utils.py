from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(*parts: str) -> str:
    return "sha256:" + sha256_hex("|".join(parts))


def compose_command(parent_signature: str, fragment: str | None) -> str:
    """
    复制运行时的指令拼接口径（见 `astrbot/core/star/command_management.py` 的实现），
    但避免依赖其内部私有函数。
    """
    fragment = (fragment or "").strip()
    parent_signature = (parent_signature or "").strip()
    if not parent_signature:
        return fragment
    if not fragment:
        return parent_signature
    return f"{parent_signature} {fragment}"