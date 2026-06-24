#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = REPO_ROOT / "openspec" / "openapi-v1.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "public" / "openapi.json"
PUBLIC_OPEN_API_TAGS = {
    "Open API",
    "System Config",
    "Config Profiles",
    "Bot Config Routes",
    "Bots",
    "Provider Sources",
    "Providers",
    "Chat",
    "IM",
    "Files",
    "Plugins",
    "Plugin Sources",
    "Plugin Pages",
    "MCP",
    "Skills",
    "Personas",
    "T2I",
    "Subagents",
}
PUBLIC_OPEN_API_EXCLUDED_PATHS = {
    "/api/v1/live-chat/ws",
    "/api/v1/unified-chat/ws",
}
COMPONENT_REF_PREFIX = "#/components/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update the public OpenAPI JSON document from the v1 YAML spec."
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=DEFAULT_SPEC,
        help=f"OpenAPI YAML source path. Default: {DEFAULT_SPEC}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"OpenAPI JSON output path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected OpenAPI object in {path}")
    return data


def iter_refs(value: Any):
    """Yield local component refs from an OpenAPI value.

    Args:
        value: Arbitrary OpenAPI object value.

    Yields:
        Local component reference strings.
    """
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith(COMPONENT_REF_PREFIX):
            yield ref
        for child in value.values():
            yield from iter_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_refs(child)


def parse_component_ref(ref: str) -> tuple[str, str] | None:
    """Parse a local component ref into its section and name.

    Args:
        ref: OpenAPI local component reference.

    Returns:
        The component section and name, or None if the ref is not a component ref.
    """
    if not ref.startswith(COMPONENT_REF_PREFIX):
        return None
    rest = ref.removeprefix(COMPONENT_REF_PREFIX)
    if "/" not in rest:
        return None
    section, name = rest.split("/", 1)
    return section, name


def filter_public_openapi(spec: dict[str, Any]) -> dict[str, Any]:
    """Filter the full v1 spec down to developer API key endpoints.

    Args:
        spec: Full OpenAPI spec loaded from the YAML source.

    Returns:
        A filtered OpenAPI spec for the public docs site.
    """
    output = dict(spec)
    output["tags"] = [
        tag
        for tag in spec.get("tags", [])
        if isinstance(tag, dict) and tag.get("name") in PUBLIC_OPEN_API_TAGS
    ]

    paths = {}
    for path, methods in spec.get("paths", {}).items():
        if path in PUBLIC_OPEN_API_EXCLUDED_PATHS:
            continue
        kept_methods = {
            method: operation
            for method, operation in methods.items()
            if any(tag in PUBLIC_OPEN_API_TAGS for tag in operation.get("tags", []))
        }
        if kept_methods:
            paths[path] = kept_methods
    output["paths"] = paths

    used_refs: dict[str, set[str]] = {}
    pending = list(iter_refs(paths))
    components = output.get("components", {})
    while pending:
        parsed = parse_component_ref(pending.pop())
        if parsed is None:
            continue
        section, name = parsed
        used_names = used_refs.setdefault(section, set())
        if name in used_names:
            continue
        used_names.add(name)
        component = components.get(section, {}).get(name)
        pending.extend(iter_refs(component))

    pruned_components = {}
    for section, values in components.items():
        if section == "securitySchemes":
            pruned_components[section] = values
            continue
        if not isinstance(values, dict):
            pruned_components[section] = values
            continue
        names = used_refs.get(section, set())
        kept_values = {name: values[name] for name in values if name in names}
        if kept_values:
            pruned_components[section] = kept_values
    output["components"] = pruned_components
    return output


def main() -> int:
    args = parse_args()
    spec_path = args.spec.resolve()
    output_path = args.output.resolve()

    spec = load_yaml(spec_path)
    spec = filter_public_openapi(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Updated {output_path.relative_to(REPO_ROOT)} from {spec_path.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
