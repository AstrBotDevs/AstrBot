from __future__ import annotations

import math
from typing import Any

# TOML has no null literal. Keep this centralized so behavior is explicit and
# easy to adjust in future migrations.
NULL_SENTINEL = "__NULL__"


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _toml_quote(value: str) -> str:
    return f'"{_toml_escape(value)}"'


def _toml_format_key(key: str) -> str:
    return _toml_quote(key)


def _format_toml_path(path: list[str]) -> str:
    return ".".join(_toml_format_key(str(part)) for part in path)


def _normalize_nulls(obj: Any) -> Any:
    if obj is None:
        return NULL_SENTINEL
    if isinstance(obj, dict):
        return {key: _normalize_nulls(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_normalize_nulls(value) for value in obj]
    return obj


def _classify_items(
    obj: dict[str, Any],
) -> tuple[
    list[tuple[str, Any]],
    list[tuple[str, dict[str, Any]]],
    list[tuple[str, list[dict[str, Any]]]],
]:
    scalar_items: list[tuple[str, Any]] = []
    nested_dicts: list[tuple[str, dict[str, Any]]] = []
    array_tables: list[tuple[str, list[dict[str, Any]]]] = []

    for key, value in obj.items():
        key_text = str(key)
        if isinstance(value, dict):
            nested_dicts.append((key_text, value))
        elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            array_tables.append((key_text, value))
        else:
            scalar_items.append((key_text, value))

    return scalar_items, nested_dicts, array_tables


def _toml_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            # TOML 1.0 does not allow NaN/Infinity.
            raise ValueError(f"non-finite float value is not TOML-compatible: {value}")
        return repr(value)
    if isinstance(value, str):
        return _toml_quote(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(
            f"{_toml_format_key(str(k))} = {_toml_literal(v)}" for k, v in value.items()
        )
        return "{ " + pairs + " }"
    return _toml_quote(str(value))


def json_to_toml(data: dict[str, Any]) -> str:
    """Serialize a JSON-like dict to TOML text used by migration snapshots.

    Notes:
    - Empty lists are emitted as `key = []`.
    - Only non-empty `list[dict]` values are emitted as array-of-tables.
      For empty lists we intentionally preserve literal emptiness because the
      element schema is unknown at serialization time.
    """
    normalized_data = _normalize_nulls(data)
    lines: list[str] = []

    def emit_table(obj: dict[str, Any], path: list[str]) -> None:
        scalar_items, nested_dicts, array_tables = _classify_items(obj)

        if path:
            lines.append(f"[{_format_toml_path(path)}]")
        for key, value in scalar_items:
            lines.append(f"{_toml_format_key(key)} = {_toml_literal(value)}")
        if scalar_items and (nested_dicts or array_tables):
            lines.append("")

        for idx, (key, value) in enumerate(nested_dicts):
            emit_table(value, [*path, key])
            if idx != len(nested_dicts) - 1 or array_tables:
                lines.append("")

        for t_idx, (key, items) in enumerate(array_tables):
            table_path = [*path, key]
            for item in items:
                lines.append(f"[[{_format_toml_path(table_path)}]]")
                for sub_key, sub_value in item.items():
                    lines.append(
                        f"{_toml_format_key(str(sub_key))} = {_toml_literal(sub_value)}"
                    )
                lines.append("")
            if t_idx == len(array_tables) - 1 and lines and lines[-1] == "":
                lines.pop()

    emit_table(normalized_data, [])
    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["NULL_SENTINEL", "json_to_toml"]
