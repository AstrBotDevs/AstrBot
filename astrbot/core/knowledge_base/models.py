"""知识库管理功能的数据模型定义

该模块定义了知识库系统所需的数据模型,包括:
- KnowledgeBase: 知识库表 (存储在独立的 kb.db)
- KBDocument: 文档表 (存储在独立的 kb.db)
- KBChunk: 文档块表 (存储在独立的 kb.db)
- KBMedia: 多媒体资源表 (存储在独立的 kb.db)
- KBSessionConfig: 会话配置表 (存储在独立的 kb.db)

注意:
- 所有模型存储在独立的知识库数据库 (data/knowledge_base/kb.db)
- 与主数据库 (astrbot.db) 完全解耦
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, Text, UniqueConstraint


class KnowledgeBase(SQLModel, table=True):
    """知识库表

    存储知识库的基本信息和统计数据。
    """

    __tablename__ = "knowledge_bases"

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
    enable_rerank: Optional[bool] = Field(default=True, nullable=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )
    doc_count: int = Field(default=0, nullable=False)
    chunk_count: int = Field(default=0, nullable=False)


class KBDocument(SQLModel, table=True):
    """文档表

    存储上传到知识库的文档元数据。
    """

    __tablename__ = "kb_documents"

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


class KBChunk(SQLModel, table=True):
    """文档块表

    存储文档分块后的文本内容和向量索引关联信息。
    """

    __tablename__ = "kb_chunks"

    id: int | None = Field(
        primary_key=True, sa_column_kwargs={"autoincrement": True}, default=None
    )
    chunk_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
        index=True,
    )
    doc_id: str = Field(max_length=36, nullable=False, index=True)
    kb_id: str = Field(max_length=36, nullable=False, index=True)
    chunk_index: int = Field(nullable=False)
    content: str = Field(sa_type=Text, nullable=False)
    char_count: int = Field(nullable=False)
    vec_doc_id: str = Field(max_length=100, nullable=False, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KBMedia(SQLModel, table=True):
    """多媒体资源表

    存储从文档中提取的图片、视频等多媒体资源。
    """

    __tablename__ = "kb_media"

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


class KBSessionConfig(SQLModel, table=True):
    """会话知识库配置表

    存储会话或平台级别的知识库关联配置。
    该表存储在知识库独立数据库中,保持完全解耦。

    支持两种配置范围:
    - platform: 平台级别配置 (如 'qq', 'telegram')
    - session: 会话级别配置 (如 'qq:group:12345')
    """

    __tablename__ = "kb_session_config"

    id: int | None = Field(
        primary_key=True, sa_column_kwargs={"autoincrement": True}, default=None
    )
    config_id: str = Field(
        max_length=36,
        nullable=False,
        unique=True,
        default_factory=lambda: str(uuid.uuid4()),
    )
    scope: str = Field(max_length=20, nullable=False)
    scope_id: str = Field(max_length=255, nullable=False, index=True)
    kb_ids: str = Field(sa_type=Text, nullable=False)
    top_k: Optional[int] = Field(default=None, nullable=True)
    enable_rerank: Optional[bool] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )

    __table_args__ = (
        UniqueConstraint("scope", "scope_id", name="uix_scope_scope_id"),
    )
