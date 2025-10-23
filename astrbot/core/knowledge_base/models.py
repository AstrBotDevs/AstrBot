import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, Text, UniqueConstraint


class KnowledgeBase(SQLModel, table=True):
    """知识库表

    存储知识库的基本信息和统计数据。
    """

    __tablename__ = "knowledge_bases"  # type: ignore

    id: int | None = Field(
        primary_key=True, sa_column_kwargs={"autoincrement": True}, default=None
    )
    kb_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
    )
    kb_name: str = Field(max_length=100, nullable=False)
    description: Optional[str] = Field(default=None, sa_type=Text)
    emoji: Optional[str] = Field(default="📚", max_length=10)
    embedding_provider_id: Optional[str] = Field(default=None, max_length=100)
    rerank_provider_id: Optional[str] = Field(default=None, max_length=100)
    # 分块配置参数
    chunk_size: Optional[int] = Field(default=512, nullable=True)
    chunk_overlap: Optional[int] = Field(default=50, nullable=True)
    # 检索配置参数
    top_k_dense: Optional[int] = Field(default=50, nullable=True)
    top_k_sparse: Optional[int] = Field(default=50, nullable=True)
    top_m_final: Optional[int] = Field(default=5, nullable=True)
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


class KBDocument(SQLModel, table=True):
    """文档表

    存储上传到知识库的文档元数据。
    """

    __tablename__ = "kb_documents"  # type: ignore

    id: int | None = Field(
        primary_key=True, sa_column_kwargs={"autoincrement": True}, default=None
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
    chunk_count: int = Field(default=0, nullable=False)
    media_count: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )


class KBMedia(SQLModel, table=True):
    """多媒体资源表

    存储从文档中提取的图片、视频等多媒体资源。
    """

    __tablename__ = "kb_media"  # type: ignore

    id: int | None = Field(
        primary_key=True, sa_column_kwargs={"autoincrement": True}, default=None
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
