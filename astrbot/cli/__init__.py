import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

try:
    __version__ = package_version("astrbot")
except PackageNotFoundError:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        if tomllib is None:
            match = re.search(
                r"(?m)^version\s*=\s*[\"']([^\"']+)[\"']",
                pyproject_path.read_text(encoding="utf-8"),
            )
            __version__ = match.group(1) if match else "0.0.0"
        else:
            with pyproject_path.open("rb") as f:
                __version__ = tomllib.load(f)["project"]["version"]
    except (FileNotFoundError, IndexError, KeyError, TypeError, ValueError):
        __version__ = "0.0.0"

match = re.match(r"^(\d+(?:\.\d+)*)(a|b|rc)(\d+)$", __version__)
if match:
    release, prerelease, number = match.groups()
    prerelease = {"a": "alpha", "b": "beta", "rc": "rc"}[prerelease]
    __version__ = f"{release}-{prerelease}.{number}"
