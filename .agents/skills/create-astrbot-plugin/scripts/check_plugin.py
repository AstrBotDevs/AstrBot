#!/usr/bin/env python3
"""Check the static contract of a generated AstrBot plugin."""

from __future__ import annotations

import argparse
import ast
import json
import keyword
import re
import sys
import tomllib
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PYTHON_FLOOR_RE = re.compile(r">=\s*([0-9]+(?:\.[0-9]+){1,2})")
REQUIRED_METADATA = {"name", "desc", "version", "author"}


def parse_metadata(path: Path) -> dict[str, str]:
    """Parse the scalar top-level metadata needed by this checker."""
    result: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[0].isspace() or ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            raise ValueError(f"metadata line {number} has an empty key")
        if value.startswith(("'", '"')) and value[-1:] == value[:1]:
            value = value[1:-1]
        result[key] = value
    return result


def locate_root(explicit: Path | None) -> Path:
    candidates = []
    if explicit is not None:
        candidates.append(explicit.expanduser().resolve())
    current = Path.cwd().resolve()
    candidates.extend((current, *current.parents))
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ValueError("could not locate pyproject.toml; pass --astrbot-root")


def python_floor(root: Path) -> str:
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    specifier = document["project"]["requires-python"]
    match = PYTHON_FLOOR_RE.search(specifier)
    if match is None:
        raise ValueError("project.requires-python has no >= lower bound")
    return f">={match.group(1)}"


def check_python_file(path: Path, errors: list[str]) -> None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as exc:
        errors.append(f"{path}: cannot parse Python: {exc}")
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = (node.module or "",)
        else:
            continue
        for name in names:
            if name == "requests" or name.startswith("requests."):
                errors.append(f"{path}: use an async HTTP client instead of requests")
            if name.startswith(("astrbot.core", "astrbot.dashboard")):
                errors.append(
                    f"{path}: import only the public astrbot.api SDK, found {name}"
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin", type=Path)
    parser.add_argument("--astrbot-root", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    errors: list[str] = []
    plugin = args.plugin.expanduser().resolve()
    if not plugin.is_dir():
        print(f"check_plugin: error: not a directory: {plugin}", file=sys.stderr)
        return 2

    metadata_path = plugin / "metadata.yaml"
    main_path = plugin / "main.py"
    if not metadata_path.is_file():
        errors.append("missing metadata.yaml")
    if not main_path.is_file():
        errors.append("missing main.py")
    if metadata_path.is_file():
        try:
            metadata = parse_metadata(metadata_path)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
        else:
            missing = REQUIRED_METADATA - metadata.keys()
            errors.extend(f"metadata.yaml: missing {key}" for key in sorted(missing))
            errors.extend(
                f"metadata.yaml: {key} must not be empty"
                for key in sorted(REQUIRED_METADATA & metadata.keys())
                if not metadata[key].strip()
            )
            name = metadata.get("name", "")
            if not NAME_RE.fullmatch(name) or keyword.iskeyword(name):
                errors.append("metadata.yaml: name is not a legal Python identifier")
            if name and name != plugin.name:
                errors.append(
                    f"metadata.yaml: name {name!r} does not match directory {plugin.name!r}",
                )

    if main_path.is_file():
        check_python_file(main_path, errors)
    for path in sorted(plugin.rglob("*.py")):
        if path != main_path:
            check_python_file(path, errors)

    schema_path = plugin / "_conf_schema.json"
    if schema_path.is_file():
        try:
            json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"_conf_schema.json: invalid strict JSON: {exc}")

    try:
        root = locate_root(args.astrbot_root)
        floor = python_floor(root)
    except (OSError, KeyError, tomllib.TOMLDecodeError, ValueError) as exc:
        errors.append(f"cannot read AstrBot Python floor: {exc}")
    else:
        readme = plugin / "README.md"
        if not readme.is_file():
            errors.append("missing README.md with the synchronized Python floor")
        elif floor not in readme.read_text(encoding="utf-8"):
            errors.append(
                f"README.md does not declare the AstrBot Python floor {floor}"
            )

    if errors:
        print("Plugin contract failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Plugin contract passed: {plugin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
