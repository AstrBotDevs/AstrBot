from typing import Any

from fastapi import APIRouter, Depends, Request, UploadFile

from astrbot import logger
from astrbot.core.auth.models import Resource
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import error, ok
from astrbot.dashboard.schemas import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseImportRequest,
    KnowledgeBaseRequest,
    KnowledgeBaseRetrieveRequest,
    KnowledgeBaseUrlImportRequest,
)
from astrbot.dashboard.services.knowledge_base_service import (
    KnowledgeBaseService,
    KnowledgeBaseServiceError,
)

from .auth import AuthContext, object_resource, require_resource_action, require_scope
from .error_handling import internal_error_response

router = APIRouter(tags=["Knowledge Bases"])


def get_service(request: Request) -> KnowledgeBaseService:
    return request.app.state.services.knowledge_bases


async def require_kb_scope(request: Request) -> AuthContext:
    auth = await require_scope(request, "kb")
    path_params = request.path_params
    if chunk_id := path_params.get("chunk_id"):
        resource = object_resource(
            "knowledge-base-chunk",
            path_params.get("kb_id", ""),
            request.query_params.get("document_id")
            or request.query_params.get("doc_id")
            or "",
            chunk_id,
        )
    elif document_id := path_params.get("document_id"):
        resource = object_resource(
            "knowledge-base-document", path_params.get("kb_id", ""), document_id
        )
    elif kb_id := path_params.get("kb_id"):
        resource = object_resource("knowledge-base", kb_id)
    else:
        resource = Resource.named("knowledge-base", "collection")
    await require_resource_action(
        request,
        auth,
        action="data.manage",
        resource=resource,
    )
    return auth


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return default


async def _run(operation, *, prefix: str):
    try:
        result = await run_maybe_async(operation)
        if isinstance(result, tuple):
            data, message = result
            return ok(data, message)
        return ok(result)
    except KnowledgeBaseServiceError as exc:
        return error(str(exc))
    except Exception as exc:
        return internal_error_response(logger, prefix, exc)


@router.get("/knowledge-bases")
async def list_knowledge_bases(
    request: Request,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.list_kbs(
            page=_to_int(request.query_params.get("page"), 1),
            page_size=_to_int(request.query_params.get("page_size"), 20),
        ),
        prefix="获取知识库列表失败",
    )


@router.post("/knowledge-bases")
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.create_kb(payload.canonical_payload()),
        prefix="创建知识库失败",
    )


@router.get("/knowledge-bases/tasks/{task_id}")
async def get_knowledge_base_task(
    task_id: str,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.get_upload_progress(task_id),
        prefix="获取上传进度失败",
    )


@router.get("/knowledge-bases/{kb_id}")
async def get_knowledge_base(
    kb_id: str,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(lambda: service.get_kb(kb_id), prefix="获取知识库详情失败")


@router.put("/knowledge-bases/{kb_id}")
async def update_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseRequest,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.update_kb({**payload.canonical_payload(), "kb_id": kb_id}),
        prefix="更新知识库失败",
    )


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base(
    kb_id: str,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.delete_kb({"kb_id": kb_id}), prefix="删除知识库失败"
    )


@router.get("/knowledge-bases/{kb_id}/stats")
async def get_knowledge_base_stats(
    kb_id: str,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.get_kb_stats(kb_id),
        prefix="获取知识库统计失败",
    )


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_knowledge_base_documents(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.list_documents(
            kb_id=kb_id,
            page=_to_int(request.query_params.get("page"), 1),
            page_size=_to_int(request.query_params.get("page_size"), 100),
            search=request.query_params.get("search"),
        ),
        prefix="获取文档列表失败",
    )


@router.post("/knowledge-bases/{kb_id}/documents")
async def upload_knowledge_base_document(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    async def _operation():
        form = await request.form()
        form_data = {
            key: value
            for key, value in form.multi_items()
            if not isinstance(value, UploadFile)
        }
        form_data["kb_id"] = kb_id
        files = [
            value
            for key, value in form.multi_items()
            if isinstance(value, UploadFile)
            and (key == "file" or key.startswith("file") or key == "files[]")
        ]
        return await service.upload_document(
            content_type=request.headers.get("content-type"),
            form_data=form_data,
            files=files,
        )

    return await _run(_operation, prefix="上传文档失败")


@router.post("/knowledge-bases/{kb_id}/documents/import")
async def import_knowledge_base_documents(
    kb_id: str,
    payload: KnowledgeBaseImportRequest,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    body = payload.model_dump(exclude_none=True)
    return await _run(
        lambda: service.import_documents({**body, "kb_id": kb_id}),
        prefix="导入文档失败",
    )


@router.post("/knowledge-bases/{kb_id}/documents/import-url")
async def import_knowledge_base_document_url(
    kb_id: str,
    payload: KnowledgeBaseUrlImportRequest,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    body = payload.model_dump(exclude_none=True)
    return await _run(
        lambda: service.upload_document_from_url({**body, "kb_id": kb_id}),
        prefix="从URL上传文档失败",
    )


@router.get("/knowledge-bases/{kb_id}/documents/{document_id}")
async def get_knowledge_base_document(
    kb_id: str,
    document_id: str,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.get_document(kb_id=kb_id, doc_id=document_id),
        prefix="获取文档详情失败",
    )


@router.delete("/knowledge-bases/{kb_id}/documents/{document_id}")
async def delete_knowledge_base_document(
    kb_id: str,
    document_id: str,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    return await _run(
        lambda: service.delete_document({"kb_id": kb_id, "doc_id": document_id}),
        prefix="删除文档失败",
    )


@router.get("/knowledge-bases/{kb_id}/chunks")
async def list_knowledge_base_chunks(
    kb_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    document_id = request.query_params.get("document_id") or request.query_params.get(
        "doc_id"
    )
    return await _run(
        lambda: service.list_chunks(
            kb_id=kb_id,
            doc_id=document_id,
            page=_to_int(request.query_params.get("page"), 1),
            page_size=_to_int(request.query_params.get("page_size"), 100),
        ),
        prefix="获取块列表失败",
    )


@router.delete("/knowledge-bases/{kb_id}/chunks/{chunk_id}")
async def delete_knowledge_base_chunk(
    kb_id: str,
    chunk_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    document_id = request.query_params.get("document_id") or request.query_params.get(
        "doc_id"
    )
    return await _run(
        lambda: service.delete_chunk(
            {"kb_id": kb_id, "chunk_id": chunk_id, "doc_id": document_id}
        ),
        prefix="删除文本块失败",
    )


@router.post("/knowledge-bases/{kb_id}/retrieve")
async def retrieve_knowledge_base(
    kb_id: str,
    payload: KnowledgeBaseRetrieveRequest,
    _auth: AuthContext = Depends(require_kb_scope),
    service: KnowledgeBaseService = Depends(get_service),
):
    body = payload.model_dump(exclude_none=True)
    return await _run(
        lambda: service.retrieve({**body, "kb_id": kb_id}),
        prefix="检索失败",
    )
