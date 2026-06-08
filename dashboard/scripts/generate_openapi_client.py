from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT_DIR / "openspec" / "openapi-v1.yaml"
DEFAULT_OUTPUT = DASHBOARD_DIR / "src" / "api" / "generated" / "openapi-v1.ts"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def load_spec(source: str) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    spec_path = Path(source)
    if not spec_path.is_absolute():
        spec_path = (ROOT_DIR / spec_path).resolve()
    text = spec_path.read_text(encoding="utf-8")
    if spec_path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def pascal_case(value: str) -> str:
    words = re.split(r"[^a-zA-Z0-9]+", value)
    return "".join(word[:1].upper() + word[1:] for word in words if word)


def camel_case(value: str) -> str:
    pascal = pascal_case(value)
    return pascal[:1].lower() + pascal[1:]


def quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def property_name(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name):
        return name
    return quote(name)


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


class TypeScriptGenerator:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.components = spec.get("components", {})

    def resolve_ref(self, obj: dict[str, Any]) -> dict[str, Any]:
        ref = obj.get("$ref")
        if not ref:
            return obj
        if not ref.startswith("#/"):
            raise ValueError(f"Unsupported external ref: {ref}")
        current: Any = self.spec
        for part in ref.removeprefix("#/").split("/"):
            current = current[part]
        return current

    def schema_to_ts(self, schema: dict[str, Any] | None) -> str:
        if not schema:
            return "unknown"
        if "$ref" in schema:
            return ref_name(schema["$ref"])

        if "allOf" in schema:
            parts = [self.schema_to_ts(item) for item in schema["allOf"]]
            return " & ".join(parts) or "unknown"
        if "oneOf" in schema:
            parts = [self.schema_to_ts(item) for item in schema["oneOf"]]
            return " | ".join(parts) or "unknown"
        if "anyOf" in schema:
            parts = [self.schema_to_ts(item) for item in schema["anyOf"]]
            return " | ".join(parts) or "unknown"

        if "const" in schema:
            return quote(str(schema["const"]))
        if "enum" in schema:
            values = schema.get("enum") or []
            return " | ".join(quote(str(value)) for value in values) or "string"

        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            return " | ".join(
                self.schema_to_ts({**schema, "type": item}) for item in schema_type
            )

        if schema_type == "string":
            if schema.get("format") == "binary":
                return "Blob | File"
            return "string"
        if schema_type in {"integer", "number"}:
            return "number"
        if schema_type == "boolean":
            return "boolean"
        if schema_type == "array":
            return f"{self.schema_to_ts(schema.get('items'))}[]"
        if schema_type == "object" or "properties" in schema:
            properties = schema.get("properties") or {}
            additional = schema.get("additionalProperties")
            if not properties:
                if isinstance(additional, dict):
                    return f"Record<string, {self.schema_to_ts(additional)}>"
                return "Record<string, unknown>"

            required = set(schema.get("required") or [])
            fields = []
            for name, prop_schema in properties.items():
                optional = "" if name in required else "?"
                fields.append(
                    f"{property_name(name)}{optional}: {self.schema_to_ts(prop_schema)};"
                )
            if additional is True:
                fields.append("[key: string]: unknown;")
            elif isinstance(additional, dict):
                fields.append(f"[key: string]: {self.schema_to_ts(additional)};")
            return "{ " + " ".join(fields) + " }"

        return "unknown"

    def component_declarations(self) -> list[str]:
        declarations = []
        schemas = self.components.get("schemas") or {}
        for name, schema in schemas.items():
            if (
                schema.get("type") == "object"
                and "properties" in schema
                and "allOf" not in schema
                and "oneOf" not in schema
                and "anyOf" not in schema
            ):
                declarations.append(self.object_interface(name, schema))
            else:
                declarations.append(
                    f"export type {name} = {self.schema_to_ts(schema)};"
                )
        return declarations

    def object_interface(self, name: str, schema: dict[str, Any]) -> str:
        required = set(schema.get("required") or [])
        lines = [f"export interface {name} {{"]
        for prop_name, prop_schema in (schema.get("properties") or {}).items():
            optional = "" if prop_name in required else "?"
            lines.append(
                f"  {property_name(prop_name)}{optional}: "
                f"{self.schema_to_ts(prop_schema)};"
            )
        additional = schema.get("additionalProperties")
        if additional is True:
            lines.append("  [key: string]: unknown;")
        elif isinstance(additional, dict):
            lines.append(f"  [key: string]: {self.schema_to_ts(additional)};")
        lines.append("}")
        return "\n".join(lines)

    def resolve_parameter(self, parameter: dict[str, Any]) -> dict[str, Any]:
        if "$ref" not in parameter:
            return parameter
        name = ref_name(parameter["$ref"])
        return self.components["parameters"][name]

    def request_body_type(self, request_body: dict[str, Any] | None) -> str | None:
        if not request_body:
            return None
        if "$ref" in request_body:
            request_body = self.resolve_ref(request_body)
        content = request_body.get("content") or {}
        if "multipart/form-data" in content:
            return "FormData"
        if "application/octet-stream" in content:
            return "Blob | ArrayBuffer | string"
        media = content.get("application/json") or next(iter(content.values()), None)
        if not media:
            return "unknown"
        return self.schema_to_ts(media.get("schema"))

    def response_type(self, operation: dict[str, Any]) -> str:
        responses = operation.get("responses") or {}
        response = responses.get("200") or responses.get("201") or responses.get("101")
        if not response:
            return "unknown"
        if "$ref" in response:
            response = self.resolve_ref(response)
        content = response.get("content") or {}
        if "application/json" in content:
            return self.schema_to_ts(content["application/json"].get("schema"))
        if "text/plain" in content or "text/html" in content:
            return "string"
        return "unknown"

    def operation_parameters(
        self,
        operation: dict[str, Any],
        path_item: dict[str, Any],
        operation_id: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        path_params: list[dict[str, Any]] = []
        query_params: list[dict[str, Any]] = []
        declarations: list[str] = []
        parameters = [
            *(path_item.get("parameters") or []),
            *(operation.get("parameters") or []),
        ]

        for raw_parameter in parameters:
            parameter = self.resolve_parameter(raw_parameter)
            target = path_params if parameter.get("in") == "path" else query_params
            if parameter.get("in") in {"path", "query"}:
                target.append(parameter)

        def emit_params(name_suffix: str, params: list[dict[str, Any]]) -> str | None:
            if not params:
                return None
            type_name = f"{pascal_case(operation_id)}{name_suffix}"
            lines = [f"export interface {type_name} {{"]
            for param in params:
                required = bool(param.get("required"))
                optional = "" if required else "?"
                lines.append(
                    f"  {property_name(param['name'])}{optional}: "
                    f"{self.schema_to_ts(param.get('schema'))};"
                )
            lines.append("}")
            declarations.append("\n".join(lines))
            return type_name

        path_type = emit_params("Path", path_params)
        query_type = emit_params("Query", query_params)
        return declarations, [path_type or "undefined", query_type or "undefined"]

    def operation_declaration(
        self,
        path: str,
        method: str,
        path_item: dict[str, Any],
        operation: dict[str, Any],
    ) -> tuple[list[str], str]:
        operation_id = operation.get("operationId") or camel_case(f"{method}_{path}")
        operation_name = camel_case(operation_id)
        declarations, [path_type, query_type] = self.operation_parameters(
            operation,
            path_item,
            operation_id,
        )
        body_type = self.request_body_type(operation.get("requestBody")) or "undefined"
        response_type = self.response_type(operation)
        args_type_name = f"{pascal_case(operation_id)}Args"

        members: list[str] = []
        if path_type != "undefined":
            members.append(f"path: {path_type};")
        if query_type != "undefined":
            members.append(f"query?: {query_type};")
        if body_type != "undefined":
            required = bool((operation.get("requestBody") or {}).get("required"))
            optional = "" if required else "?"
            members.append(f"body{optional}: {body_type};")

        if members:
            declarations.append(
                "export interface "
                + args_type_name
                + " {\n  "
                + "\n  ".join(members)
                + "\n}"
            )
            args_signature = f"args: {args_type_name}"
            args_value = "args"
        else:
            args_signature = "args?: undefined"
            args_value = "args"

        function = (
            f"  {operation_name}({args_signature}, config?: AxiosRequestConfig) {{\n"
            f"    return request<{response_type}>("
            f"{quote(method.upper())}, {quote(path)}, {args_value}, config"
            f");\n"
            f"  }}"
        )
        return declarations, function

    def generate(self) -> str:
        declarations = self.component_declarations()
        operation_functions = []

        for path, path_item in sorted((self.spec.get("paths") or {}).items()):
            for method, operation in path_item.items():
                if method not in HTTP_METHODS:
                    continue
                operation_declarations, operation_function = self.operation_declaration(
                    path,
                    method,
                    path_item,
                    operation,
                )
                declarations.extend(operation_declarations)
                operation_functions.append(operation_function)

        return (
            "\n\n".join(
                [
                    "/* eslint-disable */",
                    "// This file is auto-generated by dashboard/scripts/generate_openapi_client.py.",
                    "// Do not edit it manually; update openspec/openapi-v1.yaml and regenerate instead.",
                    "import type { AxiosRequestConfig, AxiosResponse } from 'axios';",
                    "import { apiV1Client } from '../http';",
                    "type RequestArgs = { path?: object; query?: object; body?: unknown } | undefined;",
                    "function encodePathValue(value: unknown): string {\n  return encodeURIComponent(String(value));\n}",
                    "function applyPathParams(path: string, params?: object): string {\n  if (!params) return path;\n  const values = params as Record<string, unknown>;\n  return path.replace(/\\{([^}:]+)(?::path)?\\}/g, (_match, key) => encodePathValue(values[key]));\n}",
                    "function request<T>(method: string, path: string, args?: RequestArgs, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> {\n  return apiV1Client.request<T>({\n    ...config,\n    method,\n    url: applyPathParams(path, args?.path),\n    params: args?.query,\n    data: args?.body,\n  });\n}",
                    *declarations,
                    "export const openApiV1 = {\n"
                    + ",\n".join(operation_functions)
                    + "\n};",
                ]
            )
            + "\n"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the dashboard OpenAPI v1 client."
    )
    parser.add_argument(
        "--spec",
        default=str(DEFAULT_SPEC),
        help="OpenAPI source URL or file path. Defaults to openspec/openapi-v1.yaml.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUTPUT),
        help="Generated TypeScript output path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = load_spec(args.spec)
    output = Path(args.out)
    if not output.is_absolute():
        output = (DASHBOARD_DIR / output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(TypeScriptGenerator(spec).generate(), encoding="utf-8")
    print(f"Generated {output.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
