import re
from pathlib import Path

import pytest
import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
HTTPX_SOCKS_PATTERN = re.compile(r"^httpx\[socks\](?:\s*[<>=!~][^;]*)?(?:\s*;.*)?$")


def _read_httpx_socks_dependency(entries: list[str]) -> str | None:
    for entry in entries:
        candidate = entry.strip()
        if HTTPX_SOCKS_PATTERN.match(candidate):
            return candidate
    return None


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
    requirements_dependency = _read_httpx_socks_dependency(_read_requirements())

    assert requirements_dependency is not None, (
        "Expected httpx[socks] dependency in requirements.txt for SOCKS proxy support"
    )


def test_pyproject_declares_httpx_socks_dependency() -> None:
    pyproject_dependency = _read_httpx_socks_dependency(_read_pyproject_dependencies())

    assert pyproject_dependency is not None, (
        "Expected httpx[socks] dependency in pyproject.toml for SOCKS proxy support"
    )


def test_httpx_socks_dependency_spec_matches_between_dependency_files() -> None:
    requirements_dependency = _read_httpx_socks_dependency(_read_requirements())
    pyproject_dependency = _read_httpx_socks_dependency(_read_pyproject_dependencies())

    assert requirements_dependency is not None, (
        "Expected httpx[socks] dependency in requirements.txt for SOCKS proxy support"
    )
    assert pyproject_dependency is not None, (
        "Expected httpx[socks] dependency in pyproject.toml for SOCKS proxy support"
    )
    assert requirements_dependency == pyproject_dependency, (
        "Expected httpx[socks] dependency spec to match between requirements.txt "
        "and pyproject.toml for SOCKS proxy support"
    )


@pytest.mark.parametrize(
    "entry",
    [
        "httpx[socks]",
        "httpx[socks]==0.27.0",
        "httpx[socks]==0.28.1",
        "httpx[socks]>=0.27.0,<0.28.0",
        "httpx[socks]>=0.27,<0.29",
        'httpx[socks]; python_version >= "3.11"',
        'httpx[socks]>=0.27.0 ; python_version < "3.13"',
        'httpx[socks] ; python_version < "3.13"',
        'httpx[socks]  >=0.27  ; python_version < "3.13"',
    ],
)
def test_httpx_socks_pattern_matches_valid_variants(entry: str) -> None:
    match = HTTPX_SOCKS_PATTERN.match(entry)

    assert match is not None, (
        f"Expected httpx[socks] dependency pattern to match valid entry for "
        f"SOCKS proxy support: {entry}"
    )
    assert match.group(0) == entry, (
        f"Expected httpx[socks] dependency pattern to fully match valid entry "
        f"for SOCKS proxy support: {entry}"
    )


@pytest.mark.parametrize(
    "entry",
    [
        "httpx",
        "httpx==0.27.0",
        "httpx[http2]",
        "httpx[socks-extra]",
        "httpx [socks]",
        "someprefix httpx[socks]",
        "httpx[socks] trailing-text",
        "httpx[socks] extra ; markers",
        "httpx[socks]andmore",
    ],
)
def test_httpx_socks_pattern_rejects_invalid_variants(entry: str) -> None:
    assert HTTPX_SOCKS_PATTERN.match(entry) is None, (
        f"Expected httpx[socks] dependency pattern to reject invalid entry for "
        f"SOCKS proxy support: {entry}"
    )
