from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import select

from astrbot.core.db.po import PendingOperation
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.extensions.adapters import (
    McpTodoAdapter,
    PluginAdapter,
    _is_git_repository_locator,
)
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


class _SlowFakeAdapter(_FakeAdapter):
    async def install(self, candidate: InstallCandidate) -> dict:
        self.install_calls += 1
        await asyncio.sleep(0.05)
        return {"name": candidate.name, "identifier": candidate.identifier}


class _AsyncBarrier:
    def __init__(self, parties: int) -> None:
        self.parties = parties
        self.waiting = 0
        self._ready = asyncio.Event()

    async def wait(self) -> None:
        self.waiting += 1
        if self.waiting >= self.parties:
            self._ready.set()
        await self._ready.wait()


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
async def test_policy_allowlist_matches_plugin_author_without_identifier() -> None:
    cfg = _build_policy_config()
    cfg["provider_settings"]["extension_install"]["allowlist"] = [
        {
            "kind": "plugin",
            "author": "NickMo",
        }
    ]
    req = InstallRequest(
        kind=ExtensionKind.PLUGIN,
        target="https://github.com/example/demo",
        provider="fake",
        requester_id="u1",
        requester_role="admin",
    )
    candidate = InstallCandidate(
        kind=ExtensionKind.PLUGIN,
        provider="git",
        identifier="https://github.com/example/demo",
        name="demo",
        description="d",
        source="plugin_market_cache",
        install_payload={"author": "NickMo"},
    )

    decision = ExtensionPolicyEngine(cfg).evaluate(req, candidate)
    assert decision.action == PolicyAction.ALLOW_DIRECT


@pytest.mark.asyncio
async def test_policy_blocklist_matches_plugin_author_without_identifier() -> None:
    cfg = _build_policy_config()
    cfg["provider_settings"]["extension_install"]["blocklist"] = [
        {
            "kind": "plugin",
            "author": "NickMo",
        }
    ]
    req = InstallRequest(
        kind=ExtensionKind.PLUGIN,
        target="https://github.com/example/demo",
        provider="fake",
        requester_id="u1",
        requester_role="admin",
    )
    candidate = InstallCandidate(
        kind=ExtensionKind.PLUGIN,
        provider="git",
        identifier="https://github.com/example/demo",
        name="demo",
        description="d",
        source="plugin_market_cache",
        install_payload={"author": "NickMo"},
    )

    decision = ExtensionPolicyEngine(cfg).evaluate(req, candidate)
    assert decision.action == PolicyAction.DENY


@pytest.mark.asyncio
async def test_policy_ignores_empty_plugin_author_rule() -> None:
    cfg = _build_policy_config()
    cfg["provider_settings"]["extension_install"]["allowlist"] = [
        {
            "kind": "plugin",
            "author": "",
        }
    ]
    req = InstallRequest(
        kind=ExtensionKind.PLUGIN,
        target="https://github.com/example/demo",
        provider="fake",
        requester_id="u1",
        requester_role="admin",
    )
    candidate = InstallCandidate(
        kind=ExtensionKind.PLUGIN,
        provider="git",
        identifier="https://github.com/example/demo",
        name="demo",
        description="d",
        source="plugin_market_cache",
        install_payload={"author": "NickMo"},
    )

    decision = ExtensionPolicyEngine(cfg).evaluate(req, candidate)
    assert decision.action == PolicyAction.REQUIRE_CONFIRMATION


@pytest.mark.asyncio
async def test_policy_open_mode_allows_non_blocklisted_target_without_confirmation() -> None:
    cfg = _build_policy_config()
    cfg["provider_settings"]["extension_install"]["default_mode"] = "open"
    req = InstallRequest(
        kind=ExtensionKind.PLUGIN,
        target="https://github.com/example/demo",
        provider="fake",
        requester_id="u1",
        requester_role="admin",
    )
    candidate = InstallCandidate(
        kind=ExtensionKind.PLUGIN,
        provider="git",
        identifier="https://github.com/example/demo",
        name="demo",
        description="d",
        source="plugin_market_cache",
        install_payload={"author": "NickMo"},
    )

    decision = ExtensionPolicyEngine(cfg).evaluate(req, candidate)
    assert decision.action == PolicyAction.ALLOW_DIRECT


@pytest.mark.asyncio
async def test_policy_open_mode_ignores_allowlist_and_still_denies_blocklist() -> None:
    cfg = _build_policy_config()
    cfg["provider_settings"]["extension_install"]["default_mode"] = "open"
    cfg["provider_settings"]["extension_install"]["allowlist"] = [
        {
            "kind": "plugin",
            "author": "SomeoneElse",
        }
    ]
    cfg["provider_settings"]["extension_install"]["blocklist"] = [
        {
            "kind": "plugin",
            "author": "NickMo",
        }
    ]
    req = InstallRequest(
        kind=ExtensionKind.PLUGIN,
        target="https://github.com/example/demo",
        provider="fake",
        requester_id="u1",
        requester_role="admin",
    )
    candidate = InstallCandidate(
        kind=ExtensionKind.PLUGIN,
        provider="git",
        identifier="https://github.com/example/demo",
        name="demo",
        description="d",
        source="plugin_market_cache",
        install_payload={"author": "NickMo"},
    )

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
async def test_pending_operation_service_start_allows_only_one_winner_under_race(
    tmp_path: Path,
) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        barrier = _AsyncBarrier(2)

        class _RacePendingOperationService(PendingOperationService):
            async def get_by_operation_id_or_token(self, operation_id_or_token: str):
                snapshot = await self.get_by_id(operation_id_or_token)
                await barrier.wait()
                return snapshot

        store = _RacePendingOperationService(db, token_ttl_seconds=300)
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

        started_1, started_2 = await asyncio.gather(
            store.start(created.operation_id, confirmed_by="u1"),
            store.start(created.operation_id, confirmed_by="u2"),
        )

        assert sum(operation is not None for operation in (started_1, started_2)) == 1
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
async def test_get_by_operation_id_or_token_does_not_expire_running_operation(
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
        await db.update_pending_operation(
            created.operation_id,
            status="running",
            current_status="pending",
        )
        stale = PendingOperation.model_validate(created.model_dump())
        stale.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        class _StalePendingOperationService(PendingOperationService):
            async def get_by_id(self, operation_id: str):
                _ = operation_id
                return stale

        stale_store = _StalePendingOperationService(db, token_ttl_seconds=300)
        resolved = await stale_store.get_by_operation_id_or_token(created.operation_id)
        current = await db.get_pending_operation_by_operation_id(created.operation_id)

        assert resolved is None
        assert current is not None
        assert current.status == "running"
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
async def test_orchestrator_reject_clears_all_conversation_pending(
    tmp_path: Path,
) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        store = PendingOperationService(db, token_ttl_seconds=300)
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=store,
            adapters=[_FakeAdapter(identifier="https://github.com/example/demo")],
        )
        await store.create(
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo-1",
            payload={"x": 1},
            reason="need_confirm",
        )
        await store.create(
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo-2",
            payload={"x": 2},
            reason="need_confirm",
        )

        denied = await orchestrator.deny_for_conversation(
            conversation_id="conv-1",
            actor_id="u1",
            actor_role="admin",
        )

        assert denied.status == InstallResultStatus.DENIED
        assert denied.data["count"] == 2
        assert await store.get_active_by_conversation("conv-1") is None
        operations = await db.list_pending_operations()
        assert all(operation.status == "rejected" for operation in operations)
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_deny_all_rejects_pending_operations(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        store = PendingOperationService(db, token_ttl_seconds=300)
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=store,
            adapters=[_FakeAdapter(identifier="https://github.com/example/demo")],
        )
        await store.create(
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo-1",
            payload={"x": 1},
            reason="need_confirm",
        )
        await store.create(
            conversation_id="conv-2",
            requester_id="u2",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo-2",
            payload={"x": 2},
            reason="need_confirm",
        )

        denied = await orchestrator.deny_all(actor_id="u1", actor_role="admin")

        assert denied.status == InstallResultStatus.DENIED
        assert denied.data["count"] == 2
        operations = await db.list_pending_operations()
        assert all(operation.status == "rejected" for operation in operations)
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_deny_all_requires_allowed_role(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        store = PendingOperationService(db, token_ttl_seconds=300)
        orchestrator = ExtensionInstallOrchestrator(
            policy_engine=ExtensionPolicyEngine(_build_policy_config()),
            pending_service=store,
            adapters=[_FakeAdapter(identifier="https://github.com/example/demo")],
        )
        await store.create(
            conversation_id="conv-1",
            requester_id="u1",
            requester_role="admin",
            kind=ExtensionKind.PLUGIN,
            provider="fake",
            target="https://github.com/example/demo-1",
            payload={"x": 1},
            reason="need_confirm",
        )

        denied = await orchestrator.deny_all(actor_id="u2", actor_role="member")

        assert denied.status == InstallResultStatus.DENIED
        assert "not allowed" in denied.message
        operations = await db.list_pending_operations()
        assert operations[0].status == "pending"
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


@pytest.mark.asyncio
async def test_orchestrator_confirm_is_idempotent_under_concurrency(
    tmp_path: Path,
) -> None:
    db = SQLiteDatabase(str(tmp_path / "hub.db"))
    await db.initialize()
    try:
        target = "https://github.com/example/demo"
        adapter = _SlowFakeAdapter(identifier=target)
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

        result_1, result_2 = await asyncio.gather(
            orchestrator.confirm(
                operation_id_or_token=pending.operation_id,
                actor_id="u1",
                actor_role="admin",
            ),
            orchestrator.confirm(
                operation_id_or_token=pending.operation_id,
                actor_id="u1",
                actor_role="admin",
            ),
        )

        assert adapter.install_calls == 1
        assert {result_1.status, result_2.status} == {
            InstallResultStatus.SUCCESS,
            InstallResultStatus.FAILED,
        }
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


@pytest.mark.asyncio
async def test_plugin_adapter_search_filters_installed_plugins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_file = tmp_path / "plugins.json"
    cache_file.write_text(
        """
        {
          "data": {
            "installed_plugin": {
              "name": "installed_plugin",
              "desc": "already installed",
              "author": "alice",
              "repo": "https://github.com/example/installed-plugin"
            },
            "fresh_plugin": {
              "name": "fresh_plugin",
              "desc": "new candidate",
              "author": "bob",
              "repo": "https://github.com/example/fresh-plugin"
            }
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "astrbot.core.extensions.adapters.get_astrbot_data_path",
        lambda: str(tmp_path),
    )
    context = SimpleNamespace(
        get_all_stars=lambda: [
            SimpleNamespace(
                name="installed_plugin",
                display_name="Installed Plugin",
                desc="already installed",
                author="alice",
                repo="https://github.com/example/installed-plugin",
                version="1.0.0",
            )
        ]
    )
    adapter = PluginAdapter(context)

    results = await adapter.search("plugin")

    assert [candidate.name for candidate in results] == ["fresh_plugin"]
    assert all(candidate.source != "installed" for candidate in results)
