from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import select

from astrbot.core.db.po import PendingOperation
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.extensions.adapters import McpTodoAdapter, _is_git_repository_locator
from astrbot.core.extensions.model import (
    ExtensionKind,
    InstallCandidate,
    InstallRequest,
    InstallResultStatus,
    PolicyAction,
)
from astrbot.core.extensions.orchestrator import ExtensionInstallOrchestrator
from astrbot.core.extensions.pending_operation import PendingOperationService
from astrbot.core.extensions.policy import ExtensionPolicyEngine


class _FakeAdapter:
    provider = "fake"
    kind = ExtensionKind.PLUGIN

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        self.install_calls = 0

    async def search(self, query: str) -> list[InstallCandidate]:
        if query in self.identifier:
            return [
                InstallCandidate(
                    kind=self.kind,
                    provider=self.provider,
                    identifier=self.identifier,
                    name="demo-plugin",
                    description="demo",
                    source="fake",
                )
            ]
        return []

    async def install(self, candidate: InstallCandidate) -> dict:
        self.install_calls += 1
        return {"name": candidate.name, "identifier": candidate.identifier}


class _BulkFakeAdapter:
    provider = "fake"
    kind = ExtensionKind.PLUGIN

    async def search(self, query: str) -> list[InstallCandidate]:
        return [
            InstallCandidate(
                kind=self.kind,
                provider=self.provider,
                identifier=f"https://github.com/example/demo-{idx}",
                name=f"demo-plugin-{idx}",
                description=f"demo {idx}",
                source="fake",
            )
            for idx in range(10)
        ]

    async def install(self, candidate: InstallCandidate) -> dict:
        return {"name": candidate.name, "identifier": candidate.identifier}


def _build_policy_config() -> dict:
    return {
        "provider_settings": {
            "extension_install": {
                "default_mode": "secure",
                "allowlist": [],
                "blocklist": [],
                "confirmation_required_non_allowlist": True,
                "allowed_roles": ["admin", "owner"],
                "confirmation_token_ttl_seconds": 900,
            }
        }
    }


@pytest.mark.asyncio
async def test_policy_matrix() -> None:
    cfg = _build_policy_config()
    engine = ExtensionPolicyEngine(cfg)
    req = InstallRequest(
        kind=ExtensionKind.PLUGIN,
        target="https://github.com/example/demo",
        provider="fake",
        requester_id="u1",
        requester_role="admin",
    )
    candidate = InstallCandidate(
        kind=ExtensionKind.PLUGIN,
        provider="fake",
        identifier="https://github.com/example/demo",
        name="demo",
        description="d",
        source="fake",
    )

    decision = engine.evaluate(req, candidate)
    assert decision.action == PolicyAction.REQUIRE_CONFIRMATION

    cfg["provider_settings"]["extension_install"]["allowlist"] = [
        {
            "kind": "plugin",
            "provider": "fake",
            "identifier": "https://github.com/example/demo",
        }
    ]
    decision = ExtensionPolicyEngine(cfg).evaluate(req, candidate)
    assert decision.action == PolicyAction.ALLOW_DIRECT

    cfg["provider_settings"]["extension_install"]["blocklist"] = [
        {
            "kind": "plugin",
            "provider": "fake",
            "identifier": "https://github.com/example/demo",
        }
    ]
    decision = ExtensionPolicyEngine(cfg).evaluate(req, candidate)
    assert decision.action == PolicyAction.DENY


@pytest.mark.asyncio
async def test_pending_operation_service_lifecycle(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        store = PendingOperationService(db, token_ttl_seconds=300)
        created = await store.create(
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo",
            payload={"x": 1},
            reason="need_confirm",
        )
        assert created.status == "pending"
        assert created.token
        assert len(created.token) >= 20

        fetched = await store.get_by_token(created.token)
        assert fetched is not None
        assert fetched.operation_id == created.operation_id

        active = await store.get_active_by_conversation("conv-1")
        assert active is not None
        assert active.operation_id == created.operation_id

        confirmed = await store.start(created.operation_id, confirmed_by="u1")
        assert confirmed is not None
        assert confirmed.status == "running"

        second_confirm = await store.start(created.operation_id, confirmed_by="u1")
        assert second_confirm is None
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_pending_operation_service_reject_after_confirm_is_blocked(
    tmp_path: Path,
) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        store = PendingOperationService(db, token_ttl_seconds=300)
        created = await store.create(
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo",
            payload={"x": 1},
            reason="need_confirm",
        )
        confirmed = await store.start(created.operation_id, confirmed_by="u1")
        assert confirmed is not None
        rejected = await store.reject(created.operation_id)
        assert rejected is None
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_pending_operation_service_confirm_after_reject_is_blocked(
    tmp_path: Path,
) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        store = PendingOperationService(db, token_ttl_seconds=300)
        created = await store.create(
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo",
            payload={"x": 1},
            reason="need_confirm",
        )
        rejected = await store.reject(created.operation_id)
        assert rejected is not None
        confirmed = await store.start(created.operation_id, confirmed_by="u1")
        assert confirmed is None
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_pending_list_filters_expired_operations(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        store = PendingOperationService(db, token_ttl_seconds=300)
        created = await store.create(
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo",
            payload={"x": 1},
            reason="need_confirm",
        )
        assert created.status == "pending"
        async with db.get_db() as session:
            result = await session.execute(
                select(PendingOperation).where(
                    PendingOperation.operation_id == created.operation_id
                )
            )
            record = result.scalar_one()
            record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(record)
            await session.commit()

        operations = await store.list_pending()
        assert operations == []
        expired = await db.get_pending_operation_by_operation_id(created.operation_id)
        assert expired is not None
        assert expired.status == "expired"
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_pending_and_confirm_flow(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        target = "https://github.com/example/demo"
        adapter = _FakeAdapter(identifier=target)
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=PendingOperationService(db, token_ttl_seconds=300),
            adapters=[adapter],
        )
        request = InstallRequest(
            kind=ExtensionKind.PLUGIN,
            target=target,
            provider="fake",
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
        )
        result = await orchestrator.install(request)
        assert result.status == InstallResultStatus.PENDING
        assert result.operation_id
        assert adapter.install_calls == 0

        confirmed = await orchestrator.confirm_for_conversation(
            conversation_id="conv-1",
            actor_id="u1",
            actor_role="admin",
        )
        assert confirmed.status == InstallResultStatus.SUCCESS
        assert adapter.install_calls == 1
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_pending_dedup_by_target(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        target = "https://github.com/example/demo"
        adapter = _FakeAdapter(identifier=target)
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=PendingOperationService(db, token_ttl_seconds=300),
            adapters=[adapter],
        )
        request = InstallRequest(
            kind=ExtensionKind.PLUGIN,
            target=target,
            provider="fake",
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
        )
        result_1, result_2 = await asyncio.gather(
            orchestrator.install(request),
            orchestrator.install(request),
        )

        assert result_1.status == InstallResultStatus.PENDING
        assert result_2.status == InstallResultStatus.PENDING
        assert result_1.operation_id == result_2.operation_id
        assert adapter.install_calls == 0
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_blocks_second_pending_target_in_same_conversation(
    tmp_path: Path,
) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        first_target = "https://github.com/example/demo-1"
        second_target = "https://github.com/example/demo-2"
        adapter = _FakeAdapter(identifier=first_target)
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=PendingOperationService(db, token_ttl_seconds=300),
            adapters=[adapter],
        )
        first = await orchestrator.install(
            InstallRequest(
                kind=ExtensionKind.PLUGIN,
                target=first_target,
                provider="fake",
                conversation_id="conv-1",
                requester_id="u1",
                requester_role="admin",
            )
        )
        second = await orchestrator.install(
            InstallRequest(
                kind=ExtensionKind.PLUGIN,
                target=second_target,
                provider="fake",
                conversation_id="conv-1",
                requester_id="u1",
                requester_role="admin",
            )
        )

        assert first.status == InstallResultStatus.PENDING
        assert second.status == InstallResultStatus.FAILED
        assert "pending" in second.message.lower()
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_reject_clears_conversation_pending(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        target = "https://github.com/example/demo"
        adapter = _FakeAdapter(identifier=target)
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=PendingOperationService(db, token_ttl_seconds=300),
            adapters=[adapter],
        )
        pending = await orchestrator.install(
            InstallRequest(
                kind=ExtensionKind.PLUGIN,
                target=target,
                provider="fake",
                conversation_id="conv-1",
                requester_id="u1",
                requester_role="admin",
            )
        )
        denied = await orchestrator.deny_for_conversation(
            conversation_id="conv-1",
            actor_id="u1",
            actor_role="admin",
        )
        assert pending.status == InstallResultStatus.PENDING
        assert denied.status == InstallResultStatus.DENIED
        assert (
            await orchestrator.pending_service.get_active_by_conversation("conv-1")
            is None
        )
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_confirm_for_conversation_rejects_unauthorized_actor(
    tmp_path: Path,
) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        target = "https://github.com/example/demo"
        adapter = _FakeAdapter(identifier=target)
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=PendingOperationService(db, token_ttl_seconds=300),
            adapters=[adapter],
        )
        await orchestrator.install(
            InstallRequest(
                kind=ExtensionKind.PLUGIN,
                target=target,
                provider="fake",
                conversation_id="conv-1",
                requester_id="u1",
                requester_role="admin",
            )
        )
        denied = await orchestrator.confirm_for_conversation(
            conversation_id="conv-1",
            actor_id="u2",
            actor_role="member",
        )
        assert denied.status == InstallResultStatus.DENIED
        assert adapter.install_calls == 0
    finally:
        await db.engine.dispose()


def test_plugin_locator_supports_ssh() -> None:
    assert _is_git_repository_locator("https://github.com/example/repo.git")
    assert _is_git_repository_locator("git@github.com:example/repo.git")
    assert _is_git_repository_locator("ssh://git@github.com/example/repo.git")
    assert not _is_git_repository_locator("not-a-repo")


@pytest.mark.asyncio
async def test_mcp_install_todo_status(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        cfg = _build_policy_config()
        cfg["provider_settings"]["extension_install"]["allowlist"] = [
            {"kind": "mcp", "provider": "todo", "identifier": "demo-mcp"}
        ]
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(cfg),
            pending_service=PendingOperationService(db, token_ttl_seconds=300),
            adapters=[McpTodoAdapter()],
        )
        result = await orchestrator.install(
            InstallRequest(
                kind=ExtensionKind.MCP,
                target="demo-mcp",
                provider="todo",
                requester_id="u1",
                requester_role="admin",
            )
        )
        assert result.status == InstallResultStatus.FAILED
        assert "TODO" in result.message
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_search_uses_default_limit(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=PendingOperationService(db, token_ttl_seconds=300),
            adapters=[_BulkFakeAdapter()],
        )
        results = await orchestrator.search(ExtensionKind.PLUGIN, "demo")
        assert len(results) == 6
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_search_respects_explicit_limit(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=PendingOperationService(db, token_ttl_seconds=300),
            adapters=[_BulkFakeAdapter()],
        )
        results = await orchestrator.search(ExtensionKind.PLUGIN, "demo", limit=3)
        assert len(results) == 3
    finally:
        await db.engine.dispose()
