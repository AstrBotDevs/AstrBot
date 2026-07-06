from pathlib import Path

import pytest

from astrbot.core.utils.toml_parser import read_pyproject_project_dependencies


def test_read_pyproject_project_dependencies_reads_multiline_array(
    tmp_path: Path,
) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        "\n".join(
            [
                "[project]",
                "dependencies = [",
                '  "aiohttp>=3.11.18",',
                "  \"audioop-lts ; python_full_version >= '3.13'\", # marker",
                "] # end dependencies",
            ]
        ),
        encoding="utf-8",
    )

    assert read_pyproject_project_dependencies(pyproject_path) == [
        "aiohttp>=3.11.18",
        "audioop-lts ; python_full_version >= '3.13'",
    ]


@pytest.mark.parametrize(
    ("dependency_line", "expected"),
    [
        ("dependencies = []", []),
        ('dependencies = ["aiohttp>=3.11.18"]', ["aiohttp>=3.11.18"]),
        (
            'dependencies = ["psutil>=5.8.0,<7.2.0", "httpx[socks]>=0.28.1"]',
            ["psutil>=5.8.0,<7.2.0", "httpx[socks]>=0.28.1"],
        ),
    ],
)
def test_read_pyproject_project_dependencies_accepts_inline_arrays(
    tmp_path: Path,
    dependency_line: str,
    expected: list[str],
) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        "\n".join(
            [
                "[project]",
                dependency_line,
            ]
        ),
        encoding="utf-8",
    )

    assert read_pyproject_project_dependencies(pyproject_path) == expected


@pytest.mark.parametrize(
    ("project_lines", "message"),
    [
        (["[project]", 'name = "AstrBot"'], "Missing project.dependencies"),
        (
            ["[project]", "dependencies = ["],
            "Unterminated project.dependencies array",
        ),
        (
            ["[project]", 'dependencies = "aiohttp>=3.11.18"'],
            "Unsupported project.dependencies value",
        ),
        (
            ["[project]", "dependencies = [", "  aiohttp>=3.11.18,", "]"],
            "Unsupported project.dependencies entry value",
        ),
        (
            ["[project]", "dependencies = [", '  "aiohttp>=3.11.18" extra', "]"],
            "Unsupported content after project.dependencies entry",
        ),
        (
            ["[project]", "dependencies = [", '  ""', "]"],
            "Empty project.dependencies entry value",
        ),
    ],
)
def test_read_pyproject_project_dependencies_rejects_invalid_values(
    tmp_path: Path,
    project_lines: list[str],
    message: str,
) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text("\n".join(project_lines), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        read_pyproject_project_dependencies(pyproject_path)
