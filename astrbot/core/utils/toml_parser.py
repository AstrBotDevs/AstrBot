"""Small TOML readers for bootstrapping paths without parser dependencies."""

from pathlib import Path


def _read_quoted_value(value: str, field_name: str) -> tuple[str, str]:
    """Read one quoted TOML string value and return its tail.

    Args:
        value: Raw value text that starts with a quoted string.
        field_name: Field name used in error messages.

    Returns:
        A tuple containing the unquoted string and the remaining text.

    Raises:
        ValueError: The value is not a supported quoted string.
    """
    value = value.strip()
    if len(value) < 2 or value[0] not in ("'", '"'):
        raise ValueError(f"Unsupported {field_name} value")

    quote = value[0]
    end_index = value.find(quote, 1)
    if end_index == -1:
        raise ValueError(f"Unterminated {field_name} string")

    result = value[1:end_index]
    if not result:
        raise ValueError(f"Empty {field_name} value")
    return result, value[end_index + 1 :].strip()


def _read_dependency_array(raw_value: str) -> list[str]:
    """Read a simple inline TOML string array.

    Args:
        raw_value: Raw dependency array text, including the surrounding brackets.

    Returns:
        Parsed dependency strings.

    Raises:
        ValueError: The array is missing brackets or contains unsupported entries.
    """
    value = raw_value.strip()
    if not value.startswith("["):
        raise ValueError("Unsupported project.dependencies value")

    dependencies = []
    value = value[1:].strip()
    while value:
        if value.startswith("]"):
            tail = value[1:].strip()
            if tail and not tail.startswith("#"):
                raise ValueError("Unsupported content after project.dependencies")
            return dependencies

        dependency, tail = _read_quoted_value(value, "project.dependencies entry")
        dependencies.append(dependency)

        if tail.startswith(","):
            value = tail[1:].strip()
            continue
        if tail.startswith("]"):
            value = tail
            continue
        if tail:
            raise ValueError("Unsupported content after project.dependencies entry")
        raise ValueError("Unterminated project.dependencies array")

    raise ValueError("Unterminated project.dependencies array")


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

        version, tail = _read_quoted_value(raw_value, "project.version")
        if tail and not tail.startswith("#"):
            raise ValueError("Unsupported content after project.version")
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

            dependency, tail = _read_quoted_value(
                line,
                "project.dependencies entry",
            )
            if tail.startswith(","):
                tail = tail[1:].strip()
            if tail.startswith("]"):
                tail = tail[1:].strip()
                dependencies.append(dependency)
                if tail and not tail.startswith("#"):
                    raise ValueError("Unsupported content after project.dependencies")
                return dependencies
            if tail and not tail.startswith("#"):
                raise ValueError("Unsupported content after project.dependencies entry")

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
        if not separator:
            raise ValueError("Unsupported project.dependencies value")
        raw_value = raw_value.strip()
        if raw_value == "[" or raw_value.startswith("[ #"):
            in_dependencies_array = True
            continue
        if raw_value.startswith("["):
            return _read_dependency_array(raw_value)
        raise ValueError("Unsupported project.dependencies value")

    if in_dependencies_array:
        raise ValueError("Unterminated project.dependencies array")
    raise ValueError("Missing project.dependencies")
