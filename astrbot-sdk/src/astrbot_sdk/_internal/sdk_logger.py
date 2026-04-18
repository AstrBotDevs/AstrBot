from __future__ import annotations

import os

from loguru import logger as _raw_loguru_logger

try:
    from astrbot.core.config.default import VERSION as _ASTRBOT_VERSION
except Exception:  # noqa: BLE001
    _ASTRBOT_VERSION = ""

_SHORT_LEVEL_NAMES = {
    "DEBUG": "DBUG",
    "INFO": "INFO",
    "WARNING": "WARN",
    "ERROR": "ERRO",
    "CRITICAL": "CRIT",
}


def _get_short_level_name(level_name: str) -> str:
    return _SHORT_LEVEL_NAMES.get(level_name.upper(), level_name[:4].upper())


def _build_source_file(pathname: str | None) -> str:
    if not pathname:
        return "unknown"
    dirname = os.path.dirname(pathname)
    return (
        os.path.basename(dirname) + "." + os.path.basename(pathname).replace(".py", "")
    )


def _patch_record(record: dict) -> None:
    extra = record["extra"]
    extra.setdefault("plugin_tag", "[Core]")
    extra.setdefault("short_levelname", _get_short_level_name(record["level"].name))
    level_no = record["level"].no
    version_tag = (
        f" [v{_ASTRBOT_VERSION}]" if _ASTRBOT_VERSION and level_no >= 30 else ""
    )
    extra.setdefault("astrbot_version_tag", version_tag)
    extra.setdefault("source_file", _build_source_file(record["file"].path))
    extra.setdefault("source_line", record["line"])
    extra.setdefault("is_trace", False)


logger = _raw_loguru_logger.patch(_patch_record)

__all__ = ["logger"]
