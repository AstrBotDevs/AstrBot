import re
from pathlib import Path

import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
HTTPX_SOCKS_PATTERN = re.compile(r"^httpx\[socks\](?:\s*[<>=!~].*)?$")


def _contains_httpx_socks_dependency(entries: list[str]) -> bool:
    return any(HTTPX_SOCKS_PATTERN.match(entry.strip()) for entry in entries)


def _read_requirements() -> list[str]:
    entries = []
    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        candidate = line.split("#", 1)[0].strip()
        if candidate:
            entries.append(candidate)
    return entries


def _read_pyproject_dependencies() -> list[str]:
    with PYPROJECT_PATH.open("rb") as file:
        pyproject = tomllib.load(file)
    return pyproject["project"]["dependencies"]


def test_requirements_include_httpx_socks_dependency() -> None:
    assert _contains_httpx_socks_dependency(_read_requirements())


def test_pyproject_declares_httpx_socks_dependency() -> None:
    assert _contains_httpx_socks_dependency(_read_pyproject_dependencies())
