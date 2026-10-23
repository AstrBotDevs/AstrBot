"""Keep requirements.txt in sync with the runtime dependencies in pyproject.toml."""

from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from astrbot.core.utils.toml_parser import read_pyproject_project_dependencies

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"


def _read_requirements() -> list[str]:
    """Read non-comment, non-empty requirement lines from requirements.txt.

    Returns:
        Requirement strings declared in requirements.txt.
    """
    entries = []
    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        candidate = line.split("#", 1)[0].strip()
        if candidate:
            entries.append(candidate)
    return entries


def _normalize(entries: list[str]) -> dict[str, tuple[frozenset[str], str, str]]:
    """Normalize requirement strings for order-independent comparison.

    Args:
        entries: Raw requirement strings from either dependency file.

    Returns:
        Mapping from canonicalized package name to a comparable tuple of
        ``(extras, version specifier, environment marker)``.
    """
    dependencies = {}
    for entry in entries:
        requirement = Requirement(entry)
        dependencies[canonicalize_name(requirement.name)] = (
            frozenset(requirement.extras),
            str(requirement.specifier),
            str(requirement.marker or ""),
        )
    return dependencies


def test_requirements_txt_declares_same_packages_as_pyproject() -> None:
    """Both dependency files must declare the same set of runtime packages."""
    requirements = _normalize(_read_requirements())
    pyproject = _normalize(read_pyproject_project_dependencies(PYPROJECT_PATH))

    missing = sorted(set(pyproject) - set(requirements))
    unexpected = sorted(set(requirements) - set(pyproject))

    assert not missing, (
        f"requirements.txt is missing packages declared in pyproject.toml: {missing}"
    )
    assert not unexpected, (
        f"requirements.txt declares packages absent from pyproject.toml: {unexpected}"
    )


def test_requirements_txt_specs_match_pyproject() -> None:
    """Extras, version specifiers, and markers must match between both files."""
    requirements = _normalize(_read_requirements())
    pyproject = _normalize(read_pyproject_project_dependencies(PYPROJECT_PATH))

    mismatches = [
        f"{name}: pyproject={pyproject[name]}, requirements.txt={requirements[name]}"
        for name in sorted(set(pyproject) & set(requirements))
        if pyproject[name] != requirements[name]
    ]

    assert not mismatches, (
        "Dependency specs differ between pyproject.toml and requirements.txt:\n"
        + "\n".join(mismatches)
    )
