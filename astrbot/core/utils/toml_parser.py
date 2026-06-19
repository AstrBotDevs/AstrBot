"""Small TOML readers for bootstrapping paths without parser dependencies."""

from pathlib import Path


def read_pyproject_project_version(pyproject_path: Path) -> str:
    """Read the project version from a pyproject.toml file.

    Args:
        pyproject_path: Path to the pyproject.toml file.

    Returns:
        The value of the project.version field.

    Raises:
        FileNotFoundError: The pyproject.toml file does not exist.
        ValueError: The project.version field is missing or unsupported.
    """
    in_project_section = False
    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            in_project_section = line == "[project]"
            continue

        if not in_project_section:
            continue

        key, separator, raw_value = line.partition("=")
        if key.strip() != "version":
            continue
        if not separator:
            raise ValueError("Missing value separator for project.version")

        value = raw_value.strip()
        if len(value) < 2 or value[0] not in ("'", '"'):
            raise ValueError("Unsupported project.version value")

        quote = value[0]
        end_index = value.find(quote, 1)
        if end_index == -1:
            raise ValueError("Unterminated project.version string")

        tail = value[end_index + 1 :].strip()
        if tail and not tail.startswith("#"):
            raise ValueError("Unsupported content after project.version")

        version = value[1:end_index]
        if not version:
            raise ValueError("Empty project.version value")
        return version

    raise ValueError("Missing project.version")


def read_pyproject_project_dependencies(pyproject_path: Path) -> list[str]:
    """Read project dependencies from a pyproject.toml file.

    Args:
        pyproject_path: Path to the pyproject.toml file.

    Returns:
        The values in the project.dependencies array.

    Raises:
        FileNotFoundError: The pyproject.toml file does not exist.
        ValueError: The project.dependencies field is missing or unsupported.
    """
    dependencies = []
    in_project_section = False
    in_dependencies_array = False

    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if in_dependencies_array:
            if line.startswith("]"):
                tail = line[1:].strip()
                if tail and not tail.startswith("#"):
                    raise ValueError("Unsupported content after project.dependencies")
                return dependencies

            value = line.rstrip(",").strip()
            if len(value) < 2 or value[0] not in ("'", '"'):
                raise ValueError("Unsupported project.dependencies entry")

            quote = value[0]
            end_index = value.find(quote, 1)
            if end_index == -1:
                raise ValueError("Unterminated project.dependencies entry")

            tail = value[end_index + 1 :].strip()
            if tail.startswith(","):
                tail = tail[1:].strip()
            if tail and not tail.startswith("#"):
                raise ValueError("Unsupported content after project.dependencies entry")

            dependency = value[1:end_index]
            if not dependency:
                raise ValueError("Empty project.dependencies entry")
            dependencies.append(dependency)
            continue

        if line.startswith("[") and line.endswith("]"):
            in_project_section = line == "[project]"
            continue

        if not in_project_section:
            continue

        key, separator, raw_value = line.partition("=")
        if key.strip() != "dependencies":
            continue
        if not separator or raw_value.strip() != "[":
            raise ValueError("Unsupported project.dependencies value")
        in_dependencies_array = True

    if in_dependencies_array:
        raise ValueError("Unterminated project.dependencies array")
    raise ValueError("Missing project.dependencies")
