from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from astrbot.core.skills.neo_skill_sync import NeoSkillSyncManager


class _FakeSkills:
    async def list_releases(self, **kwargs):
        _ = kwargs
        return {
            "items": [
                {
                    "id": "sr-1",
                    "skill_key": "etl/loader@v1",
                    "candidate_id": "sc-1",
                    "stage": "stable",
                }
            ],
            "total": 1,
        }

    async def get_candidate(self, candidate_id: str):
        assert candidate_id == "sc-1"
        return {
            "id": "sc-1",
            "payload_ref": "blob:blob-1",
        }

    async def get_payload(self, payload_ref: str):
        assert payload_ref == "blob:blob-1"
        return {
            "payload_ref": payload_ref,
            "kind": "astrbot_skill_v1",
            "payload": {
                "skill_markdown": "---\ndescription: test\n---\n# title\ncontent",
            },
        }


class _FakeClient:
    def __init__(self):
        self.skills = _FakeSkills()


def test_sync_release_writes_skill_and_map(monkeypatch, tmp_path: Path):
    calls = {"active": [], "sandbox_sync": 0}

    def _fake_set_skill_active(self, name, active):
        calls["active"].append((name, active))

    async def _fake_sync_sandboxes():
        calls["sandbox_sync"] += 1

    monkeypatch.setattr(
        "astrbot.core.skills.neo_skill_sync.SkillManager.set_skill_active",
        _fake_set_skill_active,
    )
    monkeypatch.setattr(
        "astrbot.core.skills.neo_skill_sync.sync_skills_to_active_sandboxes",
        _fake_sync_sandboxes,
    )

    skills_root = tmp_path / "skills"
    map_path = skills_root / "neo_skill_map.json"
    mgr = NeoSkillSyncManager(skills_root=str(skills_root), map_path=str(map_path))

    result = asyncio.run(
        mgr.sync_release(_FakeClient(), release_id="sr-1", require_stable=True)
    )

    assert result.skill_key == "etl/loader@v1"
    assert result.release_id == "sr-1"
    assert result.local_skill_name.startswith("neo_")
    assert calls["active"] == [(result.local_skill_name, True)]
    assert calls["sandbox_sync"] == 1

    skill_md = skills_root / result.local_skill_name / "SKILL.md"
    assert skill_md.exists()
    assert "description: test" in skill_md.read_text(encoding="utf-8")

    assert map_path.exists()
    map_text = map_path.read_text(encoding="utf-8")
    assert "etl/loader@v1" in map_text
    assert result.local_skill_name in map_text


def test_sync_release_rejects_non_stable(monkeypatch, tmp_path: Path):
    class _CanarySkills(_FakeSkills):
        async def list_releases(self, **kwargs):
            _ = kwargs
            return {
                "items": [
                    {
                        "id": "sr-1",
                        "skill_key": "etl",
                        "candidate_id": "sc-1",
                        "stage": "canary",
                    }
                ],
                "total": 1,
            }

    class _CanaryClient:
        def __init__(self):
            self.skills = _CanarySkills()

    async def _fake_sync_sandboxes():
        return

    monkeypatch.setattr(
        "astrbot.core.skills.neo_skill_sync.sync_skills_to_active_sandboxes",
        _fake_sync_sandboxes,
    )
    monkeypatch.setattr(
        "astrbot.core.skills.neo_skill_sync.SkillManager.set_skill_active",
        lambda self, name, active: None,
    )

    mgr = NeoSkillSyncManager(
        skills_root=str(tmp_path / "skills"),
        map_path=str(tmp_path / "skills" / "neo_skill_map.json"),
    )
    with pytest.raises(ValueError, match="Only stable releases"):
        asyncio.run(
            mgr.sync_release(_CanaryClient(), release_id="sr-1", require_stable=True)
        )
