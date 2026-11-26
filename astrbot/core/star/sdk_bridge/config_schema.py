"""Host-side JSON Schema loading, validation, and secret redaction for SDK plugins."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import jsonschema
from astrbot_sdk.config import (
    MAX_CONFIG_SCHEMA_BYTES,
    reject_external_schema_refs,
    schema_has_sensitive_fields,
)
from astrbot_sdk.errors import InvalidConfig

_JSON_TYPE_TO_ASTRBOT = {
    "string": "string",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "object",
}


def load_plugin_json_schema(plugin_root: Path) -> dict[str, Any] | None:
    """Load and validate `<plugin_root>/config.schema.json` offline.

    Args:
        plugin_root: Plugin package root directory.

    Returns:
        Parsed JSON Schema dict, or None when `config.schema.json` does not exist.

    Raises:
        InvalidConfig: The schema exceeds 64 KiB, is invalid JSON, or uses external refs.
    """
    schema_path = plugin_root / "config.schema.json"
    if not schema_path.is_file():
        return None
    try:
        raw = schema_path.read_bytes()
    except OSError as exc:
        raise InvalidConfig(f"cannot read config.schema.json: {exc}") from exc
    if len(raw) > MAX_CONFIG_SCHEMA_BYTES:
        raise InvalidConfig("config.schema.json exceeds 64 KiB limit")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidConfig(f"config.schema.json is invalid JSON: {exc}") from exc
    reject_external_schema_refs(parsed)
    return parsed


def plugin_has_sensitive_schema(plugin_root: Path) -> bool:
    """Return True if the plugin's `config.schema.json` marks sensitive fields.

    Fails closed (returns True) if a `config.schema.json` file exists but
    cannot be parsed safely.
    """
    schema_path = plugin_root / "config.schema.json"
    if not schema_path.is_file():
        return False
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return True
    return schema_has_sensitive_fields(schema)


def validate_against_json_schema(schema: dict[str, Any], candidate: Any) -> None:
    """Validate candidate config data against a JSON Schema offline.

    Args:
        schema: Parsed object-root JSON Schema.
        candidate: Candidate configuration payload.

    Raises:
        InvalidConfig: Candidate config violates the schema.
    """
    normalized = {} if candidate is None else candidate
    try:
        jsonschema.validate(instance=normalized, schema=schema)
    except jsonschema.ValidationError as exc:
        raise InvalidConfig(exc.message) from exc
    except jsonschema.SchemaError as exc:
        raise InvalidConfig(f"invalid config schema: {exc.message}") from exc


def to_astrbot_config_schema(json_schema: dict[str, Any]) -> dict[str, Any]:
    """Translate `config.schema.json` properties into AstrBot UI schema items.

    Args:
        json_schema: Parsed JSON Schema dictionary.

    Returns:
        Schema mapping compatible with `AstrBotConfig`.
    """
    defs = json_schema.get("$defs") or json_schema.get("definitions") or {}
    props = json_schema.get("properties")
    if not isinstance(props, Mapping):
        return {}

    items: dict[str, Any] = {}
    for key, raw_spec in props.items():
        if not isinstance(raw_spec, Mapping):
            continue
        spec = raw_spec
        ref = spec.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs.get(ref.removeprefix("#/$defs/"))
            if isinstance(target, Mapping):
                spec = {**target, **spec}
        raw_type = spec.get("type")
        if isinstance(raw_type, list):
            raw_type = next((item for item in raw_type if item != "null"), "string")
        astr_type = _JSON_TYPE_TO_ASTRBOT.get(str(raw_type or "string"), "string")
        entry: dict[str, Any] = {
            "description": str(spec.get("description") or spec.get("title") or key),
            "type": astr_type,
        }
        if "default" in spec:
            entry["default"] = copy.deepcopy(spec["default"])
        if spec.get("writeOnly") is True or spec.get("format") == "password":
            entry["hint"] = "Sensitive credential (write-only)"
        if astr_type == "object" and isinstance(spec.get("properties"), Mapping):
            nested = to_astrbot_config_schema(
                {"properties": spec["properties"], "$defs": defs}
            )
            if nested:
                entry["items"] = nested
        items[str(key)] = entry
    return items


def redact_write_only_fields(
    schema: dict[str, Any],
    values: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deep copy of config values with `writeOnly`/`password` fields masked."""
    defs = schema.get("$defs") or schema.get("definitions") or {}
    result = copy.deepcopy(dict(values))
    props = schema.get("properties")
    if not isinstance(props, Mapping):
        return result

    for key, val in list(result.items()):
        prop_spec = props.get(key)
        if not isinstance(prop_spec, Mapping):
            continue
        resolved = prop_spec
        ref = prop_spec.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs.get(ref.removeprefix("#/$defs/"))
            if isinstance(target, Mapping):
                resolved = {**target, **prop_spec}
        if schema_has_sensitive_fields(resolved):
            if isinstance(val, Mapping) and isinstance(
                resolved.get("properties"), Mapping
            ):
                result[key] = redact_write_only_fields(
                    {"properties": resolved["properties"], "$defs": defs},
                    val,
                )
            else:
                result[key] = ""
    return result
