from importlib import metadata

try:
    __version__ = metadata.version("AstrBot")
except metadata.PackageNotFoundError:
    __version__ = "unknown"

from astrbot.cli.__main__ import cli

__all__ = ["cli"]
