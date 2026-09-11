"""Helpers for exposing AstrBot's stable public API from the SDK package."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any


def export_public_api(module_name: str, namespace: dict[str, Any]) -> list[str]:
    module = import_module(module_name)
    exports = _public_exports(module)
    namespace.update({name: getattr(module, name) for name in exports})
    return exports


def _public_exports(module: ModuleType) -> list[str]:
    declared_exports = getattr(module, "__all__", None)
    if declared_exports is not None:
        return [str(name) for name in declared_exports]
    return [name for name in dir(module) if not name.startswith("_")]


__all__ = ["export_public_api"]
