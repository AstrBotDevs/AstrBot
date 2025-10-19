"""会话知识库配置数据库操作

该模块封装会话知识库配置的数据库查询操作。

注意: 会话配置表 (kb_session_config) 存储在知识库独立数据库 (kb.db) 中,
      而不是主数据库 (astrbot.db) 中,以实现完全解耦。
"""

import json
from typing import Optional

from sqlalchemy import select

from astrbot.core.knowledge_base.kb_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.models import KBSessionConfig


class SessionConfigDB:
    """会话知识库配置数据库操作类

    职责:
    - 提供会话知识库配置管理
    - 统一异常处理

    注意: 该类操作知识库独立数据库,实现完全解耦
    """

    def __init__(self, db: KBSQLiteDatabase):
        """初始化会话配置数据库操作类

        Args:
            db: 知识库独立数据库实例 (kb.db),不是主数据库
        """
        self.db = db

    async def get_session_kb_ids(self, session_id: str) -> list[str]:
        """获取会话关联的知识库 ID 列表

        查找顺序:
        1. 会话级别配置 (优先)
        2. 平台级别配置
        3. 返回空列表
        """
        async with self.db.get_db() as session:
            # 1. 查找会话级别配置
            stmt = select(KBSessionConfig).where(
                KBSessionConfig.scope == "session",
                KBSessionConfig.scope_id == session_id,
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                return json.loads(config.kb_ids)

            # 2. 提取平台 ID (格式: platform:xxx:session_id)
            parts = session_id.split(":")
            if len(parts) >= 2:
                platform_id = parts[0]

                # 查找平台级别配置
                stmt = select(KBSessionConfig).where(
                    KBSessionConfig.scope == "platform",
                    KBSessionConfig.scope_id == platform_id,
                )
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()

                if config:
                    return json.loads(config.kb_ids)

            # 3. 无配置
            return []

    async def set_session_kb_ids(
        self,
        scope: str,
        scope_id: str,
        kb_ids: list[str],
        top_k: Optional[int] = None,
        enable_rerank: Optional[bool] = None,
    ) -> KBSessionConfig:
        """设置会话知识库配置

        Args:
            scope: 配置范围 (session/platform)
            scope_id: 范围标识 (会话 ID 或平台 ID)
            kb_ids: 知识库 ID 列表
            top_k: 返回结果数量 (可选)
            enable_rerank: 是否启用 Rerank (可选)
        """
        async with self.db.get_db() as session:
            # 查找现有配置
            stmt = select(KBSessionConfig).where(
                KBSessionConfig.scope == scope,
                KBSessionConfig.scope_id == scope_id,
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                # 更新现有配置
                config.kb_ids = json.dumps(kb_ids)
                if top_k is not None:
                    config.top_k = top_k
                if enable_rerank is not None:
                    config.enable_rerank = enable_rerank
            else:
                # 创建新配置
                config = KBSessionConfig(
                    scope=scope,
                    scope_id=scope_id,
                    kb_ids=json.dumps(kb_ids),
                    top_k=top_k,
                    enable_rerank=enable_rerank,
                )
                session.add(config)

            await session.commit()
            await session.refresh(config)
            return config

    async def delete_session_kb_config(self, scope: str, scope_id: str) -> bool:
        """删除会话知识库配置"""
        async with self.db.get_db() as session:
            stmt = select(KBSessionConfig).where(
                KBSessionConfig.scope == scope,
                KBSessionConfig.scope_id == scope_id,
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if not config:
                return False

            await session.delete(config)
            await session.commit()
            return True

    async def list_all_session_configs(
        self, offset: int = 0, limit: int = 100, scope: Optional[str] = None
    ) -> list[KBSessionConfig]:
        """列出所有会话配置"""
        async with self.db.get_db() as session:
            stmt = select(KBSessionConfig)

            if scope:
                stmt = stmt.where(KBSessionConfig.scope == scope)

            stmt = (
                stmt.offset(offset)
                .limit(limit)
                .order_by(KBSessionConfig.created_at.desc())
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())
