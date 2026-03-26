from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import logger as logger

__all__ = ["logger"]


def __getattr__(name: str) -> Any:
    if name == "cli":
        from .cli.__main__ import cli

        return cli()
    if name == "cli_rs":
        from .rust._core import cli

        def cli_rs_wrapper() -> None:
            return cli(sys.argv)

        return cli_rs_wrapper

    if name == "logger":
        from .core import logger

        return logger
    raise AttributeError(name)
