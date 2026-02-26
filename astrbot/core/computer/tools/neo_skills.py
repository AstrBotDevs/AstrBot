import json
from collections.abc import Awaitable, Callable
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
        return "error: Permission denied. Skill lifecycle tools are only allowed for admin users."
    return None


async def _get_neo_context(
    context: ContextWrapper[AstrAgentContext],
) -> tuple[Any, Any]:
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
class NeoSkillToolBase(FunctionTool):
    error_prefix: str = "Error"

    async def _run(
        self,
        context: ContextWrapper[AstrAgentContext],
        neo_call: Callable[[Any, Any], Awaitable[Any]],
        error_action: str,
    ) -> ToolExecResult:
        if err := _ensure_admin(context):
            return err
        try:
            client, sandbox = await _get_neo_context(context)
            result = await neo_call(client, sandbox)
            return _to_json_text(result)
        except Exception as e:
            return f"{self.error_prefix} {error_action}: {str(e)}"


@dataclass
class GetExecutionHistoryTool(NeoSkillToolBase):
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
        return await self._run(
            context,
            lambda _client, sandbox: sandbox.get_execution_history(
                exec_type=exec_type,
                success_only=success_only,
                limit=limit,
                offset=offset,
                tags=tags,
                has_notes=has_notes,
                has_description=has_description,
            ),
            error_action="getting execution history",
        )


@dataclass
class AnnotateExecutionTool(NeoSkillToolBase):
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
        return await self._run(
            context,
            lambda _client, sandbox: sandbox.annotate_execution(
                execution_id=execution_id,
                description=description,
                tags=tags,
                notes=notes,
            ),
            error_action="annotating execution",
        )


@dataclass
class CreateSkillPayloadTool(NeoSkillToolBase):
    name: str = "astrbot_create_skill_payload"
    description: str = (
        "Step 1/3 for Neo skill authoring: create immutable payload content and return payload_ref. "
        "Use this to store skill_markdown and structured metadata; do NOT write local skill folders directly."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "payload": {
                    "anyOf": [{"type": "object"}, {"type": "array"}],
                    "description": (
                        "Skill payload JSON. Typical schema: {skill_markdown, inputs, outputs, meta}. "
                        "This only stores content and returns payload_ref; it does not create a candidate or release."
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
        return await self._run(
            context,
            lambda client, _sandbox: client.skills.create_payload(
                payload=payload,
                kind=kind,
            ),
            error_action="creating skill payload",
        )


@dataclass
class GetSkillPayloadTool(NeoSkillToolBase):
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
        return await self._run(
            context,
            lambda client, _sandbox: client.skills.get_payload(payload_ref),
            error_action="getting skill payload",
        )


@dataclass
class CreateSkillCandidateTool(NeoSkillToolBase):
    name: str = "astrbot_create_skill_candidate"
    description: str = (
        "Step 2/3 for Neo skill authoring: create a candidate by binding execution evidence "
        "(source_execution_ids) with skill identity (skill_key) and optional payload_ref."
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "skill_key": {
                    "type": "string",
                    "description": "Stable logical identifier, e.g. image-collage-9grid.",
                },
                "source_execution_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Execution evidence IDs captured from sandbox history.",
                },
                "scenario_key": {
                    "type": "string",
                    "description": "Optional scenario namespace for grouping candidates.",
                },
                "payload_ref": {
                    "type": "string",
                    "description": "Optional payload reference created by astrbot_create_skill_payload.",
                },
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
        return await self._run(
            context,
            lambda client, _sandbox: client.skills.create_candidate(
                skill_key=skill_key,
                source_execution_ids=source_execution_ids,
                scenario_key=scenario_key,
                payload_ref=payload_ref,
            ),
            error_action="creating skill candidate",
        )


@dataclass
class ListSkillCandidatesTool(NeoSkillToolBase):
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
        return await self._run(
            context,
            lambda client, _sandbox: client.skills.list_candidates(
                status=status,
                skill_key=skill_key,
                limit=limit,
                offset=offset,
            ),
            error_action="listing skill candidates",
        )


@dataclass
class EvaluateSkillCandidateTool(NeoSkillToolBase):
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
        return await self._run(
            context,
            lambda client, _sandbox: client.skills.evaluate_candidate(
                candidate_id,
                passed=passed,
                score=score,
                benchmark_id=benchmark_id,
                report=report,
            ),
            error_action="evaluating skill candidate",
        )


@dataclass
class PromoteSkillCandidateTool(NeoSkillToolBase):
    name: str = "astrbot_promote_skill_candidate"
    description: str = (
        "Step 3/3 for Neo skill authoring: promote candidate to canary/stable release. "
        "If stage=stable and sync_to_local=true, payload.skill_markdown is synced to local SKILL.md automatically."
    )
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
                    "description": (
                        "Only used with stage=stable. true means sync payload.skill_markdown to local SKILL.md; "
                        "false means release remains Neo-side only."
                    ),
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
            sync_mgr = NeoSkillSyncManager()
            result = await sync_mgr.promote_with_optional_sync(
                client,
                candidate_id=candidate_id,
                stage=stage,
                sync_to_local=sync_to_local,
            )
            if result.get("sync_error"):
                rollback_json = result.get("rollback")
                if rollback_json:
                    return (
                        "Error promoting skill candidate: stable release synced failed; "
                        f"auto rollback succeeded. sync_error={result['sync_error']}; "
                        f"rollback={_to_json_text(rollback_json)}"
                    )
            return _to_json_text(
                {
                    "release": result.get("release"),
                    "sync": result.get("sync"),
                    "rollback": result.get("rollback"),
                }
            )
        except Exception as e:
            return f"Error promoting skill candidate: {str(e)}"


@dataclass
class ListSkillReleasesTool(NeoSkillToolBase):
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
        return await self._run(
            context,
            lambda client, _sandbox: client.skills.list_releases(
                skill_key=skill_key,
                active_only=active_only,
                stage=stage,
                limit=limit,
                offset=offset,
            ),
            error_action="listing skill releases",
        )


@dataclass
class RollbackSkillReleaseTool(NeoSkillToolBase):
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
        return await self._run(
            context,
            lambda client, _sandbox: client.skills.rollback_release(release_id),
            error_action="rolling back skill release",
        )


@dataclass
class SyncSkillReleaseTool(NeoSkillToolBase):
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
        return await self._run(
            context,
            lambda client, _sandbox: _sync_release_to_dict(
                client,
                release_id=release_id,
                skill_key=skill_key,
                require_stable=require_stable,
            ),
            error_action="syncing skill release",
        )


async def _sync_release_to_dict(
    client: Any,
    *,
    release_id: str | None,
    skill_key: str | None,
    require_stable: bool,
) -> dict[str, str]:
    sync_mgr = NeoSkillSyncManager()
    result = await sync_mgr.sync_release(
        client,
        release_id=release_id,
        skill_key=skill_key,
        require_stable=require_stable,
    )
    return sync_mgr.sync_result_to_dict(result)
