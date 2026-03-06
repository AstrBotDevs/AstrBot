"""
Extension Hub 安装编排器模块

本模块实现了插件/技能/MCP 扩展的统一安装管理，核心功能包括:

1. **安装流程控制**: 搜索、解析、安装扩展的完整生命周期
2. **策略执行**: 基于角色和配置的安装权限控制
3. **确认工作流**: 支持需要用户确认的安装请求（会话级别绑定）
4. **并发安全**: 通过目标锁和会话锁保证安装操作的原子性

主要组件:
- ExtensionAdapter: 适配器协议，定义搜索和安装接口
- ExtensionCatalogService: 扩展目录服务，聚合多个适配器
- ExtensionInstallOrchestrator: 核心编排器，协调安装流程

工作流程:
1. 用户/AI 发起安装请求 (install)
2. 策略引擎评估是否需要确认 (REQUIRE_CONFIRMATION / ALLOW / DENY)
3. 若需确认，创建 PendingOperation 并绑定到会话
4. 用户通过自然语言或命令确认/拒绝
5. 执行实际安装或清理挂起记录

相关提交:
- 350fdf13: Extension Hub v1 初始实现
- e64503cf: 会话级别确认工作流
- f3f79deb: 可配置搜索结果限制
- ef0bc377: 增强 deny 工具和用户消息
"""
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
    """扩展适配器协议

    定义了扩展搜索和安装的标准接口。每种扩展类型（plugin/skill/mcp）
    都需要实现此协议。参见 adapters.py 中的具体实现。

    Attributes:
        provider: 适配器提供者标识，如 "astrbot"、"mcp_todo"
        kind: 扩展类型 (PLUGIN / SKILL / MCP)
    """

    provider: str
    kind: ExtensionKind

    async def search(self, query: str) -> list[InstallCandidate]: ...
    async def install(self, candidate: InstallCandidate) -> dict[str, Any]: ...


@dataclass(slots=True)
class ExtensionCatalogService:
    """扩展目录服务

    聚合多个适配器，提供统一的搜索入口。支持按类型和提供者
    查找对应的适配器，并对搜索结果进行数量限制。
    """
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
    """扩展安装编排器

    核心职责:
    1. 协调扩展的搜索和安装流程
    2. 执行策略引擎的权限判定
    3. 管理待确认的安装操作 (PendingOperation)
    4. 处理用户确认/拒绝请求

    并发控制:
    - _target_locks: 按安装目标加锁，防止同一扩展被并发安装
    - _conversation_locks: 按会话加锁，保证同一会话只有一个待处理安装

    Attributes:
        policy_engine: 策略引擎，评估安装权限
        pending_service: 待处理操作服务，管理挂起状态
        adapters: 已注册的扩展适配器列表
        search_result_limit: 默认搜索结果数量限制 (默认 6)
    """
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

    def _is_allowed_role(self, actor_role: str) -> bool:
        """检查角色是否在允许列表中"""
        return actor_role in set(self.policy_engine.config.allowed_roles or [])

    def _can_deny_operation(
        self,
        operation: PendingOperation,
        *,
        actor_id: str | None,
        actor_role: str,
    ) -> bool:
        """检查操作者是否有权拒绝某个挂起操作

        权限规则:
        1. 允许列表中的角色可以直接拒绝
        2. 操作的原始请求者可以拒绝自己的请求

        该设计允许普通用户取消自己发起的安装请求，而不仅限于管理员。
        """
        if self._is_allowed_role(actor_role):
            return True
        if actor_id and operation.requester_id == actor_id:
            return True
        return False

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
        """处理安装请求，执行策略判定和安装流程

        Args:
            request: 安装请求，包含目标、类型、发起者信息等

        Returns:
            InstallResult: 安装结果，状态可能是:
                - SUCCESS: 安装成功
                - PENDING: 需要确认，等待用户响应
                - DENIED: 被策略拒绝
                - FAILED: 安装失败
        """
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
                            data={
                                "candidate_name": candidate.name,
                                "candidate_description": candidate.description,
                                "candidate_identifier": candidate.identifier,
                                "candidate_kind": candidate.kind.value,
                                "candidate_provider": candidate.provider,
                            },
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
                    data={
                        "candidate_name": candidate.name,
                        "candidate_description": candidate.description,
                        "candidate_identifier": candidate.identifier,
                        "candidate_kind": candidate.kind.value,
                        "candidate_provider": candidate.provider,
                    },
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
        """确认一个挂起的安装操作

        只有 allowed_roles 中的角色才能确认安装。
        确认后立即执行实际安装。

        Args:
            operation_id_or_token: 操作 ID 或确认令牌
            actor_id: 确认者 ID
            actor_role: 确认者角色

        Returns:
            InstallResult: 安装结果
        """
        operation = await self.pending_service.get_by_operation_id_or_token(
            operation_id_or_token
        )
        if operation is None:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="pending operation not found",
            )
        if not self._is_allowed_role(actor_role):
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
        """确认指定会话中的挂起安装

        通过会话 ID 查找挂起操作并确认。用于自然语言确认流程。

        Args:
            conversation_id: 会话 ID
            actor_id: 确认者 ID
            actor_role: 确认者角色
        """
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
        """拒绝一个挂起的安装操作

        权限规则:
        - allowed_roles 中的角色可以拒绝任何操作
        - 操作的原始请求者可以拒绝自己的请求

        Args:
            operation_id_or_token: 操作 ID 或令牌
            actor_id: 拒绝者 ID (可选)
            actor_role: 拒绝者角色
            reason: 拒绝原因
        """
        operation = await self.pending_service.get_by_operation_id_or_token(
            operation_id_or_token
        )
        if operation is None:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="operation cannot be rejected",
            )
        if not self._can_deny_operation(
            operation, actor_id=actor_id, actor_role=actor_role
        ):
            return InstallResult(
                status=InstallResultStatus.DENIED,
                message="actor is not allowed to reject this operation",
            )
        operation = await self.pending_service.reject(
            operation.operation_id,
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
            data={"count": 1},
        )

    async def deny_for_conversation(
        self,
        *,
        conversation_id: str,
        actor_id: str,
        actor_role: str,
        reason: str = "rejected by user",
    ) -> InstallResult:
        """拒绝指定会话中的所有挂起安装

        用于用户在会话中发送"取消"或"不要安装"等拒绝意图时调用。
        会拒绝该会话中所有有权拒绝的挂起操作。

        Args:
            conversation_id: 会话 ID
            actor_id: 拒绝者 ID
            actor_role: 拒绝者角色
            reason: 拒绝原因
        """
        operations = await self.pending_service.list_pending_by_conversation(
            conversation_id
        )
        if not operations:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="pending operation not found for conversation",
            )
        authorized_operations = [
            operation
            for operation in operations
            if self._can_deny_operation(
                operation, actor_id=actor_id, actor_role=actor_role
            )
        ]
        if not authorized_operations:
            return InstallResult(
                status=InstallResultStatus.DENIED,
                message="actor is not allowed to reject operations in this conversation",
            )
        rejected_count = 0
        last_operation_id: str | None = None
        for operation in authorized_operations:
            rejected = await self.pending_service.reject(
                operation.operation_id,
                reason=reason,
            )
            if rejected is not None:
                rejected_count += 1
                last_operation_id = rejected.operation_id
        if rejected_count == 0:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="operation cannot be rejected",
            )
        return InstallResult(
            status=InstallResultStatus.DENIED,
            message=f"rejected {rejected_count} operation(s)",
            operation_id=last_operation_id,
            data={"count": rejected_count},
        )

    async def deny_all(
        self,
        *,
        actor_id: str,
        actor_role: str,
        kind: ExtensionKind | None = None,
        reason: str = "rejected by agent",
    ) -> InstallResult:
        """拒绝所有挂起的安装操作

        用于管理员或 AI 清理所有待确认的安装请求。
        可按扩展类型过滤。

        Args:
            actor_id: 拒绝者 ID
            actor_role: 拒绝者角色
            kind: 可选的扩展类型过滤
            reason: 拒绝原因
        """
        operations = await self.pending_service.list_pending(kind=kind)
        authorized_operations = [
            operation
            for operation in operations
            if self._can_deny_operation(
                operation, actor_id=actor_id, actor_role=actor_role
            )
        ]
        if not authorized_operations:
            return InstallResult(
                status=InstallResultStatus.DENIED,
                message="actor is not allowed to reject pending operations",
            )
        rejected_count = 0
        for operation in authorized_operations:
            rejected = await self.pending_service.reject(
                operation.operation_id,
                reason=reason,
            )
            if rejected is not None:
                rejected_count += 1
        if rejected_count == 0:
            return InstallResult(
                status=InstallResultStatus.FAILED,
                message="no pending operations were rejected",
            )
        return InstallResult(
            status=InstallResultStatus.DENIED,
            message=f"rejected {rejected_count} operation(s)",
            data={"count": rejected_count},
        )

    async def pending(
        self, *, kind: ExtensionKind | None = None
    ) -> list[PendingOperation]:
        return await self.pending_service.list_pending(kind=kind)
