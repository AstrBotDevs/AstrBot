from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import PendingOperation

from .model import ExtensionKind


@dataclass(slots=True)
class PendingOperationService:
    db: BaseDatabase
    token_ttl_seconds: int = 900

    @staticmethod
    def _is_expired(operation: PendingOperation) -> bool:
        expires_at = operation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)

    async def expire_pending_operations(self) -> int:
        return await self.db.expire_pending_operations(
            before=datetime.now(timezone.utc)
        )

    async def create(
        self,
        *,
        requester_id: str,
        requester_role: str,
        kind: ExtensionKind,
        provider: str,
        target: str,
        payload: dict[str, Any],
        reason: str,
        decision: str | None = None,
    ) -> PendingOperation:
        operation_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(16)
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.token_ttl_seconds
        )
        return await self.db.create_pending_operation(
            operation_id=operation_id,
            token=token,
            requester_id=requester_id,
            requester_role=requester_role,
            kind=kind.value,
            provider=provider,
            target=target,
            payload=payload,
            status="pending",
            reason=reason,
            decision=decision,
            expires_at=expires_at,
        )

    async def get_by_id(self, operation_id: str) -> PendingOperation | None:
        return await self.db.get_pending_operation_by_operation_id(operation_id)

    async def get_by_token(self, token: str) -> PendingOperation | None:
        return await self.db.get_pending_operation_by_token(token)

    async def list_pending(
        self, *, kind: ExtensionKind | None = None
    ) -> list[PendingOperation]:
        await self.expire_pending_operations()
        return await self.db.list_pending_operations(
            status="pending",
            kind=kind.value if kind else None,
        )

    async def get_by_operation_id_or_token(
        self, operation_id_or_token: str
    ) -> PendingOperation | None:
        operation = await self.get_by_id(operation_id_or_token)
        if operation is None:
            operation = await self.get_by_token(operation_id_or_token)
        if operation is not None and operation.status == "pending":
            if self._is_expired(operation):
                await self.db.update_pending_operation(
                    operation.operation_id,
                    status="expired",
                    reason="token expired",
                )
                return None
            return operation
        return operation

    async def confirm(
        self, operation_id_or_token: str, *, confirmed_by: str
    ) -> PendingOperation | None:
        operation = await self.get_by_operation_id_or_token(operation_id_or_token)
        if operation is None:
            return None
        if operation.status != "pending":
            return None
        return await self.db.update_pending_operation(
            operation.operation_id,
            status="confirmed",
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc),
        )

    async def reject(
        self, operation_id_or_token: str, *, reason: str = "rejected by user"
    ) -> PendingOperation | None:
        operation = await self.get_by_operation_id_or_token(operation_id_or_token)
        if operation is None:
            return None
        if operation.status != "pending":
            return None
        return await self.db.update_pending_operation(
            operation.operation_id,
            status="rejected",
            reason=reason,
        )
