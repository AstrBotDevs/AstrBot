from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import logger as logger

__all__ = ["logger"]


def __getattr__(name: str) -> Any:
    if name == "logger":
        from .core import logger

        return logger
    raise AttributeError(name)
