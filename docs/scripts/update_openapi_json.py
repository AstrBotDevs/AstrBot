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
DEFAULT_ZH_SCOPE_OUTPUT = REPO_ROOT / "docs" / "zh" / "dev" / "openapi-scopes.md"
DEFAULT_EN_SCOPE_OUTPUT = REPO_ROOT / "docs" / "en" / "dev" / "openapi-scopes.md"
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")
PUBLIC_OPEN_API_SCOPES = (
    "bot",
    "provider",
    "persona",
    "im",
    "config",
    "chat",
    "data",
    "file",
    "plugin",
    "mcp",
    "skill",
)
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
    parser.add_argument(
        "--zh-scope-output",
        type=Path,
        default=DEFAULT_ZH_SCOPE_OUTPUT,
        help=f"Chinese scope reference path. Default: {DEFAULT_ZH_SCOPE_OUTPUT}",
    )
    parser.add_argument(
        "--en-scope-output",
        type=Path,
        default=DEFAULT_EN_SCOPE_OUTPUT,
        help=f"English scope reference path. Default: {DEFAULT_EN_SCOPE_OUTPUT}",
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
    paths = {}
    for path, methods in spec.get("paths", {}).items():
        if path in PUBLIC_OPEN_API_EXCLUDED_PATHS:
            continue
        kept_methods = {}
        for method, operation in methods.items():
            if (
                method not in HTTP_METHODS
                or not isinstance(operation, dict)
                or operation.get("x-astrbot-scope") not in PUBLIC_OPEN_API_SCOPES
            ):
                continue
            operation = dict(operation)
            required_scope = operation["x-astrbot-scope"]
            scope_description = f"**Required scope:** `{required_scope}`"
            sensitive_scopes = operation.get("x-astrbot-sensitive-scopes", [])
            if sensitive_scopes:
                formatted_scopes = ", ".join(f"`{scope}`" for scope in sensitive_scopes)
                scope_description += (
                    "\n\n**Conditional sensitive scope:** " + formatted_scopes
                )
            description = str(operation.get("description", "")).strip()
            if scope_description not in description:
                operation["description"] = "\n\n".join(
                    part for part in (description, scope_description) if part
                )
            kept_methods[method] = operation
        if kept_methods:
            paths[path] = kept_methods
    output["paths"] = paths

    used_tags = {
        tag
        for methods in paths.values()
        for operation in methods.values()
        for tag in operation.get("tags", [])
    }
    output["tags"] = [
        tag
        for tag in spec.get("tags", [])
        if isinstance(tag, dict) and tag.get("name") in used_tags
    ]

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


def render_scope_reference(spec: dict[str, Any], *, language: str) -> str:
    """Render the complete API key scope-to-endpoint reference.

    Args:
        spec: Filtered public OpenAPI specification.
        language: Documentation language, either ``zh`` or ``en``.

    Returns:
        Generated Markdown document.

    Raises:
        ValueError: If the requested language is unsupported.
    """
    if language == "zh":
        title = "API Scope 与接口对照"
        intro = (
            "本页由 `openspec/openapi-v1.yaml` 自动生成。"
            "每个接口的基础权限来自 `x-astrbot-scope`；敏感操作还会列出需要显式授予的子权限。"
        )
        method_header = "方法"
        endpoint_header = "接口"
        sensitive_header = "条件性敏感子权限"
        includes_label = "包含权限"
        sensitive_scope_label = "敏感子权限"
        description_key = "description_zh"
        scope_separator = "、"
    elif language == "en":
        title = "API Scope–Endpoint Reference"
        intro = (
            "This page is generated from `openspec/openapi-v1.yaml`. "
            "Each endpoint's base permission comes from `x-astrbot-scope`; "
            "sensitive operations also list the sub-scope that must be granted explicitly."
        )
        method_header = "Method"
        endpoint_header = "Endpoint"
        sensitive_header = "Conditional sensitive sub-scope"
        includes_label = "Includes"
        sensitive_scope_label = "Sensitive sub-scope"
        description_key = "description"
        scope_separator = ", "
    else:
        raise ValueError(f"Unsupported documentation language: {language}")

    operations = []
    scope_definitions = spec.get("x-astrbot-scope-definitions", {})
    for path, methods in spec.get("paths", {}).items():
        for method in HTTP_METHODS:
            operation = methods.get(method)
            if not isinstance(operation, dict):
                continue
            scope = operation.get("x-astrbot-scope")
            if scope not in PUBLIC_OPEN_API_SCOPES:
                continue
            operations.append((scope, path, method, operation))

    lines = [
        "---",
        "outline: deep",
        "---",
        "",
        "<!-- Generated by docs/scripts/update_openapi_json.py. Do not edit directly. -->",
        "",
        f"# {title}",
        "",
        intro,
        "",
    ]
    for scope in PUBLIC_OPEN_API_SCOPES:
        scoped_operations = sorted(
            (item for item in operations if item[0] == scope),
            key=lambda item: (item[1], HTTP_METHODS.index(item[2])),
        )
        if not scoped_operations:
            continue
        definition = scope_definitions.get(scope, {})
        lines.extend(
            [
                f"## `{scope}`",
                "",
            ]
        )
        description = definition.get(description_key)
        if description:
            lines.extend([description, ""])
        included_scopes = definition.get("includes", [])
        if included_scopes:
            included_display = scope_separator.join(
                f"`{value}`" for value in included_scopes
            )
            lines.extend([f"- **{includes_label}:** {included_display}", ""])
        sensitive_children = [
            (name, child_definition)
            for name, child_definition in scope_definitions.items()
            if child_definition.get("parent") == scope
            and child_definition.get("sensitive") is True
        ]
        for name, child_definition in sensitive_children:
            child_description = child_definition.get(description_key, "")
            lines.append(f"- **{sensitive_scope_label} `{name}`:** {child_description}")
        if sensitive_children:
            lines.append("")
        lines.extend(
            [
                f"| {method_header} | {endpoint_header} | {sensitive_header} |",
                "| --- | --- | --- |",
            ]
        )
        for _, path, method, operation in scoped_operations:
            sensitive_scopes = operation.get("x-astrbot-sensitive-scopes", [])
            sensitive_display = (
                ", ".join(f"`{value}`" for value in sensitive_scopes)
                if sensitive_scopes
                else "—"
            )
            lines.append(f"| `{method.upper()}` | `{path}` | {sensitive_display} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    spec_path = args.spec.resolve()
    output_path = args.output.resolve()
    zh_scope_output_path = args.zh_scope_output.resolve()
    en_scope_output_path = args.en_scope_output.resolve()

    spec = load_yaml(spec_path)
    spec = filter_public_openapi(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    zh_scope_output_path.parent.mkdir(parents=True, exist_ok=True)
    zh_scope_output_path.write_text(
        render_scope_reference(spec, language="zh"),
        encoding="utf-8",
    )
    en_scope_output_path.parent.mkdir(parents=True, exist_ok=True)
    en_scope_output_path.write_text(
        render_scope_reference(spec, language="en"),
        encoding="utf-8",
    )
    print(
        f"Updated {output_path.relative_to(REPO_ROOT)}, "
        f"{zh_scope_output_path.relative_to(REPO_ROOT)}, and "
        f"{en_scope_output_path.relative_to(REPO_ROOT)} from "
        f"{spec_path.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
