import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

from astrbot.core.utils.toml_parser import read_pyproject_project_dependencies

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
    return read_pyproject_project_dependencies(PYPROJECT_PATH)


def _read_pinned_version(package: str) -> Version | None:
    pattern = re.compile(rf"^{re.escape(package)}==([^\s\\]+)")
    for entry in _read_requirements():
        if match := pattern.match(entry):
            return Version(match.group(1))
    return None


def test_requirements_include_locked_httpx_socks_dependencies() -> None:
    """The flattened, hash-pinned export must retain the SOCKS dependency graph."""
    assert _read_pinned_version("httpx") is not None
    assert _read_pinned_version("socksio") is not None


def test_pyproject_declares_httpx_socks_dependency() -> None:
    pyproject_dependency = _read_httpx_socks_dependency(_read_pyproject_dependencies())

    assert pyproject_dependency is not None, (
        "Expected httpx[socks] dependency in pyproject.toml for SOCKS proxy support"
    )


def test_locked_httpx_version_satisfies_direct_dependency_spec() -> None:
    locked_version = _read_pinned_version("httpx")
    pyproject_dependency = _read_httpx_socks_dependency(_read_pyproject_dependencies())

    assert locked_version is not None
    assert pyproject_dependency is not None, (
        "Expected httpx[socks] dependency in pyproject.toml for SOCKS proxy support"
    )
    direct_requirement = Requirement(pyproject_dependency)
    assert "socks" in direct_requirement.extras
    assert locked_version in direct_requirement.specifier


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
