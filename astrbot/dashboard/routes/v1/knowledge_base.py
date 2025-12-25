from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

from ...services.knowledge_base import KnowledgeBaseService
from ..route import Route, RouteContext


class V1KnowledgeBaseRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle):
        super().__init__(context)
        self.kb_service = KnowledgeBaseService(core_lifecycle)
        self.routes = {
            "/v1/kbs": [("GET", self.kb_service.list_kbs, "v1_kb_list_kbs")],
            "/v1/kb": [
                ("POST", self.kb_service.create_kb, "v1_kb_create_kb"),
            ],
            "/v1/kb/<kb_id>": [
                ("GET", self.kb_service.get_kb, "v1_kb_get_kb"),
                ("PUT", self.kb_service.update_kb, "v1_kb_update_kb"),
                ("DELETE", self.kb_service.delete_kb, "v1_kb_delete_kb"),
            ],
            "/v1/kb/<kb_id>/documents": (
                "GET",
                self.kb_service.list_documents,
                "v1_kb_list_documents",
            ),
            "/v1/kb/<kb_id>/document-file": [
                ("POST", self.kb_service.upload_document, "v1_kb_upload_document"),
            ],
            "/v1/kb/<kb_id>/document-url": [
                (
                    "POST",
                    self.kb_service.upload_document_from_url,
                    "v1_kb_upload_document_from_url",
                ),
            ],
            "/v1/kb/<kb_id>/document-preload": [
                ("POST", self.kb_service.import_documents, "v1_kb_import_documents"),
            ],
            "/v1/kb/<kb_id>/document-progress/<task_id>": [
                (
                    "GET",
                    self.kb_service.get_upload_progress,
                    "v1_kb_get_upload_progress",
                ),
            ],
            "/v1/kb/<kb_id>/document/<doc_id>": [
                ("GET", self.kb_service.get_document, "v1_kb_get_document"),
                ("DELETE", self.kb_service.delete_document, "v1_kb_delete_document"),
            ],
            "/v1/kb/<kb_id>/document/<doc_id>/chunks": [
                ("GET", self.kb_service.list_chunks, "v1_kb_list_chunks"),
            ],
            "/v1/kb/<kb_id>/document/<doc_id>/chunk/<chunk_id>": [
                ("DELETE", self.kb_service.delete_chunk, "v1_kb_delete_chunk"),
            ],
        }
        self.register_routes()
