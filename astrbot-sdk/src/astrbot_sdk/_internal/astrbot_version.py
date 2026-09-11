from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def get_astrbot_version() -> str:
    try:
        return version("AstrBot")
    except PackageNotFoundError:
        return ""


__all__ = ["get_astrbot_version"]
