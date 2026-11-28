import runpy
from pathlib import Path

import pytest


@pytest.fixture(params=["core", "cli"])
def comparator(request):
    """Load the actual comparator without initializing databases and providers.

    Args:
        request: Pytest request selecting the core or CLI implementation.

    Returns:
        The production VersionComparator class for the selected implementation.
    """
    module_path = (
        Path(__file__).resolve().parents[1]
        / "astrbot"
        / request.param
        / "utils"
        / "version_comparator.py"
    )
    return runpy.run_path(str(module_path))["VersionComparator"]


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("1.0.0-dev", "1.0.0-delta", 1),
        ("1.0.0-v1", "1.0.0-1", 1),
        ("1.0.0-BETA", "1.0.0-alpha", -1),
        ("1.0.0-RC.1", "1.0.0-rc.1", -1),
        ("v1.0.0-dev", "V1.0.0-delta", 1),
        ("v1.0.0", "V1.0.0", 0),
        ("1.0.0-dev+build.v1", "1.0.0-dev+build.V2", 0),
        ("1.0", "1.0.0", 0),
        ("1.9", "1.10", -1),
        ("1.0.0.1", "1.0.0", 1),
        ("1.0.0-beta.2", "1.0.0-beta.11", -1),
        ("1.0.0-alpha", "1.0.0", -1),
        ("1.0.0+v1", "1.0.0+V2", 0),
    ],
)
def test_compare_versions(comparator, left, right, expected):
    """Check version precedence in both directions.

    Args:
        comparator: Production core or CLI comparator class.
        left: First version string.
        right: Second version string.
        expected: Expected comparison result for left against right.
    """
    assert comparator.compare_version(left, right) == expected
    assert comparator.compare_version(right, left) == -expected


def test_semver_precedence_example(comparator):
    """Check the ordering example from SemVer section 11.

    Args:
        comparator: Production core or CLI comparator class.
    """
    versions = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
    ]

    for left, right in zip(versions, versions[1:]):
        assert comparator.compare_version(left, right) == -1
        assert comparator.compare_version(right, left) == 1
