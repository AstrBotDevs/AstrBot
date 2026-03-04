from __future__ import annotations

import importlib.machinery
import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType


def _constants_file() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "astrbot"
        / "core"
        / "release_constants.py"
    )


@lru_cache(maxsize=1)
def _release_constants_module() -> ModuleType:
    constants_path = _constants_file()
    module_name = "astrbot_core_release_constants_loader"
    loader = importlib.machinery.SourceFileLoader(module_name, str(constants_path))
    spec = importlib.util.spec_from_loader(module_name, loader)
    if spec is None:
        raise RuntimeError(f"Failed to load spec for {constants_path}")

    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


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
