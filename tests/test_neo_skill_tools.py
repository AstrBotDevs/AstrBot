from __future__ import annotations

import asyncio
from types import SimpleNamespace

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet
from astrbot.core.tools.computer_tools.shipyard_neo.neo_skills import (
    CreateSkillPayloadTool,
    PromoteSkillCandidateTool,
)


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
        "astrbot.core.tools.computer_tools.shipyard_neo.neo_skills.get_booter",
        _fake_get_booter,
    )
    monkeypatch.setattr(
        "astrbot.core.tools.computer_tools.shipyard_neo.neo_skills.NeoSkillSyncManager.sync_release",
        _fake_sync_release,
    )

    event = SimpleNamespace(
        role="admin",
        unified_msg_origin="session-1",
        get_sender_id=lambda: "admin-user",
    )
    astr_ctx = SimpleNamespace(
        context=SimpleNamespace(
            get_config=lambda umo: {  # noqa: ARG005
                "provider_settings": {
                    "computer_use_require_admin": True,
                }
            }
        ),
        event=event,
    )
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


def test_create_skill_payload_tool_schema_allows_non_empty_payload_objects():
    tool = CreateSkillPayloadTool()
    payload_schema = tool.parameters["properties"]["payload"]
    assert "anyOf" in payload_schema

    object_schema = next(
        s for s in payload_schema["anyOf"] if isinstance(s, dict) and s.get("type") == "object"
    )
    assert object_schema.get("additionalProperties") is True
    assert "skill_markdown" in object_schema.get("properties", {})

    array_schema = next(
        s for s in payload_schema["anyOf"] if isinstance(s, dict) and s.get("type") == "array"
    )
    assert array_schema.get("items", {}).get("type") == "object"
    assert array_schema.get("items", {}).get("additionalProperties") is True


def test_create_skill_payload_tool_google_schema_keeps_object_array_items():
    tool = CreateSkillPayloadTool()
    schema = ToolSet([tool]).google_schema()
    payload_schema = schema["function_declarations"][0]["parameters"]["properties"]["payload"]

    array_schema = next(
        s for s in payload_schema["anyOf"] if isinstance(s, dict) and s.get("type") == "array"
    )
    assert array_schema["items"]["type"] == "object"
