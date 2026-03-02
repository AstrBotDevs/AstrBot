from __future__ import annotations

import asyncio
from types import SimpleNamespace

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.computer.tools.neo_skills import PromoteSkillCandidateTool


class _FakeSkills:
    def __init__(self):
        self.rollback_called_with = None

    async def promote_candidate(self, candidate_id: str, stage: str = "canary"):
        assert candidate_id == "cand-1"
        assert stage == "stable"
        return {
            "id": "sr-1",
            "skill_key": "k1",
            "candidate_id": candidate_id,
            "stage": stage,
        }

    async def rollback_release(self, release_id: str):
        self.rollback_called_with = release_id
        return {"id": "rb-1", "rollback_of": release_id}


class _FakeClient:
    def __init__(self):
        self.skills = _FakeSkills()


class _FakeBooter:
    def __init__(self):
        self.bay_client = _FakeClient()
        self.sandbox = object()


def test_promote_stable_sync_failure_auto_rolls_back(monkeypatch):
    async def _fake_get_booter(_ctx, _session_id):
        return _FakeBooter()

    async def _fake_sync_release(self, client, **kwargs):
        _ = self, client, kwargs
        raise ValueError("sync failed")

    monkeypatch.setattr(
        "astrbot.core.computer.tools.neo_skills.get_booter",
        _fake_get_booter,
    )
    monkeypatch.setattr(
        "astrbot.core.computer.tools.neo_skills.NeoSkillSyncManager.sync_release",
        _fake_sync_release,
    )

    event = SimpleNamespace(role="admin", unified_msg_origin="session-1")
    astr_ctx = SimpleNamespace(context=SimpleNamespace(), event=event)
    run_ctx = ContextWrapper(context=astr_ctx)

    tool = PromoteSkillCandidateTool()
    result = asyncio.run(
        tool.call(
            run_ctx,
            candidate_id="cand-1",
            stage="stable",
            sync_to_local=True,
        )
    )

    assert isinstance(result, str)
    assert "auto rollback succeeded" in result
    assert "sync failed" in result
