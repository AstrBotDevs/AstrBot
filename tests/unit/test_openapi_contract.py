"""Regression tests for the Dashboard OpenAPI contract artifacts."""

import importlib.util
import json
import re
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.routing import APIWebSocketRoute

from astrbot.dashboard.api.conversations import _export_response
from astrbot.dashboard.api.router import build_api_router
from astrbot.dashboard.services.conversation_service import ConversationExport

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_SOURCE = REPO_ROOT / "openspec" / "openapi-v1.yaml"
PUBLIC_OPENAPI = REPO_ROOT / "docs" / "public" / "openapi.json"
GENERATED_SDK = (
    REPO_ROOT / "dashboard" / "src" / "api" / "generated" / "openapi-v1" / "sdk.gen.ts"
)
HTTP_METHODS = frozenset(
    {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
)

# FastAPI deliberately excludes WebSocket routes from app.openapi(). Keep this
# protocol boundary explicit instead of ignoring a broad family of chat paths.
RUNTIME_WEBSOCKET_OPERATIONS = frozenset(
    {
        ("get", "/api/v1/chat/ws"),
        ("get", "/api/v1/live-chat/ws"),
        ("get", "/api/v1/unified-chat/ws"),
    }
)

# These endpoints intentionally do not return the standard JSON envelope on
# successful requests. The map is deliberately exact so a new raw transport
# has to be documented before it can bypass JSON-envelope assumptions.
NON_JSON_SUCCESS_MEDIA = {
    ("post", "/api/v1/chat"): frozenset({"text/event-stream"}),
    ("get", "/api/v1/chat/runs/{run_id}/stream"): frozenset({"text/event-stream"}),
    (
        "post",
        "/api/v1/chat/sessions/{session_id}/messages/{message_id}/regenerate",
    ): frozenset({"text/event-stream"}),
    ("post", "/api/v1/chat/threads/{thread_id}/messages"): frozenset(
        {"text/event-stream"}
    ),
    ("get", "/api/v1/logs/live"): frozenset({"text/event-stream"}),
    ("get", "/api/v1/appearance/wallpapers/{wallpaper_id}"): frozenset(
        {"image/gif", "image/jpeg", "image/png", "image/webp"}
    ),
    ("get", "/api/v1/appearance/wallpapers/{wallpaper_id}/thumbnail"): frozenset(
        {"image/webp"}
    ),
    ("get", "/api/v1/file"): frozenset({"application/octet-stream"}),
    ("get", "/api/v1/files/content"): frozenset({"application/octet-stream"}),
    ("get", "/api/v1/files/tokens/{file_token}"): frozenset(
        {"application/octet-stream"}
    ),
    ("get", "/api/v1/files/{attachment_id}"): frozenset({"application/octet-stream"}),
    ("get", "/api/v1/files/{attachment_id}/content"): frozenset(
        {"application/octet-stream"}
    ),
    ("get", "/api/v1/data-files/download/{path}"): frozenset(
        {"application/octet-stream"}
    ),
    (
        "get",
        "/api/v1/chat/projects/{project_id}/workspace/file/download",
    ): frozenset({"application/octet-stream"}),
    ("get", "/api/v1/skills/{skill_name}/archive"): frozenset({"application/zip"}),
    ("post", "/api/v1/conversations/export"): frozenset({"application/x-ndjson"}),
    ("get", "/api/v1/backups/{filename}"): frozenset({"application/zip"}),
}

_SDK_BLOCK = re.compile(
    r"^export const (?P<operation_id>[A-Za-z_$][\w$]*) =(?P<body>.*?)(?=^export const |\Z)",
    re.MULTILINE | re.DOTALL,
)
_SDK_URL = re.compile(r"\burl:\s*'(?P<path>[^']+)'")
_SDK_TRANSPORT = re.compile(
    r"\)\.(?:(?P<sse>sse)\.)?(?P<method>delete|get|patch|post|put)\s*<",
)
_SDK_RESPONSE_TYPE = re.compile(r"\bresponseType:\s*'(?P<response_type>[^']+)'")


def _load_source() -> dict:
    source = yaml.safe_load(OPENAPI_SOURCE.read_text(encoding="utf-8"))
    assert isinstance(source, dict)
    return source


def _iter_operations(spec: dict) -> Iterable[tuple[str, str, dict]]:
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                yield method, path, operation


def _operation_set(spec: dict) -> frozenset[tuple[str, str]]:
    return frozenset((method, path) for method, path, _ in _iter_operations(spec))


def _runtime_app() -> FastAPI:
    app = FastAPI()
    app.include_router(build_api_router())
    return app


def _runtime_websocket_operations() -> frozenset[tuple[str, str]]:
    """Return WebSocket routes through FastAPI's included-router tree.

    FastAPI 0.1xx keeps included routers lazy, so ``app.routes`` only contains
    the outer private router wrapper. The route tree is still the runtime
    router used for dispatch and preserves each inclusion prefix.
    """

    def walk(router, prefix: str) -> Iterable[tuple[str, str]]:
        for route in router.routes:
            if isinstance(route, APIWebSocketRoute):
                yield "get", f"{prefix}{route.path}"
                continue
            original_router = getattr(route, "original_router", None)
            include_context = getattr(route, "include_context", None)
            included_prefix = getattr(include_context, "prefix", prefix)
            if original_router is not None:
                yield from walk(original_router, included_prefix)

    api_router = build_api_router()
    return frozenset(walk(api_router, api_router.prefix))


def _response_media(operation: dict) -> frozenset[str]:
    return frozenset(operation.get("responses", {}).get("200", {}).get("content", {}))


def _non_json_success_media(spec: dict) -> dict[tuple[str, str], frozenset[str]]:
    """Return every explicitly-declared non-JSON successful transport.

    FastAPI keeps its default JSON response in the generated operation even
    when an endpoint can stream or download a file on success. JSON is thus
    deliberately normalized away here, while every other media type remains
    subject to the exact allowlist below.
    """
    transports = {}
    for method, path, operation in _iter_operations(spec):
        media_types = _response_media(operation) - {"application/json"}
        if media_types:
            transports[(method, path)] = media_types
    return transports


def _load_public_openapi_filter():
    spec = importlib.util.spec_from_file_location(
        "update_openapi_json_contract_test",
        REPO_ROOT / "docs" / "scripts" / "update_openapi_json.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generated_sdk_operations() -> dict[str, tuple[str, str, str, str | None]]:
    operations: dict[str, tuple[str, str, str, str | None]] = {}
    for match in _SDK_BLOCK.finditer(GENERATED_SDK.read_text(encoding="utf-8")):
        body = match["body"]
        url_match = _SDK_URL.search(body)
        if url_match is None:
            continue
        transport_match = _SDK_TRANSPORT.search(body)
        assert transport_match is not None, match["operation_id"]
        method = transport_match["method"]
        transport = f"sse.{method}" if transport_match["sse"] else method
        response_type_match = _SDK_RESPONSE_TYPE.search(body)
        response_type = (
            response_type_match["response_type"] if response_type_match else None
        )
        operations[match["operation_id"]] = (
            method,
            url_match["path"],
            transport,
            response_type,
        )
    return operations


def test_runtime_v1_operations_match_source_contract() -> None:
    source = _load_source()
    app = _runtime_app()

    source_operations = _operation_set(source)
    runtime_operations = _operation_set(app.openapi())

    assert runtime_operations == source_operations - RUNTIME_WEBSOCKET_OPERATIONS

    source_websockets = frozenset(
        (method, path)
        for method, path, operation in _iter_operations(source)
        if operation.get("x-websocket") is True
    )
    runtime_websockets = _runtime_websocket_operations()
    assert source_websockets == RUNTIME_WEBSOCKET_OPERATIONS
    assert runtime_websockets == RUNTIME_WEBSOCKET_OPERATIONS


def test_generated_sdk_matches_source_operation_ids_and_sse_transport() -> None:
    source_operation_items = list(_iter_operations(_load_source()))
    source_operation_details = {
        operation["operationId"]: (method, path, operation)
        for method, path, operation in source_operation_items
    }
    assert len(source_operation_details) == len(source_operation_items)
    source_operations = {
        operation_id: (method, path)
        for operation_id, (method, path, _operation) in source_operation_details.items()
    }
    expected_sse_transports = {
        operation_id: f"sse.{method}"
        for operation_id, (method, _path, operation) in source_operation_details.items()
        if _response_media(operation) == frozenset({"text/event-stream"})
    }
    expected_blob_response_types = {
        operation_id: "blob"
        for operation_id, (method, path, _operation) in source_operation_details.items()
        if (expected_media := NON_JSON_SUCCESS_MEDIA.get((method, path)))
        and expected_media != frozenset({"text/event-stream"})
    }
    sdk_operations = _generated_sdk_operations()

    assert {
        operation_id: (method, path)
        for operation_id, (
            method,
            path,
            _transport,
            _response_type,
        ) in sdk_operations.items()
    } == source_operations
    assert {
        operation_id: sdk_operations[operation_id][2]
        for operation_id in expected_sse_transports
    } == expected_sse_transports
    assert {
        operation_id: sdk_operations[operation_id][3]
        for operation_id in expected_sse_transports
    } == dict.fromkeys(expected_sse_transports, "text")
    assert {
        operation_id: sdk_operations[operation_id][3]
        for operation_id in expected_blob_response_types
    } == expected_blob_response_types
    assert sdk_operations["streamLiveLogs"] == (
        "get",
        "/api/v1/logs/live",
        "sse.get",
        "text",
    )


def test_public_openapi_is_exact_filtered_source() -> None:
    source = _load_source()
    public_filter = _load_public_openapi_filter()
    public_openapi = json.loads(PUBLIC_OPENAPI.read_text(encoding="utf-8"))

    assert public_filter.PUBLIC_OPEN_API_EXCLUDED_PATHS == {
        "/api/v1/live-chat/ws",
        "/api/v1/unified-chat/ws",
    }
    assert public_openapi == public_filter.filter_public_openapi(source)
    assert "/api/v1/chat/ws" in public_openapi["paths"]
    assert "/api/v1/live-chat/ws" not in public_openapi["paths"]
    assert "/api/v1/unified-chat/ws" not in public_openapi["paths"]


def test_non_json_success_transports_are_explicit_in_source_and_runtime() -> None:
    source = _load_source()
    runtime = _runtime_app().openapi()

    # Do not treat raw transports as a broad exception to the JSON-envelope
    # contract. A new stream/download must be added here intentionally and
    # then represented in the source spec and generated Dashboard client.
    assert _non_json_success_media(source) == NON_JSON_SUCCESS_MEDIA
    assert _non_json_success_media(runtime) == NON_JSON_SUCCESS_MEDIA


def test_conversation_export_response_uses_declared_ndjson_media_type() -> None:
    response = _export_response(
        ConversationExport(BytesIO(b'{"version": 1}\n'), "x.jsonl")
    )

    assert response.media_type == "application/x-ndjson"
