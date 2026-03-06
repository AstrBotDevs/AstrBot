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
        conversation_id: str,
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
            conversation_id=conversation_id,
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

    async def get_active_by_conversation(
        self, conversation_id: str
    ) -> PendingOperation | None:
        await self.expire_pending_operations()
        operation = await self.db.get_active_pending_operation_by_conversation(
            conversation_id
        )
        if operation is None:
            return None
        if self._is_expired(operation):
            await self.db.update_pending_operation(
                operation.operation_id,
                status="expired",
                reason="token expired",
            )
            return None
        return operation

    async def list_pending(
        self, *, kind: ExtensionKind | None = None
    ) -> list[PendingOperation]:
        await self.expire_pending_operations()
        return await self.db.list_pending_operations(
            status="pending",
            kind=kind.value if kind else None,
        )

    async def list_pending_by_conversation(
        self, conversation_id: str, *, kind: ExtensionKind | None = None
    ) -> list[PendingOperation]:
        await self.expire_pending_operations()
        return await self.db.list_pending_operations(
            status="pending",
            kind=kind.value if kind else None,
            conversation_id=conversation_id,
        )

    async def get_by_operation_id_prefix(self, prefix: str) -> PendingOperation | None:
        if len(prefix) < 4:
            return None
        operations = await self.list_pending()
        matches = [op for op in operations if op.operation_id.startswith(prefix)]
        if len(matches) == 1:
            return matches[0]
        return None

    async def get_by_operation_id_or_token(
        self, operation_id_or_token: str
    ) -> PendingOperation | None:
        operation = await self.get_by_id(operation_id_or_token)
        if operation is None:
            operation = await self.get_by_token(operation_id_or_token)
        if operation is None:
            operation = await self.get_by_operation_id_prefix(operation_id_or_token)
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

    async def start(
        self, operation_id_or_token: str, *, confirmed_by: str
    ) -> PendingOperation | None:
        operation = await self.get_by_operation_id_or_token(operation_id_or_token)
        if operation is None:
            return None
        if operation.status != "pending":
            return None
        return await self.db.update_pending_operation(
            operation.operation_id,
            status="running",
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
