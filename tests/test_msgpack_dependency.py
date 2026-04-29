from pathlib import Path

import tomllib

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
MSGPACK_DEPENDENCY = "msgpack>=1.1.1"


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


def test_requirements_include_msgpack_dependency() -> None:
    assert MSGPACK_DEPENDENCY in _read_requirements(), (
        "Expected msgpack dependency in requirements.txt for vendored SDK protocol "
        "codec support"
    )


def test_pyproject_declares_msgpack_dependency() -> None:
    assert MSGPACK_DEPENDENCY in _read_pyproject_dependencies(), (
        "Expected msgpack dependency in pyproject.toml for vendored SDK protocol "
        "codec support"
    )
