"""
知识库管理模块

提供文档上传、解析、分块、向量化、检索等功能
"""

from astrbot.core.db.po import KBSessionConfig
from astrbot.core.knowledge_base.models import (
    KBChunk,
    KBDocument,
    KBMedia,
    KnowledgeBase,
)

# 注意: 以下导入在对应模块实现后取消注释
from .database import KBDatabase
from .manager import KBManager
from .manager_ops import KBManagerOps
from .session_config_db import SessionConfigDB

# from .injector import KnowledgeBaseInjector

__all__ = [
    "KnowledgeBase",
    "KBDocument",
    "KBChunk",
    "KBMedia",
    "KBSessionConfig",
    "KBDatabase",
    "SessionConfigDB",
    "KBManager",
    "KBManagerOps",
    # "KnowledgeBaseInjector",
]
