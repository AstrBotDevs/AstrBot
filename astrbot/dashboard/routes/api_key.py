import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from quart import g, request

from astrbot.core.db import BaseDatabase

from .route import Response, Route, RouteContext

ALL_OPEN_API_SCOPES = ("chat", "config", "file", "im")


class ApiKeyRoute(Route):
    def __init__(self, context: RouteContext, db: BaseDatabase) -> None:
        super().__init__(context)
        self.db = db
        self.routes = {
            "/apikey/list": ("GET", self.list_api_keys),
            "/apikey/create": ("POST", self.create_api_key),
            "/apikey/revoke": ("POST", self.revoke_api_key),
            "/apikey/delete": ("POST", self.delete_api_key),
        }
        self.register_routes()

    @staticmethod
    def _normalize_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def _serialize_datetime(cls, dt: datetime | None) -> str | None:
        normalized = cls._normalize_utc(dt)
        if normalized is None:
            return None
        return normalized.astimezone().isoformat()

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            raw_key.encode("utf-8"),
            b"astrbot_api_key",
            100_000,
        ).hex()

    @staticmethod
    def _serialize_api_key(key) -> dict:
        expires_at = ApiKeyRoute._normalize_utc(key.expires_at)
        return {
            "key_id": key.key_id,
            "name": key.name,
            "key_prefix": key.key_prefix,
            "scopes": key.scopes or [],
            "created_by": key.created_by,
            "created_at": ApiKeyRoute._serialize_datetime(key.created_at),
            "updated_at": ApiKeyRoute._serialize_datetime(key.updated_at),
            "last_used_at": ApiKeyRoute._serialize_datetime(key.last_used_at),
            "expires_at": ApiKeyRoute._serialize_datetime(key.expires_at),
            "revoked_at": ApiKeyRoute._serialize_datetime(key.revoked_at),
            "is_revoked": key.revoked_at is not None,
            "is_expired": bool(expires_at and expires_at < datetime.now(timezone.utc)),
        }

    async def list_api_keys(self):
        keys = await self.db.list_api_keys()
        return (
            Response().ok(data=[self._serialize_api_key(key) for key in keys]).__dict__
        )

    async def create_api_key(self):
        post_data = await request.json or {}

        name = str(post_data.get("name", "")).strip() or "Untitled API Key"
        scopes = post_data.get("scopes")
        if scopes is None:
            normalized_scopes = list(ALL_OPEN_API_SCOPES)
        elif isinstance(scopes, list):
            normalized_scopes = [
                scope
                for scope in scopes
                if isinstance(scope, str) and scope in ALL_OPEN_API_SCOPES
            ]
            normalized_scopes = list(dict.fromkeys(normalized_scopes))
            if not normalized_scopes:
                return Response().error("At least one valid scope is required").__dict__
        else:
            return Response().error("Invalid scopes").__dict__

        expires_at = None
        expires_in_days = post_data.get("expires_in_days")
        if expires_in_days is not None:
            try:
                expires_in_days_int = int(expires_in_days)
            except (TypeError, ValueError):
                return Response().error("expires_in_days must be an integer").__dict__
            if expires_in_days_int <= 0:
                return (
                    Response().error("expires_in_days must be greater than 0").__dict__
                )
            expires_at = datetime.now(timezone.utc) + timedelta(
                days=expires_in_days_int
            )

        raw_key = f"abk_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(raw_key)
        key_prefix = raw_key[:12]
        created_by = g.get("username", "unknown")

        api_key = await self.db.create_api_key(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=normalized_scopes,  # type: ignore
            created_by=created_by,
            expires_at=expires_at,
        )

        payload = self._serialize_api_key(api_key)
        payload["api_key"] = raw_key
        return Response().ok(data=payload).__dict__

    async def revoke_api_key(self):
        post_data = await request.json or {}
        key_id = post_data.get("key_id")
        if not key_id:
            return Response().error("Missing key: key_id").__dict__

        success = await self.db.revoke_api_key(key_id)
        if not success:
            return Response().error("API key not found").__dict__
        return Response().ok().__dict__

    async def delete_api_key(self):
        post_data = await request.json or {}
        key_id = post_data.get("key_id")
        if not key_id:
            return Response().error("Missing key: key_id").__dict__

        success = await self.db.delete_api_key(key_id)
        if not success:
            return Response().error("API key not found").__dict__
        return Response().ok().__dict__
