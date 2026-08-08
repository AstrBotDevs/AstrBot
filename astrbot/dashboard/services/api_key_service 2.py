from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from astrbot.core.db import BaseDatabase
from astrbot.core.utils.datetime_utils import normalize_datetime_utc

from .auth_service import ALL_OPEN_API_SCOPES, OPEN_API_SCOPE_INCLUDES


class ApiKeyServiceError(Exception):
    pass


class ApiKeyService:
    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            raw_key.encode("utf-8"),
            b"astrbot_api_key",
            100_000,
        ).hex()

    @staticmethod
    def _normalize_utc(dt: datetime | None) -> datetime | None:
        return normalize_datetime_utc(dt)

    @classmethod
    def _serialize_datetime(cls, dt: datetime | None) -> str | None:
        normalized = cls._normalize_utc(dt)
        if normalized is None:
            return None
        return normalized.astimezone().isoformat()

    @classmethod
    def serialize_api_key(cls, key) -> dict:
        expires_at = cls._normalize_utc(key.expires_at)
        return {
            "key_id": key.key_id,
            "name": key.name,
            "key_prefix": key.key_prefix,
            "scopes": key.scopes or [],
            "created_by": key.created_by,
            "created_at": cls._serialize_datetime(key.created_at),
            "updated_at": cls._serialize_datetime(key.updated_at),
            "last_used_at": cls._serialize_datetime(key.last_used_at),
            "expires_at": cls._serialize_datetime(key.expires_at),
            "revoked_at": cls._serialize_datetime(key.revoked_at),
            "is_revoked": key.revoked_at is not None,
            "is_expired": bool(expires_at and expires_at < datetime.now(timezone.utc)),
        }

    @staticmethod
    def _normalize_scopes(raw_scopes: Any) -> list[str]:
        if raw_scopes is None:
            return list(ALL_OPEN_API_SCOPES)
        if not isinstance(raw_scopes, list):
            raise ApiKeyServiceError("Invalid scopes")

        scopes = []
        invalid_scopes = []
        for scope in raw_scopes:
            if isinstance(scope, str) and scope in ALL_OPEN_API_SCOPES:
                scopes.append(scope)
            else:
                invalid_scopes.append(str(scope))
        if invalid_scopes:
            raise ApiKeyServiceError(f"Invalid scopes: {', '.join(invalid_scopes)}")
        for scope in tuple(scopes):
            scopes.extend(OPEN_API_SCOPE_INCLUDES.get(scope, ()))
        normalized_scopes = list(dict.fromkeys(scopes))
        if not normalized_scopes:
            raise ApiKeyServiceError("At least one valid scope is required")
        return normalized_scopes

    @staticmethod
    def _resolve_expires_at(expires_in_days: Any) -> datetime | None:
        if expires_in_days is None:
            return None
        try:
            expires_in_days_int = int(expires_in_days)
        except (TypeError, ValueError) as exc:
            raise ApiKeyServiceError("expires_in_days must be an integer") from exc
        if expires_in_days_int <= 0:
            raise ApiKeyServiceError("expires_in_days must be greater than 0")
        return datetime.now(timezone.utc) + timedelta(days=expires_in_days_int)

    async def list_api_keys(self) -> list[dict]:
        keys = await self.db.list_api_keys()
        return [self.serialize_api_key(key) for key in keys]

    async def create_api_key(self, payload: dict, *, created_by: str) -> dict:
        name = str(payload.get("name", "")).strip() or "Untitled API Key"
        scopes = self._normalize_scopes(payload.get("scopes"))
        expires_at = self._resolve_expires_at(payload.get("expires_in_days"))

        raw_key = f"abk_{secrets.token_urlsafe(32)}"
        api_key = await self.db.create_api_key(
            name=name,
            key_hash=self.hash_key(raw_key),
            key_prefix=raw_key[:12],
            scopes=scopes,  # type: ignore
            created_by=created_by,
            expires_at=expires_at,
        )

        result = self.serialize_api_key(api_key)
        result["api_key"] = raw_key
        return result

    async def revoke_api_key(self, key_id: str | None) -> bool:
        if not key_id:
            raise ApiKeyServiceError("Missing key: key_id")
        return await self.db.revoke_api_key(key_id)

    async def delete_api_key(self, key_id: str | None) -> bool:
        if not key_id:
            raise ApiKeyServiceError("Missing key: key_id")
        return await self.db.delete_api_key(key_id)
