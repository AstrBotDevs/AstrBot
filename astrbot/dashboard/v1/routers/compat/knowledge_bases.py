from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.services.route_bridge_service import DashboardRouteBridgeService

from ...auth import AuthContext
from .common import get_bridge, require_kb_scope
from .common import json_or_empty as _json_or_empty

router = APIRouter(tags=["Knowledge Bases"])


@router.get("/knowledge-bases")
async def list_knowledge_bases(
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(request, auth, method="GET", target_path="/api/kb/list")


@router.post("/knowledge-bases")
async def create_knowledge_base(
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="POST", target_path="/api/kb/create"
    )


@router.get("/knowledge-bases/tasks/{task_id}")
async def get_knowledge_base_task(
    task_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/kb/document/upload/progress",
        query={"task_id": task_id},
    )


@router.get("/knowledge-bases/{kb_id}")
async def get_knowledge_base(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request, auth, method="GET", target_path="/api/kb/get", query={"kb_id": kb_id}
    )


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/kb/update",
        json_body={"kb_id": kb_id, **body},
    )


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/kb/delete",
        json_body={"kb_id": kb_id},
    )


@router.get("/knowledge-bases/{kb_id}/stats")
async def get_knowledge_base_stats(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/kb/stats",
        query={"kb_id": kb_id},
    )


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_knowledge_base_documents(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    query = dict(request.query_params)
    query["kb_id"] = kb_id
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/kb/document/list",
        query=query,
    )


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_knowledge_base_document(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/kb/document/upload",
        query={"kb_id": kb_id},
    )


@router.post("/knowledge-bases/{kb_id}/documents/import")
async def import_knowledge_base_documents(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/kb/document/import",
        json_body={"kb_id": kb_id, **body},
    )


@router.post("/knowledge-bases/{kb_id}/documents/import-url")
async def import_knowledge_base_document_url(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/kb/document/upload/url",
        json_body={"kb_id": kb_id, **body},
    )


@router.get("/knowledge-bases/{kb_id}/documents/{document_id}")
async def get_knowledge_base_document(
    kb_id: str,
    document_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/kb/document/get",
        query={"kb_id": kb_id, "doc_id": document_id},
    )


@router.delete("/knowledge-bases/{kb_id}/documents/{document_id}")
async def delete_knowledge_base_document(
    kb_id: str,
    document_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/kb/document/delete",
        json_body={"kb_id": kb_id, "doc_id": document_id},
    )


@router.get("/knowledge-bases/{kb_id}/chunks")
async def list_knowledge_base_chunks(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    query = dict(request.query_params)
    query["kb_id"] = kb_id
    if "document_id" in query and "doc_id" not in query:
        query["doc_id"] = query.pop("document_id")
    return await bridge.forward(
        request,
        auth,
        method="GET",
        target_path="/api/kb/chunk/list",
        query=query,
    )


@router.delete("/knowledge-bases/{kb_id}/chunks/{chunk_id}")
async def delete_knowledge_base_chunk(
    kb_id: str,
    chunk_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    document_id = request.query_params.get("document_id") or request.query_params.get(
        "doc_id"
    )
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/kb/chunk/delete",
        json_body={"kb_id": kb_id, "chunk_id": chunk_id, "doc_id": document_id},
    )


@router.post("/knowledge-bases/{kb_id}/retrieve")
async def retrieve_knowledge_base(
    kb_id: str,
    request: Request,
    auth: AuthContext = Depends(require_kb_scope),
    bridge: DashboardRouteBridgeService = Depends(get_bridge),
):
    body = await _json_or_empty(request)
    return await bridge.forward(
        request,
        auth,
        method="POST",
        target_path="/api/kb/retrieve",
        json_body={"kb_id": kb_id, **body},
    )
