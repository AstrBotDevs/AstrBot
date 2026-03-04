from __future__ import annotations

import importlib.util
from pathlib import Path


def _constants_file() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "astrbot"
        / "core"
        / "release_constants.py"
    )


def load_release_constants(*names: str) -> dict[str, str]:
    constants_path = _constants_file()
    spec = importlib.util.spec_from_file_location(
        "astrbot_core_release_constants_tmp",
        constants_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load spec for {constants_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    values: dict[str, str] = {}
    missing: list[str] = []

    for name in names:
        value = getattr(module, name, None)
        if not isinstance(value, str):
            missing.append(name)
            continue
        value = value.strip()
        if not value:
            missing.append(name)
            continue
        values[name] = value

    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            f"Failed to parse {missing_str} from astrbot/core/release_constants.py",
        )

    return values


def load_release_constant(name: str) -> str:
    return load_release_constants(name)[name]
