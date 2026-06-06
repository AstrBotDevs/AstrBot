import uuid
from datetime import datetime, timezone

from sqlmodel import Field, MetaData, SQLModel, Text, UniqueConstraint

from .capabilities import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_INDEX_TYPE,
    DEFAULT_TOP_K_DENSE,
    DEFAULT_TOP_K_SPARSE,
    DEFAULT_TOP_M_FINAL,
)


class BaseKBModel(SQLModel, table=False):
    metadata = MetaData()


class KnowledgeBase(BaseKBModel, table=True):
    """知识库表

    存储知识库的基本信息和统计数据。
    """

    __tablename__ = "knowledge_bases"  # type: ignore

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    kb_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
    )
    kb_name: str = Field(max_length=100, nullable=False)
    description: str | None = Field(default=None, sa_type=Text)
    emoji: str | None = Field(default="📚", max_length=10)
    embedding_provider_id: str | None = Field(default=None, max_length=100)
    rerank_provider_id: str | None = Field(default=None, max_length=100)
    # 分块配置参数
    chunk_size: int | None = Field(default=DEFAULT_CHUNK_SIZE, nullable=True)
    chunk_overlap: int | None = Field(default=DEFAULT_CHUNK_OVERLAP, nullable=True)
    # 索引类型: "flat" (精确) 或 "hnsw" (近似最近邻，适合大规模)
    index_type: str | None = Field(default=DEFAULT_INDEX_TYPE, max_length=10)
    # 检索配置参数
    top_k_dense: int | None = Field(default=DEFAULT_TOP_K_DENSE, nullable=True)
    top_k_sparse: int | None = Field(default=DEFAULT_TOP_K_SPARSE, nullable=True)
    top_m_final: int | None = Field(default=DEFAULT_TOP_M_FINAL, nullable=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )
    doc_count: int = Field(default=0, nullable=False)
    chunk_count: int = Field(default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "kb_name",
            name="uix_kb_name",
        ),
    )


class KBDocument(BaseKBModel, table=True):
    """文档表

    存储上传到知识库的文档元数据。
    """

    __tablename__ = "kb_documents"  # type: ignore

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    doc_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
    )
    kb_id: str = Field(max_length=36, nullable=False, index=True)
    doc_name: str = Field(max_length=255, nullable=False)
    file_type: str = Field(max_length=20, nullable=False)
    file_size: int = Field(nullable=False)
    file_path: str = Field(max_length=512, nullable=False)
    source_type: str = Field(default="file", max_length=20, nullable=False)
    source_uri: str | None = Field(default=None, sa_type=Text)
    content_hash: str | None = Field(default=None, max_length=64, index=True)
    parser_name: str | None = Field(default=None, max_length=100)
    parser_version: str | None = Field(default=None, max_length=50)
    chunker_name: str | None = Field(default=None, max_length=100)
    chunker_version: str | None = Field(default=None, max_length=50)
    status: str = Field(default="ready", max_length=20, nullable=False, index=True)
    error_stage: str | None = Field(default=None, max_length=50)
    error_message: str | None = Field(default=None, sa_type=Text)
    version: int = Field(default=1, nullable=False)
    parent_doc_id: str | None = Field(default=None, max_length=36, index=True)
    chunk_count: int = Field(default=0, nullable=False)
    media_count: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )
    indexed_at: datetime | None = Field(default=None)


class KBMedia(BaseKBModel, table=True):
    """多媒体资源表

    存储从文档中提取的图片、视频等多媒体资源。
    """

    __tablename__ = "kb_media"  # type: ignore

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    media_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
    )
    doc_id: str = Field(max_length=36, nullable=False, index=True)
    kb_id: str = Field(max_length=36, nullable=False, index=True)
    media_type: str = Field(max_length=20, nullable=False)
    file_name: str = Field(max_length=255, nullable=False)
    file_path: str = Field(max_length=512, nullable=False)
    file_size: int = Field(nullable=False)
    mime_type: str = Field(max_length=100, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KBIngestionTask(BaseKBModel, table=True):
    """Persistent knowledge-base ingestion task state."""

    __tablename__ = "kb_ingestion_tasks"  # type: ignore

    id: int | None = Field(
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
        default=None,
    )
    task_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
    )
    kb_id: str = Field(max_length=36, nullable=False, index=True)
    task_type: str = Field(max_length=30, nullable=False, index=True)
    status: str = Field(default="pending", max_length=20, nullable=False, index=True)
    progress_stage: str | None = Field(default=None, max_length=50)
    progress_current: int = Field(default=0, nullable=False)
    progress_total: int = Field(default=100, nullable=False)
    progress: str | None = Field(default=None, sa_type=Text)
    result: str | None = Field(default=None, sa_type=Text)
    error: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )
