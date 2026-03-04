from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _constants_file() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "astrbot"
        / "core"
        / "release_constants.py"
    )


def load_release_constants(*names: str) -> dict[str, str]:
    constants_path = _constants_file()
    source = constants_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(constants_path))

    wanted = set(names)
    values: dict[str, str] = {}

    for node in tree.body:
        target_name: str | None = None
        value_node: Any | None = None

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target_name = target.id
                    break
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value

        if not target_name or target_name not in wanted:
            continue
        if not isinstance(value_node, ast.Constant) or not isinstance(
            value_node.value,
            str,
        ):
            continue

        value = value_node.value.strip()
        if value:
            values[target_name] = value

        if len(values) == len(wanted):
            break

    missing = [name for name in names if name not in values]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            f"Failed to parse {missing_str} from astrbot/core/release_constants.py",
        )

    return values


def load_release_constant(name: str) -> str:
    return load_release_constants(name)[name]
