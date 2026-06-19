from pathlib import Path

import pytest

from astrbot.core.utils.toml_parser import (
    read_pyproject_project_dependencies,
    read_pyproject_project_version,
)


def test_read_pyproject_project_version_reads_project_section(tmp_path: Path) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        "\n".join(
            [
                'version = "ignored"',
                "[project]",
                'name = "AstrBot"',
                'version = "1.2.3-beta.4" # release version',
                "[tool.example]",
                'version = "ignored-again"',
            ]
        ),
        encoding="utf-8",
    )

    assert read_pyproject_project_version(pyproject_path) == "1.2.3-beta.4"


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


def test_read_pyproject_project_version_raises_when_missing(tmp_path: Path) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text('[project]\nname = "AstrBot"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Missing project.version"):
        read_pyproject_project_version(pyproject_path)
