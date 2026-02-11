import json
from dataclasses import dataclass, field
from typing import Any

from astrbot.api import FunctionTool
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.skills.neo_skill_sync import NeoSkillSyncManager

from ..computer_client import get_booter


def _to_jsonable(model_like: Any) -> Any:
    if isinstance(model_like, dict):
        return model_like
    if isinstance(model_like, list):
        return [_to_jsonable(i) for i in model_like]
    if hasattr(model_like, "model_dump"):
        return _to_jsonable(model_like.model_dump())
    return model_like


def _to_json_text(data: Any) -> str:
    return json.dumps(_to_jsonable(data), ensure_ascii=False, default=str)


def _ensure_admin(context: ContextWrapper[AstrAgentContext]) -> str | None:
    if context.context.event.role != "admin":
        return (
            "error: Permission denied. Skill lifecycle tools are only allowed for admin users."
        )
    return None


async def _get_neo_context(context: ContextWrapper[AstrAgentContext]) -> tuple[Any, Any]:
    booter = await get_booter(
        context.context.context,
        context.context.event.unified_msg_origin,
    )
    client = getattr(booter, "bay_client", None)
    sandbox = getattr(booter, "sandbox", None)
    if client is None or sandbox is None:
        raise RuntimeError(
            "Current sandbox booter does not support Neo skill lifecycle APIs. "
            "Please switch to shipyard_neo."
        )
    return client, sandbox


@dataclass
class GetExecutionHistoryTool(FunctionTool):
    name: str = "astrbot_get_execution_history"
    description: str = "Get execution history from current sandbox."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "exec_type": {"type": "string"},
                "success_only": {"type": "boolean", "default": False},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
                "tags": {"type": "string"},
                "has_notes": {"type": "boolean", "default": False},
                "has_description": {"type": "boolean", "default": False},
            },
            "required": [],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        exec_type: str | None = None,
        success_only: bool = False,
        limit: int = 100,
        offset: int = 0,
        tags: str | None = None,
        has_notes: bool = False,
        has_description: bool = False,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            _client, sandbox = await _get_neo_context(context)
            result = await sandbox.get_execution_history(
                exec_type=exec_type,
                success_only=success_only,
                limit=limit,
                offset=offset,
                tags=tags,
                has_notes=has_notes,
                has_description=has_description,
            )
            return _to_json_text(result)
        except Exception as e:
            return f"Error getting execution history: {str(e)}"


@dataclass
class AnnotateExecutionTool(FunctionTool):
    name: str = "astrbot_annotate_execution"
    description: str = "Annotate one execution history record."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "execution_id": {"type": "string"},
                "description": {"type": "string"},
                "tags": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["execution_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        execution_id: str,
        description: str | None = None,
        tags: str | None = None,
        notes: str | None = None,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            _client, sandbox = await _get_neo_context(context)
            result = await sandbox.annotate_execution(
                execution_id=execution_id,
                description=description,
                tags=tags,
                notes=notes,
            )
            return _to_json_text(result)
        except Exception as e:
            return f"Error annotating execution: {str(e)}"


@dataclass
class CreateSkillPayloadTool(FunctionTool):
    name: str = "astrbot_create_skill_payload"
    description: str = "Create a generic skill payload and return payload_ref."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "payload": {
                    "anyOf": [{"type": "object"}, {"type": "array"}],
                    "description": (
                        "Skill payload JSON. Recommended fields: skill_markdown, commands, meta."
                    ),
                },
                "kind": {
                    "type": "string",
                    "description": "Payload kind.",
                    "default": "astrbot_skill_v1",
                },
            },
            "required": ["payload"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        payload: dict[str, Any] | list[Any],
        kind: str = "astrbot_skill_v1",
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, _sandbox = await _get_neo_context(context)
            result = await client.skills.create_payload(payload=payload, kind=kind)
            return _to_json_text(result)
        except Exception as e:
            return f"Error creating skill payload: {str(e)}"


@dataclass
class GetSkillPayloadTool(FunctionTool):
    name: str = "astrbot_get_skill_payload"
    description: str = "Get one skill payload by payload_ref."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "payload_ref": {"type": "string"},
            },
            "required": ["payload_ref"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        payload_ref: str,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, _sandbox = await _get_neo_context(context)
            result = await client.skills.get_payload(payload_ref)
            return _to_json_text(result)
        except Exception as e:
            return f"Error getting skill payload: {str(e)}"


@dataclass
class CreateSkillCandidateTool(FunctionTool):
    name: str = "astrbot_create_skill_candidate"
    description: str = "Create a skill candidate from source execution IDs."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "skill_key": {"type": "string"},
                "source_execution_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "scenario_key": {"type": "string"},
                "payload_ref": {"type": "string"},
            },
            "required": ["skill_key", "source_execution_ids"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        skill_key: str,
        source_execution_ids: list[str],
        scenario_key: str | None = None,
        payload_ref: str | None = None,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, _sandbox = await _get_neo_context(context)
            result = await client.skills.create_candidate(
                skill_key=skill_key,
                source_execution_ids=source_execution_ids,
                scenario_key=scenario_key,
                payload_ref=payload_ref,
            )
            return _to_json_text(result)
        except Exception as e:
            return f"Error creating skill candidate: {str(e)}"


@dataclass
class ListSkillCandidatesTool(FunctionTool):
    name: str = "astrbot_list_skill_candidates"
    description: str = "List skill candidates."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "skill_key": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
            "required": [],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        status: str | None = None,
        skill_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, _sandbox = await _get_neo_context(context)
            result = await client.skills.list_candidates(
                status=status,
                skill_key=skill_key,
                limit=limit,
                offset=offset,
            )
            return _to_json_text(result)
        except Exception as e:
            return f"Error listing skill candidates: {str(e)}"


@dataclass
class EvaluateSkillCandidateTool(FunctionTool):
    name: str = "astrbot_evaluate_skill_candidate"
    description: str = "Evaluate a skill candidate."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "passed": {"type": "boolean"},
                "score": {"type": "number"},
                "benchmark_id": {"type": "string"},
                "report": {"type": "string"},
            },
            "required": ["candidate_id", "passed"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        candidate_id: str,
        passed: bool,
        score: float | None = None,
        benchmark_id: str | None = None,
        report: str | None = None,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, _sandbox = await _get_neo_context(context)
            result = await client.skills.evaluate_candidate(
                candidate_id,
                passed=passed,
                score=score,
                benchmark_id=benchmark_id,
                report=report,
            )
            return _to_json_text(result)
        except Exception as e:
            return f"Error evaluating skill candidate: {str(e)}"


@dataclass
class PromoteSkillCandidateTool(FunctionTool):
    name: str = "astrbot_promote_skill_candidate"
    description: str = "Promote one candidate to release stage (canary/stable)."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "string"},
                "stage": {
                    "type": "string",
                    "description": "Release stage: canary/stable",
                    "default": "canary",
                },
                "sync_to_local": {
                    "type": "boolean",
                    "description": "When stage is stable, sync payload.skill_markdown to local SKILL.md.",
                    "default": True,
                },
            },
            "required": ["candidate_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        candidate_id: str,
        stage: str = "canary",
        sync_to_local: bool = True,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        if stage not in {"canary", "stable"}:
            return "Error promoting skill candidate: stage must be canary or stable."

        try:
            client, _sandbox = await _get_neo_context(context)
            release = await client.skills.promote_candidate(candidate_id, stage=stage)
            release_json = _to_jsonable(release)

            sync_json: dict[str, Any] | None = None
            rollback_json: dict[str, Any] | None = None
            if stage == "stable" and sync_to_local:
                sync_mgr = NeoSkillSyncManager()
                try:
                    sync_result = await sync_mgr.sync_release(
                        client,
                        release_id=str(release_json.get("id", "")),
                        require_stable=True,
                    )
                    sync_json = {
                        "skill_key": sync_result.skill_key,
                        "local_skill_name": sync_result.local_skill_name,
                        "release_id": sync_result.release_id,
                        "candidate_id": sync_result.candidate_id,
                        "payload_ref": sync_result.payload_ref,
                        "map_path": sync_result.map_path,
                        "synced_at": sync_result.synced_at,
                    }
                except Exception as sync_err:
                    # Keep state consistent by rolling back the new release.
                    try:
                        rollback = await client.skills.rollback_release(
                            str(release_json.get("id", ""))
                        )
                        rollback_json = _to_jsonable(rollback)
                    except Exception as rollback_err:
                        return (
                            "Error promoting skill candidate: stable release synced failed; "
                            f"auto rollback also failed. sync_error={sync_err}; "
                            f"rollback_error={rollback_err}"
                        )
                    return (
                        "Error promoting skill candidate: stable release synced failed; "
                        f"auto rollback succeeded. sync_error={sync_err}; "
                        f"rollback={_to_json_text(rollback_json)}"
                    )

            return _to_json_text(
                {
                    "release": release_json,
                    "sync": sync_json,
                    "rollback": rollback_json,
                }
            )
        except Exception as e:
            return f"Error promoting skill candidate: {str(e)}"


@dataclass
class ListSkillReleasesTool(FunctionTool):
    name: str = "astrbot_list_skill_releases"
    description: str = "List skill releases."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "skill_key": {"type": "string"},
                "active_only": {"type": "boolean", "default": False},
                "stage": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
            "required": [],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        skill_key: str | None = None,
        active_only: bool = False,
        stage: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, _sandbox = await _get_neo_context(context)
            result = await client.skills.list_releases(
                skill_key=skill_key,
                active_only=active_only,
                stage=stage,
                limit=limit,
                offset=offset,
            )
            return _to_json_text(result)
        except Exception as e:
            return f"Error listing skill releases: {str(e)}"


@dataclass
class RollbackSkillReleaseTool(FunctionTool):
    name: str = "astrbot_rollback_skill_release"
    description: str = "Rollback one skill release."
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "release_id": {"type": "string"},
            },
            "required": ["release_id"],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        release_id: str,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, _sandbox = await _get_neo_context(context)
            result = await client.skills.rollback_release(release_id)
            return _to_json_text(result)
        except Exception as e:
            return f"Error rolling back skill release: {str(e)}"


@dataclass
class SyncSkillReleaseTool(FunctionTool):
    name: str = "astrbot_sync_skill_release"
    description: str = (
        "Sync stable Neo release payload to local SKILL.md and update mapping metadata."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "release_id": {"type": "string"},
                "skill_key": {"type": "string"},
                "require_stable": {"type": "boolean", "default": True},
            },
            "required": [],
        }
    )

    async def call(
        self,
        context: ContextWrapper[AstrAgentContext],
        release_id: str | None = None,
        skill_key: str | None = None,
        require_stable: bool = True,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, _sandbox = await _get_neo_context(context)
            sync_mgr = NeoSkillSyncManager()
            result = await sync_mgr.sync_release(
                client,
                release_id=release_id,
                skill_key=skill_key,
                require_stable=require_stable,
            )
            return _to_json_text(
                {
                    "skill_key": result.skill_key,
                    "local_skill_name": result.local_skill_name,
                    "release_id": result.release_id,
                    "candidate_id": result.candidate_id,
                    "payload_ref": result.payload_ref,
                    "map_path": result.map_path,
                    "synced_at": result.synced_at,
                }
            )
        except Exception as e:
            return f"Error syncing skill release: {str(e)}"
