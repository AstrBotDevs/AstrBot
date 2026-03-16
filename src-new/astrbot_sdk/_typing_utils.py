from __future__ import annotations

import typing
from typing import Any


def unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    origin = typing.get_origin(annotation)
    if origin in {typing.Union, getattr(typing, "UnionType", object())}:
        args = [item for item in typing.get_args(annotation) if item is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


__all__ = ["unwrap_optional"]
