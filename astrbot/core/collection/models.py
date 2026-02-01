from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from jsonschema import Draft7Validator


@dataclass(slots=True)
class ImportOptions:
    import_mode: str = "add"  # add | clean
    apply_configs: bool = True
    overwrite_existing_configs: bool = False
    apply_priority: bool = True
    proxy: str = ""


class CollectionValidationError(ValueError):
    """Raised when a plugin collection payload is invalid."""


@dataclass(slots=True)
class CollectionPlugin:
    name: str
    repo: str
    exported_version: str
    display_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "repo": self.repo,
            "exported_version": self.exported_version,
        }
        if self.display_name is not None:
            data["display_name"] = self.display_name
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CollectionPlugin:
        exported_version = data.get("exported_version")
        if exported_version is None:
            # Backward compatibility for schema 1.0 payloads.
            exported_version = data.get("version", "")
        return cls(
            name=str(data.get("name", "")),
            repo=str(data.get("repo", "")),
            exported_version=str(exported_version or ""),
            display_name=(
                str(data["display_name"])
                if data.get("display_name") is not None
                else None
            ),
        )


@dataclass(slots=True)
class CollectionMetadata:
    name: str
    description: str
    author: str
    version: str
    created_at: str
    astrbot_version: str
    plugin_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "created_at": self.created_at,
            "astrbot_version": self.astrbot_version,
            "plugin_count": self.plugin_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CollectionMetadata:
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            version=str(data.get("version", "")),
            created_at=str(data.get("created_at", "")),
            astrbot_version=str(data.get("astrbot_version", "")),
            plugin_count=int(data.get("plugin_count", 0) or 0),
        )


@dataclass(slots=True)
class PluginCollection:
    schema_version: str
    metadata: CollectionMetadata
    plugins: list[CollectionPlugin]
    plugin_configs: dict[str, Any] | None = None
    handler_priority_overrides: dict[str, int] | None = None

    SCHEMA_VERSION: ClassVar[str] = "1.0"

    JSON_SCHEMA: ClassVar[dict[str, Any]] = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["schema_version", "metadata", "plugins"],
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "metadata": {
                "type": "object",
                "required": [
                    "name",
                    "description",
                    "author",
                    "version",
                    "created_at",
                    "astrbot_version",
                    "plugin_count",
                ],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "maxLength": 100},
                    "description": {"type": "string", "maxLength": 500},
                    "author": {"type": "string"},
                    "version": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "astrbot_version": {"type": "string"},
                    "plugin_count": {"type": "integer", "minimum": 0},
                },
            },
            "plugins": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "repo", "exported_version"],
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "repo": {"type": "string"},
                        "exported_version": {"type": "string"},
                        "display_name": {"type": ["string", "null"]},
                    },
                },
            },
            "plugin_configs": {
                "type": ["object", "null"],
                "additionalProperties": True,
            },
            "handler_priority_overrides": {
                "type": ["object", "null"],
                "additionalProperties": {"type": "integer"},
            },
        },
    }

    _validator: ClassVar[Draft7Validator] = Draft7Validator(JSON_SCHEMA)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "metadata": self.metadata.to_dict(),
            "plugins": [p.to_dict() for p in self.plugins],
        }
        if self.plugin_configs is not None:
            data["plugin_configs"] = self.plugin_configs
        if self.handler_priority_overrides is not None:
            data["handler_priority_overrides"] = self.handler_priority_overrides
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginCollection:
        cls.validate_dict(data)

        meta = CollectionMetadata.from_dict(data["metadata"])
        plugins = [CollectionPlugin.from_dict(p) for p in (data.get("plugins") or [])]
        return cls(
            schema_version=str(data.get("schema_version", cls.SCHEMA_VERSION)),
            metadata=meta,
            plugins=plugins,
            plugin_configs=data.get("plugin_configs"),
            handler_priority_overrides=data.get("handler_priority_overrides"),
        )

    @classmethod
    def validate_dict(cls, data: dict[str, Any]) -> None:
        errors = sorted(cls._validator.iter_errors(data), key=lambda e: list(e.path))
        if not errors:
            return
        parts: list[str] = []
        for err in errors:
            loc = "/".join(str(p) for p in err.absolute_path)
            prefix = f"{loc}: " if loc else ""
            parts.append(prefix + err.message)
        raise CollectionValidationError("; ".join(parts))
