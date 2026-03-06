from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from astrbot.core import logger
from astrbot.core.db.po import PendingOperation

from .model import (
    ExtensionKind,
    InstallCandidate,
    InstallRequest,
    InstallResult,
    InstallResultStatus,
    PolicyAction,
)
from .pending_operation import PendingOperationService
from .policy import ExtensionPolicyEngine


class ExtensionAdapter(Protocol):
    provider: str
    kind: ExtensionKind

    async def search(self, query: str) -> list[InstallCandidate]: ...

    async def install(self, candidate: InstallCandidate) -> dict[str, Any]: ...


@dataclass(slots=True)
class ExtensionCatalogService:
    adapters: list[ExtensionAdapter]
    _adapter_map: dict[tuple[ExtensionKind, str], ExtensionAdapter] = field(
        init=False,
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        for adapter in self.adapters:
            self._adapter_map[(adapter.kind, adapter.provider)] = adapter

    def get_adapter(
        self, kind: ExtensionKind, provider: str | None = None
    ) -> ExtensionAdapter | None:
        if provider:
            return self._adapter_map.get((kind, provider))
        for (adapter_kind, _), adapter in self._adapter_map.items():
            if adapter_kind == kind:
                return adapter
        return None

    async def search(
        self,
        kind: ExtensionKind,
        query: str,
        provider: str = "",
        limit: int | None = None,
    ) -> list[InstallCandidate]:
        adapter = self.get_adapter(kind, provider or None)
        if adapter is None:
            return []
        candidates = await adapter.search(query)
        if limit is None:
            return candidates
        return candidates[:limit]


@dataclass(slots=True)
class ExtensionInstallOrchestrator:
    policy_engine: ExtensionPolicyEngine
    pending_service: PendingOperationService
    adapters: list[ExtensionAdapter] = field(default_factory=list)
    catalog_service: ExtensionCatalogService | None = None
    search_result_limit: int = 6
    _target_locks: defaultdict[str, asyncio.Lock] = field(
        init=False,
        default_factory=lambda: defaultdict(asyncio.Lock),
    )
    _conversation_locks: defaultdict[str, asyncio.Lock] = field(
        init=False,
        default_factory=lambda: defaultdict(asyncio.Lock),
    )

    def __post_init__(self) -> None:
        if self.catalog_service is None:
            self.catalog_service = ExtensionCatalogService(self.adapters)
        elif self.adapters and not self.catalog_service.adapters:
            self.catalog_service = ExtensionCatalogService(self.adapters)

    def _get_adapter(
        self, kind: ExtensionKind, provider: str | None = None
    ) -> ExtensionAdapter | None:
        if self.catalog_service is None:
            return None
        return self.catalog_service.get_adapter(kind, provider)

    def _resolve_search_limit(self, limit: int | None = None) -> int:
        if limit is not None:
            return max(1, limit)
        return max(1, self.search_result_limit)

    async def search(
        self,
        kind: ExtensionKind,
        query: str,
        provider: str = "",
        limit: int | None = None,
    ) -> list[InstallCandidate]:
        if self.catalog_service is None:
            return []
        return await self.catalog_service.search(
            kind,
            query,
            provider=provider,
            limit=self._resolve_search_limit(limit),
        )

    async def _resolve_candidate(self, request: InstallRequest) -> InstallCandidate:
        adapter = self._get_adapter(request.kind, request.provider or None)
        if adapter is None:
            raise ValueError(
                f"no adapter available for kind={request.kind.value}, provider={request.provider}"
            )

        candidates = await adapter.search(request.target)
        for candidate in candidates:
            if (
                candidate.identifier == request.target
                or candidate.name == request.target
            ):
                return candidate

        return InstallCandidate(
            kind=request.kind,
            provider=adapter.provider,
            identifier=request.target,
            name=request.target.rsplit("/", maxsplit=1)[-1] or request.target,
            source="direct",
            install_payload={"target": request.target},
        )

    @staticmethod
    def _candidate_to_payload(candidate: InstallCandidate) -> dict[str, Any]:
        return {
            "kind": candidate.kind.value,
            "provider": candidate.provider,
            "identifier": candidate.identifier,
            "name": candidate.name,
            "description": candidate.description,
            "version": candidate.version,
            "source": candidate.source,
            "install_payload": candidate.install_payload,
        }

    @staticmethod
    def _candidate_from_payload(payload: dict[str, Any]) -> InstallCandidate:
        return InstallCandidate(
            kind=ExtensionKind(str(payload["kind"])),
            provider=str(payload["provider"]),
            identifier=str(payload["identifier"]),
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            version=str(payload.get("version", "")),
            source=str(payload.get("source", "")),
            install_payload=dict(payload.get("install_payload", {})),
        )

    async def _execute_install(self, candidate: InstallCandidate) -> dict[str, Any]:
        adapter = self._get_adapter(candidate.kind, candidate.provider)
        if adapter is None:
            raise ValueError(
                f"no adapter available for kind={candidate.kind.value}, provider={candidate.provider}"
            )
        return await adapter.install(candidate)

    async def _run_with_target_lock(
        self, target_key: str, install_callable: Callable[[], Awaitable[InstallResult]]
    ) -> InstallResult:
        lock = self._target_locks[target_key]
        async with lock:
            return await install_callable()

    async def _run_with_conversation_lock(
        self,
        conversation_key: str,
        operation_callable: Callable[[], Awaitable[InstallResult]],
    ) -> InstallResult:
        lock = self._conversation_locks[conversation_key]
        async with lock:
            return await operation_callable()

    @staticmethod
    def _conversation_key(request: InstallRequest) -> str:
        conversation_id = request.conversation_id.strip()
        if conversation_id:
            return conversation_id
        requester_id = request.requester_id.strip() or "anonymous"
        return f"manual:{request.kind.value}:{requester_id}"

    async def install(self, request: InstallRequest) -> InstallResult:
        candidate = await self._resolve_candidate(request)
        metadata = dict(candidate.install_payload.get("metadata", {}))
        metadata.update(request.metadata)
        candidate.install_payload["metadata"] = metadata
        decision = self.policy_engine.evaluate(request, candidate)
        conversation_key = self._conversation_key(request)
        target_key = (
            f"{candidate.kind.value}:{candidate.provider}:{candidate.identifier}"
        )

        if decision.action == PolicyAction.DENY:
            return InstallResult(
                status=InstallResultStatus.DENIED,
                message=f"install denied: {decision.reason}",
            )

        if decision.action == PolicyAction.REQUIRE_CONFIRMATION:

            async def _create_or_get_pending() -> InstallResult:
                operation = await self.pending_service.get_active_by_conversation(
                    conversation_key
                )
                if operation is not None:
                    if (
                        operation.kind == request.kind.value
                        and operation.provider == candidate.provider
                        and operation.target == candidate.identifier
                    ):
                        return InstallResult(
                            status=InstallResultStatus.PENDING,
                            message="existing pending operation",
                            operation_id=operation.operation_id,
                        )
                    return InstallResult(
                        status=InstallResultStatus.FAILED,
                        message=(
                            "a pending install already exists for this conversation; "
                            "confirm or reject it before starting another install"
                        ),
                        operation_id=operation.operation_id,
                    )

                pending = await self.pending_service.create(
                    conversation_id=conversation_key,
                    requester_id=request.requester_id,
                    requester_role=request.requester_role,
                    kind=request.kind,
                    provider=candidate.provider,
                    target=candidate.identifier,
                    payload={
                        "request": {
                            "kind": request.kind.value,
                            "target": request.target,
                            "provider": request.provider,
                        },
                        "candidate": self._candidate_to_payload(candidate),
                    },
                    reason=decision.reason,
                    decision=decision.action.value,
                )
                return InstallResult(
                    status=InstallResultStatus.PENDING,
                    message="confirmation required",
                    operation_id=pending.operation_id,
                )

            return await self._run_with_conversation_lock(
                conversation_key, _create_or_get_pending
            )

        async def _do_install() -> InstallResult:
            try:
                result = await self._execute_install(candidate)
                return InstallResult(
                    status=InstallResultStatus.SUCCESS,
                    message="install completed",
                    data=result,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "extension direct install failed: kind=%s provider=%s target=%s err=%s",
                    candidate.kind.value,
                    candidate.provider,
                    candidate.identifier,
                    exc,
                )
                return InstallResult(
                    status=InstallResultStatus.FAILED,
                    message=f"install failed: {exc}",
                )

        return await self._run_with_target_lock(target_key, _do_install)

    async def _execute_pending_operation(
        self, operation: PendingOperation
    ) -> InstallResult:
        payload = operation.payload or {}
        candidate_payload = payload.get("candidate", {})
        try:
            candidate = self._candidate_from_payload(candidate_payload)
        except Exception as exc:  # noqa: BLE001
            await self.pending_service.db.update_pending_operation(
                operation.operation_id,
                status="failed",
                error=f"invalid pending payload: {exc}",
            )
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message=f"invalid pending payload: {exc}",
                operation_id=operation.operation_id,
            )
        target_key = (
            f"{candidate.kind.value}:{candidate.provider}:{candidate.identifier}"
        )

        async def _do_install() -> InstallResult:
            await self.pending_service.db.update_pending_operation(
                operation.operation_id,
                status="running",
            )
            try:
                result = await self._execute_install(candidate)
                await self.pending_service.db.update_pending_operation(
                    operation.operation_id,
                    status="success",
                )
                return InstallResult(
                    status=InstallResultStatus.SUCCESS,
                    message="install completed",
                    operation_id=operation.operation_id,
                    data=result,
                )
            except Exception as exc:  # noqa: BLE001
                await self.pending_service.db.update_pending_operation(
                    operation.operation_id,
                    status="failed",
                    error=str(exc),
                )
                return InstallResult(
                    status=InstallResultStatus.FAILED,
                    message=f"install failed: {exc}",
                    operation_id=operation.operation_id,
                )

        return await self._run_with_target_lock(target_key, _do_install)

    async def confirm(
        self,
        *,
        operation_id_or_token: str,
        actor_id: str,
        actor_role: str,
    ) -> InstallResult:
        operation = await self.pending_service.get_by_operation_id_or_token(
            operation_id_or_token
        )
        if operation is None:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="pending operation not found",
            )
        if actor_role not in set(self.policy_engine.config.allowed_roles or []):
            return InstallResult(
                status=InstallResultStatus.DENIED,
                message="actor role is not allowed",
            )
        started = await self.pending_service.start(
            operation_id_or_token,
            confirmed_by=actor_id,
        )
        if started is None:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="operation cannot be confirmed",
                operation_id=operation.operation_id,
            )
        return await self._execute_pending_operation(started)

    async def confirm_for_conversation(
        self,
        *,
        conversation_id: str,
        actor_id: str,
        actor_role: str,
    ) -> InstallResult:
        operation = await self.pending_service.get_active_by_conversation(
            conversation_id
        )
        if operation is None:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="pending operation not found for conversation",
            )
        return await self.confirm(
            operation_id_or_token=operation.operation_id,
            actor_id=actor_id,
            actor_role=actor_role,
        )

    async def deny(
        self,
        *,
        operation_id_or_token: str,
        actor_id: str | None = None,
        actor_role: str,
        reason: str = "rejected by user",
    ) -> InstallResult:
        if actor_role not in set(self.policy_engine.config.allowed_roles or []):
            return InstallResult(
                status=InstallResultStatus.DENIED,
                message="actor role is not allowed",
            )
        operation = await self.pending_service.reject(
            operation_id_or_token,
            reason=reason,
        )
        if operation is None:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="operation cannot be rejected",
            )
        return InstallResult(
            status=InstallResultStatus.DENIED,
            message="operation rejected",
            operation_id=operation.operation_id,
        )

    async def deny_for_conversation(
        self,
        *,
        conversation_id: str,
        actor_id: str,
        actor_role: str,
        reason: str = "rejected by user",
    ) -> InstallResult:
        operation = await self.pending_service.get_active_by_conversation(
            conversation_id
        )
        if operation is None:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="pending operation not found for conversation",
            )
        return await self.deny(
            operation_id_or_token=operation.operation_id,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
        )

    async def pending(
        self, *, kind: ExtensionKind | None = None
    ) -> list[PendingOperation]:
        return await self.pending_service.list_pending(kind=kind)
