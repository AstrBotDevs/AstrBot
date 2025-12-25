"""API Key 服务

提供 API Key 的创建、查询、删除等业务逻辑
"""

import hashlib
import secrets
from datetime import datetime, timezone

from quart import g, request
from sqlalchemy import select
from sqlmodel import col, desc

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import ApiKey

from ..entities import Response
from . import BaseService


class ApiKeyService(BaseService):
    """API Key 服务"""

    def __init__(self, core_lifecycle, db: BaseDatabase):
        super().__init__(core_lifecycle)
        self.db = db

    def _generate_api_key(self) -> str:
        """生成一个安全的 API Key"""
        # 生成 32 字节的随机 token，然后编码为 base64 URL-safe 字符串
        token = secrets.token_urlsafe(32)
        # 添加前缀以便识别
        return f"astrbot_{token}"

    def _hash_api_key(self, api_key: str) -> str:
        """对 API Key 进行哈希"""
        return hashlib.sha256(api_key.encode()).hexdigest()

    async def create_api_key(self):
        """创建新的 API Key"""
        post_data = await request.json
        name = post_data.get("name", "")

        # 获取当前用户名（从 JWT token 中）
        username = getattr(g, "username", None)
        if not username:
            return Response().error("未授权").__dict__

        # 生成新的 API Key
        raw_api_key = self._generate_api_key()
        hashed_key = self._hash_api_key(raw_api_key)

        # 创建数据库记录
        async with self.db.get_db() as session:
            api_key_obj = ApiKey(
                api_key=hashed_key,
                username=username,
                name=name if name else None,
            )
            session.add(api_key_obj)
            await session.commit()
            await session.refresh(api_key_obj)

            # 返回完整的 API Key（只在创建时返回一次）
            return (
                Response()
                .ok(
                    {
                        "key_id": api_key_obj.key_id,
                        "api_key": raw_api_key,  # 只返回一次，前端需要保存
                        "name": api_key_obj.name,
                        "username": api_key_obj.username,
                        "created_at": api_key_obj.created_at.isoformat(),
                    },
                    "API Key 创建成功，请妥善保管",
                )
                .__dict__
            )

    async def list_api_keys(self):
        """列出当前用户的所有 API Keys"""
        username = getattr(g, "username", None)
        if not username:
            return Response().error("未授权").__dict__

        async with self.db.get_db() as session:
            stmt = (
                select(ApiKey)
                .where(col(ApiKey.username) == username)
                .order_by(desc(ApiKey.created_at))
            )
            result = await session.execute(stmt)
            api_keys = result.scalars().all()

            # 不返回实际的 API Key，只返回元数据
            keys_data = [
                {
                    "key_id": key.key_id,
                    "name": key.name,
                    "username": key.username,
                    "created_at": key.created_at.isoformat(),
                    "expires_at": key.expires_at.isoformat()
                    if key.expires_at
                    else None,
                    "last_used_at": key.last_used_at.isoformat()
                    if key.last_used_at
                    else None,
                }
                for key in api_keys
            ]

            return Response().ok(keys_data).__dict__

    async def delete_api_key(self, key_id: str):
        """删除指定的 API Key"""
        username = getattr(g, "username", None)
        if not username:
            return Response().error("未授权").__dict__

        async with self.db.get_db() as session:
            stmt = select(ApiKey).where(
                col(ApiKey.key_id) == key_id, col(ApiKey.username) == username
            )
            result = await session.execute(stmt)
            api_key = result.scalar_one_or_none()

            if not api_key:
                return Response().error("API Key 不存在或无权限").__dict__

            await session.delete(api_key)
            await session.commit()

            return Response().ok(None, "API Key 删除成功").__dict__

    async def verify_api_key(self, api_key: str) -> ApiKey | None:
        """验证 API Key 是否有效

        返回对应的 ApiKey 对象，如果无效则返回 None
        """
        hashed_key = self._hash_api_key(api_key)

        async with self.db.get_db() as session:
            stmt = select(ApiKey).where(col(ApiKey.api_key) == hashed_key)
            result = await session.execute(stmt)
            api_key_obj = result.scalar_one_or_none()

            if api_key_obj:
                # 更新最后使用时间
                api_key_obj.last_used_at = datetime.now(timezone.utc)
                await session.commit()

            return api_key_obj
