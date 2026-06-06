"""Knowledge base capabilities and default limits."""

from typing import Any

ALLOWED_UPLOAD_EXTENSIONS = frozenset(
    {
        "adoc",
        "docx",
        "epub",
        "md",
        "markdown",
        "pdf",
        "rst",
        "txt",
        "xls",
        "xlsx",
    },
)

MAX_UPLOAD_FILE_SIZE = 128 * 1024 * 1024
MAX_UPLOAD_FILES = 10
MAX_BATCH_DELETE_DOCUMENTS = 100
MAX_BATCH_REBUILD_DOCUMENTS = 100
MAX_RETRIEVE_TOP_K = 100
DEFAULT_KB_PAGE_SIZE = 20
DEFAULT_DOCUMENT_PAGE_SIZE = 10
DEFAULT_CHUNK_PAGE_SIZE = 10
DEFAULT_BULK_PAGE_SIZE = 100
DOCUMENT_PAGE_SIZE_OPTIONS = (10, 20, 50, 100)
CHUNK_PAGE_SIZE_OPTIONS = (10, 25, 50, 100)

DOCUMENT_FILTER_STATUSES = (
    "pending",
    "parsing",
    "chunking",
    "embedding",
    "ready",
    "failed",
)
DOCUMENT_FILTER_SOURCE_TYPES = ("file", "url", "import")

FEATURE_SPARSE_RETRIEVAL = True
FEATURE_RERANK = True
FEATURE_URL_IMPORT = True
FEATURE_DOCUMENT_REBUILD = True
FEATURE_KB_REBUILD = True
FEATURE_CONSISTENCY_CHECK = True
FEATURE_CONSISTENCY_REPAIR = True
FEATURE_BATCH_DELETE = True
FEATURE_BATCH_REBUILD = True

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_TOP_K_DENSE = 50
DEFAULT_TOP_K_SPARSE = 50
DEFAULT_TOP_M_FINAL = 5
DEFAULT_INDEX_TYPE = "flat"
DEFAULT_UPLOAD_BATCH_SIZE = 32
DEFAULT_UPLOAD_TASKS_LIMIT = 3
DEFAULT_UPLOAD_MAX_RETRIES = 3


def get_knowledge_base_capabilities() -> dict[str, Any]:
    """Return API-safe knowledge base capabilities."""
    return {
        "upload": {
            "allowed_extensions": sorted(ALLOWED_UPLOAD_EXTENSIONS),
            "max_file_size_bytes": MAX_UPLOAD_FILE_SIZE,
            "max_files_per_upload": MAX_UPLOAD_FILES,
        },
        "defaults": {
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
            "batch_size": DEFAULT_UPLOAD_BATCH_SIZE,
            "tasks_limit": DEFAULT_UPLOAD_TASKS_LIMIT,
            "max_retries": DEFAULT_UPLOAD_MAX_RETRIES,
            "top_k_dense": DEFAULT_TOP_K_DENSE,
            "top_k_sparse": DEFAULT_TOP_K_SPARSE,
            "top_m_final": DEFAULT_TOP_M_FINAL,
            "index_type": DEFAULT_INDEX_TYPE,
        },
        "limits": {
            "max_retrieve_top_k": MAX_RETRIEVE_TOP_K,
            "max_batch_delete_documents": MAX_BATCH_DELETE_DOCUMENTS,
            "max_batch_rebuild_documents": MAX_BATCH_REBUILD_DOCUMENTS,
        },
        "pagination": {
            "document_page_size_options": list(DOCUMENT_PAGE_SIZE_OPTIONS),
            "chunk_page_size_options": list(CHUNK_PAGE_SIZE_OPTIONS),
            "default_kb_page_size": DEFAULT_KB_PAGE_SIZE,
            "default_document_page_size": DEFAULT_DOCUMENT_PAGE_SIZE,
            "default_chunk_page_size": DEFAULT_CHUNK_PAGE_SIZE,
            "bulk_page_size": DEFAULT_BULK_PAGE_SIZE,
        },
        "document_filters": {
            "statuses": list(DOCUMENT_FILTER_STATUSES),
            "source_types": list(DOCUMENT_FILTER_SOURCE_TYPES),
        },
        "features": {
            "sparse_retrieval": FEATURE_SPARSE_RETRIEVAL,
            "rerank": FEATURE_RERANK,
            "url_import": FEATURE_URL_IMPORT,
            "document_rebuild": FEATURE_DOCUMENT_REBUILD,
            "kb_rebuild": FEATURE_KB_REBUILD,
            "consistency_check": FEATURE_CONSISTENCY_CHECK,
            "consistency_repair": FEATURE_CONSISTENCY_REPAIR,
            "batch_delete": FEATURE_BATCH_DELETE,
            "batch_rebuild": FEATURE_BATCH_REBUILD,
        },
    }
