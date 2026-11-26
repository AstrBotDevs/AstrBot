"""Typed plugin configuration, JSON Schema export, and sensitive field detection."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from .errors import InvalidConfig

MAX_CONFIG_SCHEMA_BYTES = 64 * 1024

try:
    from pydantic import BaseModel, ConfigDict, ValidationError

    class PluginConfig(BaseModel):
        """Base class for typed plugin configurations validated by Pydantic v2."""

        model_config = ConfigDict(extra="forbid")

except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    ValidationError = ValueError  # type: ignore[misc,assignment]

    class PluginConfig:  # type: ignore[no-redef]
        """Placeholder base class when pydantic is not installed."""

        def __init__(self, **_: Any) -> None:
            raise ModuleNotFoundError(
                "install astrbot-sdk[schema] (pydantic>=2) to use PluginConfig"
            )


def _declare_object_root(schema: dict[str, Any]) -> None:
    if schema.get("type") == "object":
        return
    reference = schema.get("$ref")
    match = (
        re.fullmatch(r"#/\$defs/([A-Za-z0-9_.-]+)", reference)
        if isinstance(reference, str)
        else None
    )
    definitions = schema.get("$defs")
    if "type" not in schema and match and isinstance(definitions, dict):
        definition = definitions.get(match.group(1))
        if isinstance(definition, dict) and definition.get("type") == "object":
            # Recursive Pydantic models place `"type": "object"` inside `$defs`.
            schema["type"] = "object"
            return
    raise InvalidConfig("plugin configuration schema must declare an object root")


def reject_external_schema_refs(schema: Any) -> None:
    """Verify a JSON Schema has an object root and no external `$ref` entries.

    Args:
        schema: Parsed JSON Schema mapping.

    Raises:
        InvalidConfig: The schema root is not an object or uses an external ref.
    """
    if not isinstance(schema, dict):
        raise InvalidConfig("config.schema.json must be a JSON object")

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if ref is not None:
                if not isinstance(ref, str) or not ref.startswith("#/"):
                    raise InvalidConfig(
                        f"external or invalid schema $ref is not allowed: {ref!r}"
                    )
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(schema)
    _declare_object_root(schema)


def schema_has_sensitive_fields(schema: Any) -> bool:
    """Return True if any subschema marks `writeOnly: true` or `format: "password"`.

    Args:
        schema: Parsed JSON Schema value.

    Returns:
        Whether any field marks sensitive credentials.
    """
    if isinstance(schema, Mapping):
        if schema.get("writeOnly") is True or schema.get("format") == "password":
            return True
        return any(schema_has_sensitive_fields(v) for v in schema.values())
    if isinstance(schema, list):
        return any(schema_has_sensitive_fields(item) for item in schema)
    return False


def export_config_schema(
    model_cls: type[Any],
    package_root: str | Path,
) -> Path:
    """Export a `PluginConfig` (Pydantic v2 BaseModel) to `config.schema.json`.

    Args:
        model_cls: Pydantic v2 BaseModel subclass.
        package_root: Plugin package root directory.

    Returns:
        Path to the written `config.schema.json`.

    Raises:
        InvalidConfig: The model or exported schema violates Host constraints.
    """
    try:
        pydantic = import_module("pydantic")
    except ModuleNotFoundError as exc:
        raise InvalidConfig(
            "install astrbot-sdk[schema] to export a Pydantic config model"
        ) from exc

    if not isinstance(model_cls, type) or not issubclass(model_cls, pydantic.BaseModel):
        raise InvalidConfig("model must be a Pydantic BaseModel subclass")

    schema = cast(Any, model_cls).model_json_schema(mode="validation")
    reject_external_schema_refs(schema)
    encoded = (
        json.dumps(schema, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_CONFIG_SCHEMA_BYTES:
        raise InvalidConfig("config.schema.json exceeds 64 KiB limit")
    out_path = Path(package_root) / "config.schema.json"
    out_path.write_bytes(encoded)
    return out_path


def validate_config_against_model(
    model_cls: type[Any],
    candidate: Any,
) -> Any:
    """Validate candidate config data against a `PluginConfig` model.

    Args:
        model_cls: Pydantic v2 BaseModel subclass.
        candidate: Raw candidate configuration payload.

    Returns:
        Validated model instance.

    Raises:
        InvalidConfig: Candidate config fails validation.
    """
    payload = {} if candidate is None else candidate
    try:
        return model_cls.model_validate(payload)
    except Exception as exc:
        raise InvalidConfig(str(exc)) from exc


def main() -> None:
    """CLI entrypoint: `python -m astrbot_sdk.config module:Model <package_root>`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", metavar="module:Model")
    parser.add_argument("package_root", type=Path)
    args = parser.parse_args()
    module_name, sep, attr_name = args.model.partition(":")
    if not sep or not module_name or not attr_name:
        parser.error("model must be specified as module:Model")
    try:
        model = getattr(import_module(module_name), attr_name)
        export_config_schema(model, args.package_root)
    except (
        ImportError,
        AttributeError,
        OSError,
        TypeError,
        ValueError,
        InvalidConfig,
    ) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
