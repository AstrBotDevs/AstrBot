from __future__ import annotations

import importlib
import sys
from functools import lru_cache
from pathlib import Path


def _constants_file() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "astrbot"
        / "core"
        / "release_constants.py"
    )


@lru_cache(maxsize=1)
def _release_constants_module():
    try:
        return importlib.import_module("astrbot.core.release_constants")
    except ModuleNotFoundError:
        constants_dir = str(_constants_file().parent)
        if constants_dir not in sys.path:
            sys.path.insert(0, constants_dir)
        return importlib.import_module("release_constants")


def load_release_constants(*names: str) -> dict[str, str]:
    module = _release_constants_module()

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
