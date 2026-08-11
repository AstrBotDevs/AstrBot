#!/usr/bin/env python3
"""Create a minimal AstrBot plugin from the current source checkout."""

from __future__ import annotations

import argparse
import keyword
import re
import sys
import tomllib
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PYTHON_FLOOR_RE = re.compile(r">=\s*([0-9]+(?:\.[0-9]+){1,2})")


def yaml_string(value: str) -> str:
    """Return a single-quoted YAML scalar."""
    return "'" + value.replace("'", "''") + "'"


def validate_name(name: str) -> None:
    if not NAME_RE.fullmatch(name) or keyword.iskeyword(name):
        raise ValueError(
            "plugin name must be a legal Python identifier and must not be a keyword",
        )


def locate_astrbot_root(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser().resolve())
    current = Path.cwd().resolve()
    candidates.extend((current, *current.parents))
    for candidate in candidates:
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except OSError, tomllib.TOMLDecodeError:
            continue
        project = document.get("project", {})
        if isinstance(project, dict) and project.get("requires-python"):
            return candidate
    raise ValueError(
        "could not locate an AstrBot checkout with project.requires-python; "
        "pass --astrbot-root explicitly",
    )


def read_python_floor(root: Path) -> tuple[str, str | None]:
    pyproject = root / "pyproject.toml"
    document = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = document.get("project", {})
    specifier = project.get("requires-python") if isinstance(project, dict) else None
    if not isinstance(specifier, str):
        raise ValueError("pyproject.toml project.requires-python must be a string")
    match = PYTHON_FLOOR_RE.search(specifier)
    if match is None:
        raise ValueError(
            "project.requires-python must contain a lower bound such as >=3.14",
        )
    pin_path = root / ".python-version"
    pin = pin_path.read_text(encoding="utf-8").strip() if pin_path.is_file() else None
    return f">={match.group(1)}", pin or None


def class_name(plugin_name: str) -> str:
    parts = [part for part in plugin_name.split("_") if part]
    result = "".join(part[:1].upper() + part[1:] for part in parts)
    return result + "Plugin"


def write_text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="new plugin directory"
    )
    parser.add_argument(
        "--name", required=True, help="metadata name and Python module name"
    )
    parser.add_argument("--author", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--repo", default="")
    parser.add_argument("--display-name", default="")
    parser.add_argument("--command", default="hello")
    parser.add_argument("--astrbot-root", type=Path)
    parser.add_argument(
        "--force", action="store_true", help="replace an existing directory"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        validate_name(args.name)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", args.command):
            raise ValueError("command must contain ASCII letters, digits, '_' or '-'")
        handler_name = args.command.replace("-", "_")
        if keyword.iskeyword(handler_name):
            raise ValueError("command must not produce a Python keyword handler name")
        root = locate_astrbot_root(args.astrbot_root)
        python_floor, python_pin = read_python_floor(root)
        output = args.output.expanduser().resolve()
        if output.exists():
            if not args.force:
                raise ValueError(f"output directory already exists: {output}")
            if not output.is_dir():
                raise ValueError(f"output path is not a directory: {output}")
        else:
            output.mkdir(parents=True)
        if output == root:
            raise ValueError("refusing to scaffold directly into the AstrBot checkout")
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"scaffold_plugin: error: {exc}", file=sys.stderr)
        return 2

    if args.force:
        for child in output.iterdir():
            if child.is_dir():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()

    display_name = args.display_name or args.name
    metadata = [
        f"name: {args.name}",
        f"desc: {yaml_string(args.description)}",
        f"version: {yaml_string(args.version)}",
        f"author: {yaml_string(args.author)}",
    ]
    if args.repo:
        metadata.append(f"repo: {yaml_string(args.repo)}")
    if args.display_name:
        metadata.append(f"display_name: {yaml_string(display_name)}")

    write_text(output / "metadata.yaml", "\n".join(metadata))
    write_text(
        output / "main.py",
        f'''from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star


class {class_name(args.name)}(Star):
    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)

    @filter.command("{args.command}")
    async def {handler_name}(self, event: AstrMessageEvent):
        """Reply with a placeholder response; replace this with the plugin behavior."""
        yield event.plain_result("Plugin scaffold is ready.")

    async def terminate(self) -> None:
        """Release clients, tasks, files, and other plugin-owned resources."""
''',
    )
    pin_text = f"; repository pin: `{python_pin}`" if python_pin else ""
    write_text(
        output / "README.md",
        f"""# {display_name}

{args.description}

## Development

- Python requirement: `{python_floor}`{pin_text}, read from the AstrBot checkout's `pyproject.toml`.
- Install into a source checkout with `uv run astrbot plug install --editable <path>`.
- Replace the placeholder `/{args.command}` handler and add focused tests before publishing.

This plugin uses only the public `astrbot.api` SDK. Keep persistent files under the plugin data directory, not in this source tree.
""",
    )
    print(f"Created {output}")
    print(f"Python floor: {python_floor} (source: {root / 'pyproject.toml'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
