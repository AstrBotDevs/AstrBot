from importlib import metadata

try:
    __version__ = metadata.version("AstrBot")
except metadata.PackageNotFoundError:
    __version__ = "unknown"
