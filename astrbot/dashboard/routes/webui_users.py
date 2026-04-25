import hashlib
import secrets
import string

from quart import g, request
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import WebUIUser
from astrbot.core.utils.datetime_utils import to_utc_isoformat

from .route import Response, Route, RouteContext


def _serialize_user(user: WebUIUser) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "scope": user.scope,
        "enabled": user.enabled,
        "allowed_config_ids": user.allowed_config_ids or [],
        "allow_provider_management": user.allow_provider_management,
        "created_by": user.created_by,
        "created_at": to_utc_isoformat(user.created_at),
        "updated_at": to_utc_isoformat(user.updated_at),
    }


def _normalize_config_ids(value) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        config_id = str(item or "").strip()
        if config_id and config_id not in normalized:
            normalized.append(config_id)
    return normalized


def _generate_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _hash_password(password: str) -> str:
    return hashlib.md5(password.encode("utf-8")).hexdigest()  # noqa: S324


class WebUIUsersRoute(Route):
    def __init__(self, context: RouteContext, db: BaseDatabase) -> None:
        super().__init__(context)
        self.db = db
        self.routes = {
            "/webui/users": ("GET", self.list_users),
            "/webui/users/create": ("POST", self.create_user),
            "/webui/users/update": ("POST", self.update_user),
            "/webui/users/delete": ("POST", self.delete_user),
        }
        self.register_routes()

    def _require_admin(self):
        if g.get("webui_role", "admin") != "admin":
            return Response().error("Permission denied").__dict__
        return None

    async def list_users(self):
        if denied := self._require_admin():
            return denied

        async with self.db.get_db() as session:
            result = await session.execute(
                select(WebUIUser).order_by(col(WebUIUser.created_at).desc())
            )
            users = result.scalars().all()
        return Response().ok([_serialize_user(user) for user in users]).__dict__

    async def create_user(self):
        if denied := self._require_admin():
            return denied

        post_data = await request.json
        if not isinstance(post_data, dict):
            return Response().error("缺少用户数据").__dict__

        username = str(post_data.get("username") or "").strip()
        if not username:
            return Response().error("用户名不能为空").__dict__
        if username == self.config["dashboard"]["username"]:
            return Response().error("不能使用管理员用户名").__dict__

        initial_password = _generate_password()
        user = WebUIUser(
            username=username,
            password=_hash_password(initial_password),
            scope=str(post_data.get("scope") or "chatui").strip() or "chatui",
            enabled=bool(post_data.get("enabled", True)),
            allowed_config_ids=_normalize_config_ids(
                post_data.get("allowed_config_ids")
            ),
            allow_provider_management=bool(
                post_data.get("allow_provider_management", False)
            ),
            created_by=g.get("username", "admin"),
        )

        try:
            async with self.db.get_db() as session:
                async with session.begin():
                    session.add(user)
                await session.refresh(user)
        except IntegrityError:
            return Response().error("用户名已存在").__dict__

        return (
            Response()
            .ok(
                {
                    **_serialize_user(user),
                    "initial_password": initial_password,
                },
                "创建成功",
            )
            .__dict__
        )

    async def update_user(self):
        if denied := self._require_admin():
            return denied

        post_data = await request.json
        if not isinstance(post_data, dict):
            return Response().error("缺少用户数据").__dict__

        user_id = str(post_data.get("user_id") or "").strip()
        if not user_id:
            return Response().error("缺少 user_id").__dict__

        async with self.db.get_db() as session:
            async with session.begin():
                result = await session.execute(
                    select(WebUIUser).where(col(WebUIUser.user_id) == user_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    return Response().error("用户不存在").__dict__

                if "scope" in post_data:
                    user.scope = (
                        str(post_data.get("scope") or "chatui").strip() or "chatui"
                    )
                if "enabled" in post_data:
                    user.enabled = bool(post_data.get("enabled"))
                if "allowed_config_ids" in post_data:
                    user.allowed_config_ids = _normalize_config_ids(
                        post_data.get("allowed_config_ids")
                    )
                if "allow_provider_management" in post_data:
                    user.allow_provider_management = bool(
                        post_data.get("allow_provider_management")
                    )
                new_password = None
                if post_data.get("reset_password"):
                    new_password = _generate_password()
                    user.password = _hash_password(new_password)
                session.add(user)
            await session.refresh(user)

        data = _serialize_user(user)
        if new_password:
            data["new_password"] = new_password
        return Response().ok(data, "更新成功").__dict__

    async def delete_user(self):
        if denied := self._require_admin():
            return denied

        post_data = await request.json
        if not isinstance(post_data, dict):
            return Response().error("缺少用户数据").__dict__
        user_id = str(post_data.get("user_id") or "").strip()
        if not user_id:
            return Response().error("缺少 user_id").__dict__

        async with self.db.get_db() as session:
            async with session.begin():
                result = await session.execute(
                    select(WebUIUser).where(col(WebUIUser.user_id) == user_id)
                )
                user = result.scalar_one_or_none()
                if not user:
                    return Response().error("用户不存在").__dict__
                await session.delete(user)

        return Response().ok(message="删除成功").__dict__
