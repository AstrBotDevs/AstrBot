"""Keep requirements.txt in sync with the runtime dependencies in pyproject.toml."""

from pathlib import Path

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from astrbot.core.utils.requirements_utils import _iter_requirement_lines
from astrbot.core.utils.toml_parser import read_pyproject_project_dependencies

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"

MarkerKey = frozenset | tuple[str, frozenset]


def _read_requirements(path: Path = REQUIREMENTS_PATH) -> list[str]:
    """Read requirement lines, expanding includes and skipping pip directives.

    Args:
        path: Requirements file to read.

    Returns:
        Requirement strings with nested ``-r`` includes expanded, comments
        stripped, and pip options such as ``--extra-index-url``, ``-c``, and
        ``-e`` removed.
    """
    entries = []
    for line in _iter_requirement_lines(str(path)):
        if line.startswith("-"):
            continue
        candidate = line.split(" --", 1)[0].strip()
        if candidate:
            entries.append(candidate)
    return entries


def _canonical_marker(marker: Marker | None) -> MarkerKey:
    """Build an order-insensitive canonical key for a marker.

    Args:
        marker: Parsed environment marker, or ``None``.

    Returns:
        Canonical key where reordered ``and``/``or`` clauses compare equal via
        ``frozenset`` membership while operator precedence is preserved.
    """
    if marker is None:
        return frozenset()

    def render(items: list) -> tuple[str, frozenset]:
        # Split on "or"; each group is an AND of operands. Nested parenthesized
        # clauses become nested keys, so precedence is preserved.
        groups: list[list[str | tuple]] = [[]]
        for item in items:
            if isinstance(item, str):
                if item == "or":
                    groups.append([])
                continue
            if isinstance(item, list):
                groups[-1].append(render(item))
            else:
                groups[-1].append(str(item))
        return ("or", frozenset(frozenset(group) for group in groups))

    return render(marker._markers)


def _normalize(entries: list[str]) -> dict[str, tuple[frozenset[str], str, MarkerKey]]:
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
            _canonical_marker(requirement.marker),
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
