"""AstrBot Development Mode .

核心运行时测试.

"""

from __future__ import annotations

import sys

import anyio
import click


@click.command()
def dev() -> None:
    """启动开发模式."""
    from astrbot._internal.runtime import bootstrap

    try:
        anyio.run(bootstrap, backend="asyncio")
    except KeyboardInterrupt:
        sys.exit(0)
