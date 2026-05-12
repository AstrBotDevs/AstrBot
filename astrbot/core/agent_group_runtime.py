from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path

PRESET_NOT_FOUND = "preset_not_found"
RUN_NOT_FOUND = "run_not_found"
RUN_EXISTS = "run_exists"
RUN_NOT_ACTIVE = "run_not_active"
MEMBER_NOT_FOUND = "member_not_found"
MEMBER_IMPERSONATION = "member_impersonation"
VERSION_CONFLICT = "version_conflict"
INVALID_WORKSPACE = "invalid_workspace"
INVALID_PRESET = "invalid_preset"
INVALID_HELPER_NAME = "invalid_helper_name"
HELPER_SUBAGENT_NOT_FOUND = "helper_subagent_not_found"
HELPER_SUBAGENT_EXISTS = "helper_subagent_exists"
DEFAULT_SUMMARY_PRESET = "agent_group_summary"

ACTIVE_RUN_STATUSES = {"active", "waiting_for_input"}
TERMINAL_RUN_STATUSES = {"completed", "failed", "limit_reached", "cancelled"}
NOTIFIABLE_RUN_STATUSES = {
    "completed",
    "failed",
    "limit_reached",
    "cancelled",
    "waiting_for_input",
}
MEMBER_TOOL_NAMES = (
    "msg_to_agent",
    "msg_to_group",
    "mark_complete",
    "revoke_complete",
    "get_group_status",
    "ask_local_agent",
    "create_group_subagent",
    "run_group_subagent",
    "reset_group_subagent",
    "delete_group_subagent",
)
_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_HELPER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_UNSET = object()


@dataclass
class AgentGroupMemberPreset:
    name: str
    source_type: str = "subagent"
    subagent_preset: str = ""
    persona_id: str = ""
    checkpoint_async_enabled: bool | None = None
    """null = inherit, true = enabled, false = disabled"""
    checkpoint_async_provider_id: str | None = None
    """null = inherit from chain"""


def resolve_checkpoint_enabled(
    member_value: bool | None,
    preset_value: bool | None = None,
    category_default: bool = False,
) -> bool:
    """Resolve checkpoint enabled value using the chain:
    member > preset > category_default
    Returns the first non-None value, or category_default.
    """
    if member_value is not None:
        return member_value
    if preset_value is not None:
        return preset_value
    return category_default


def resolve_checkpoint_provider_id(
    member_value: str | None,
    preset_value: str | None = None,
    global_value: str = "",
) -> str:
    """Resolve checkpoint provider_id using the chain:
    member > preset > global
    Returns the first non-None, non-empty value.
    """
    if member_value:
        return member_value
    if preset_value:
        return preset_value
    return global_value


@dataclass
class AgentGroupPreset:
    name: str
    members: list[AgentGroupMemberPreset]
    initial_recipients: list[str]
    principles: list[str]
    collaboration_prompt: str = ""
    summary_preset: str = DEFAULT_SUMMARY_PRESET
    summary_include_private: bool = False
    token_limit: int | None = None
    time_limit_seconds: int | None = None


@dataclass
class AgentGroupRuntimeError:
    error_code: str
    message: str
    details: Any = None


@dataclass
class AgentGroupRuntimeResult:
    ok: bool
    data: Any = None
    error: AgentGroupRuntimeError | None = None

    @classmethod
    def success(cls, data: Any = None) -> AgentGroupRuntimeResult:
        return cls(ok=True, data=data)

    @classmethod
    def failure(
        cls,
        error_code: str,
        message: str,
        details: Any = None,
    ) -> AgentGroupRuntimeResult:
        return cls(
            ok=False,
            error=AgentGroupRuntimeError(error_code, message, details),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": asdict(self.error) if self.error else None,
        }


class _AgentGroupMemberEventView:
    def __init__(self, event, extras: dict[str, Any]) -> None:
        self._event = event
        self._extras = {
            key: value for key, value in extras.items() if value is not None
        }

    def __getattr__(self, name: str) -> Any:
        return getattr(self._event, name)

    def get_extra(self, key: str) -> Any:
        if key in self._extras:
            return self._extras[key]
        getter = getattr(self._event, "get_extra", None)
        if getter is None:
            return None
        return getter(key)

    def set_extra(self, key: str, value: Any) -> None:
        self._extras[key] = value


class _WorkspaceWriteLease:
    def __init__(self, lock: asyncio.Lock) -> None:
        self._lock = lock
        self._released = False

    async def __aenter__(self) -> _WorkspaceWriteLease:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.release()

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._lock.release()


class AgentGroupRuntimeManager:
    def __init__(
        self,
        db,
        subagent_runtime_manager,
        conversation_manager,
        config: dict | None = None,
    ) -> None:
        self.db = db
        self.subagent_runtime_manager = subagent_runtime_manager
        self.conversation_manager = conversation_manager
        self.presets: dict[str, AgentGroupPreset] = {}
        self._workspace_locks: dict[str, asyncio.Lock] = {}
        self._workspace_write_locks: dict[str, asyncio.Lock] = {}
        self._run_state_locks: dict[str, asyncio.Lock] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._time_limit_handles: set[asyncio.TimerHandle] = set()
        self.workspace_root = Path(get_astrbot_workspaces_path()) / "agent_groups"
        if config is not None:
            self.reload_from_config(config)

    def reload_from_config(self, cfg: dict | None) -> None:
        self.presets = {preset.name: preset for preset in self.normalize_presets(cfg)}

    def normalize_presets(self, cfg: dict | None) -> list[AgentGroupPreset]:
        if not isinstance(cfg, dict):
            return []

        presets = []
        for raw_preset in cfg.get("presets", []):
            if not isinstance(raw_preset, dict):
                continue
            if raw_preset.get("enabled", True) is False:
                continue
            name = str(raw_preset.get("name") or "").strip()
            if not name:
                continue

            members = []
            for raw_member in raw_preset.get("members", []):
                if not isinstance(raw_member, dict):
                    continue
                if raw_member.get("enabled", True) is False:
                    continue
                member_name = str(raw_member.get("name") or "").strip()
                source_type = str(raw_member.get("source_type") or "").strip()
                subagent_preset = str(raw_member.get("subagent_preset") or "").strip()
                persona_id = str(raw_member.get("persona_id") or "").strip()
                if source_type not in {"subagent", "persona"}:
                    source_type = (
                        "persona" if persona_id and not subagent_preset else "subagent"
                    )
                if not member_name:
                    continue
                if source_type == "subagent" and not subagent_preset:
                    continue
                if source_type == "persona" and not persona_id:
                    continue
                members.append(
                    AgentGroupMemberPreset(
                        name=member_name,
                        source_type=source_type,
                        subagent_preset=subagent_preset
                        if source_type == "subagent"
                        else "",
                        persona_id=persona_id if source_type == "persona" else "",
                    )
                )

            presets.append(
                AgentGroupPreset(
                    name=name,
                    members=members,
                    initial_recipients=self._string_list(
                        raw_preset.get("initial_recipients")
                    ),
                    principles=self._string_list(raw_preset.get("principles")),
                    collaboration_prompt=str(
                        raw_preset.get("collaboration_prompt") or ""
                    ),
                    summary_preset=str(
                        raw_preset.get("summary_preset")
                        or cfg.get("summary_preset")
                        or DEFAULT_SUMMARY_PRESET
                    ).strip()
                    or DEFAULT_SUMMARY_PRESET,
                    summary_include_private=bool(
                        raw_preset.get("summary_include_private", False)
                    ),
                    token_limit=self._positive_int_or_none(
                        raw_preset.get("token_limit")
                    ),
                    time_limit_seconds=self._positive_int_or_none(
                        raw_preset.get("time_limit_seconds")
                    ),
                )
            )

        return presets

    def list_presets(self) -> list[AgentGroupPreset]:
        return list(self.presets.values())

    async def start_run(
        self,
        event,
        preset_name: str,
        task: str,
        *,
        workspace_id: str | None = None,
        metadata: dict | None = None,
        runtime_context: Any = None,
        dispatch_initial: bool = True,
    ) -> AgentGroupRuntimeResult:
        preset = self.presets.get(preset_name)
        if preset is None:
            return AgentGroupRuntimeResult.failure(
                PRESET_NOT_FOUND,
                "Agent group preset was not found.",
            )
        if not preset.members:
            return AgentGroupRuntimeResult.failure(
                INVALID_PRESET,
                "Agent group preset has no enabled members.",
            )

        workspace_id = await self._resolve_workspace_id(event, preset, workspace_id)
        try:
            workspace_path = self.ensure_workspace_path(workspace_id)
        except ValueError as exc:
            return AgentGroupRuntimeResult.failure(
                INVALID_WORKSPACE,
                str(exc),
                {"workspace_id": workspace_id},
            )

        workspace_lock = self._workspace_locks.setdefault(workspace_id, asyncio.Lock())
        async with workspace_lock:
            active = await self.db.get_active_agent_group_run_for_workspace(
                workspace_id
            )
            if active is not None:
                expired = await self._expire_if_time_limit_reached(
                    active,
                    runtime_context=runtime_context,
                )
                if expired is None:
                    return AgentGroupRuntimeResult.failure(
                        RUN_EXISTS,
                        "An active agent group run already exists for this workspace.",
                        {
                            "run_id": self._value(active, "run_id"),
                            "workspace_id": workspace_id,
                        },
                    )

            umo = self._value(event, "unified_msg_origin")
            conversation_id = await self._resolve_conversation_id(event)
            members = [self._member_state(member) for member in preset.members]
            initial_recipients = [
                name
                for name in preset.initial_recipients
                if any(member["name"] == name for member in members)
            ] or [members[0]["name"]]
            started_at_epoch = self._now()
            run_metadata = {
                **(metadata or {}),
                "workspace_path": str(workspace_path),
                "initial_recipients": initial_recipients,
                "principles": list(preset.principles),
                "collaboration_prompt": preset.collaboration_prompt,
                "summary_preset": preset.summary_preset,
                "summary_include_private": preset.summary_include_private,
                "token_limit": preset.token_limit,
                "time_limit_seconds": preset.time_limit_seconds,
                "started_at_epoch": started_at_epoch,
            }
            if preset.time_limit_seconds is not None:
                run_metadata["deadline_at_epoch"] = (
                    started_at_epoch + preset.time_limit_seconds
                )
            messages = [
                {
                    "from": "local_agent",
                    "to": "group",
                    "content": task,
                    "private": False,
                }
            ]

            run = await self.db.create_agent_group_run(
                umo=umo,
                conversation_id=conversation_id,
                workspace_id=workspace_id,
                preset_name=preset.name,
                task=task,
                status="active",
                members=members,
                messages=messages,
                final_opinions={},
                summary=None,
                token_usage={"total": 0, "members": {}},
                metadata=run_metadata,
            )

            instance_result = await self._create_member_instances(
                event,
                run,
                preset,
                members,
            )
            if not instance_result.ok:
                await self._save_state(
                    run,
                    status="failed",
                    members=members,
                    messages=messages,
                    final_opinions={},
                    summary=None,
                    token_usage={"total": 0, "members": {}},
                    metadata=run_metadata,
                )
                return instance_result

            saved = await self._save_state(
                run,
                status="active",
                members=members,
                messages=messages,
                final_opinions={},
                summary=None,
                token_usage={"total": 0, "members": {}},
                metadata=run_metadata,
                runtime_context=runtime_context,
            )
            if not saved.ok:
                return saved
            self._schedule_time_limit_watchdog(
                saved.data,
                runtime_context=runtime_context,
            )
            if dispatch_initial:
                self._schedule_initial_dispatch(
                    event,
                    saved.data,
                    runtime_context=runtime_context,
                )
            return saved

    async def get_status(
        self,
        *,
        run_id: str | None = None,
        workspace_id: str | None = None,
        include_private: bool = False,
    ) -> AgentGroupRuntimeResult:
        run = None
        if run_id:
            run = await self.db.get_agent_group_run(run_id)
        elif workspace_id:
            run = await self.db.get_active_agent_group_run_for_workspace(workspace_id)
        if run is None:
            return AgentGroupRuntimeResult.failure(
                RUN_NOT_FOUND,
                "Agent group run was not found.",
            )
        expired = await self._expire_if_time_limit_reached(run)
        if expired is not None:
            return expired
        return AgentGroupRuntimeResult.success(
            self._run_payload(run, include_private=include_private)
        )

    async def list_runs(
        self,
        *,
        umo: str | None = None,
        workspace_id: str | None = None,
        status: str | None = None,
        include_private: bool = False,
    ) -> AgentGroupRuntimeResult:
        runs = await self.db.list_agent_group_runs(
            umo=umo,
            workspace_id=workspace_id,
            status=status,
        )
        return AgentGroupRuntimeResult.success(
            {
                "runs": [
                    self._run_payload(run, include_private=include_private)
                    for run in runs
                ]
            }
        )

    async def send_input(
        self,
        run_id: str,
        content: str,
        *,
        event=None,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        loaded = await self._load_mutable_run(run_id)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        recipients = self._active_member_names(members)
        messages = list(self._value(run, "messages") or [])
        messages.append(
            {
                "from": "local_agent",
                "to": "group",
                "content": content,
                "private": False,
            }
        )
        metadata = dict(self._run_metadata(run))
        self._mark_messages_unread(metadata, recipients, [len(messages) - 1])
        saved = await self._save_state(
            run,
            status="active",
            messages=messages,
            metadata=metadata,
        )
        if saved.ok:
            self._schedule_member_dispatches(
                event,
                saved.data,
                recipients,
                runtime_context=runtime_context,
            )
        return saved

    async def cancel_run(
        self,
        run_id: str,
        reason: str | None = None,
        *,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        loaded = await self._load_mutable_run(run_id, allow_terminal=True)
        if not loaded.ok:
            return loaded
        run = loaded.data
        metadata = dict(self._run_metadata(run))
        if reason:
            metadata["cancel_reason"] = reason
        return await self._save_state(
            run,
            status="cancelled",
            metadata=metadata,
            runtime_context=runtime_context,
        )

    async def msg_to_agent(
        self,
        run_id: str,
        *,
        from_member: str,
        to_member: str,
        content: str,
        actor_member: str | None = None,
        event=None,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        if actor_member and actor_member != from_member:
            return self._member_impersonation_result(actor_member, from_member)
        loaded = await self._load_mutable_run(run_id)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        if not self._member_exists(members, from_member):
            return self._member_missing_result(from_member)
        if not self._member_exists(members, to_member):
            return self._member_missing_result(to_member)
        messages = list(self._value(run, "messages") or [])
        messages.append(
            {
                "from": from_member,
                "to": to_member,
                "content": content,
                "private": True,
            }
        )
        recipients = []
        if to_member != "local_agent" and to_member in self._active_member_names(
            members
        ):
            recipients.append(to_member)
        metadata = dict(self._run_metadata(run))
        self._mark_messages_unread(metadata, recipients, [len(messages) - 1])
        saved = await self._save_state(run, messages=messages, metadata=metadata)
        if saved.ok:
            self._schedule_member_dispatches(
                event,
                saved.data,
                recipients,
                runtime_context=runtime_context,
            )
        return saved

    async def msg_to_group(
        self,
        run_id: str,
        *,
        from_member: str,
        content: str,
        actor_member: str | None = None,
        event=None,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        if actor_member and actor_member != from_member:
            return self._member_impersonation_result(actor_member, from_member)
        loaded = await self._load_mutable_run(run_id)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        if not self._member_exists(members, from_member):
            return self._member_missing_result(from_member)
        messages = list(self._value(run, "messages") or [])
        messages.append(
            {
                "from": from_member,
                "to": "group",
                "content": content,
                "private": False,
            }
        )
        recipients = self._active_member_names(members, exclude={from_member})
        metadata = dict(self._run_metadata(run))
        self._mark_messages_unread(metadata, recipients, [len(messages) - 1])
        saved = await self._save_state(run, messages=messages, metadata=metadata)
        if saved.ok:
            self._schedule_member_dispatches(
                event,
                saved.data,
                recipients,
                runtime_context=runtime_context,
            )
        return saved

    async def ask_local_agent(
        self,
        run_id: str,
        *,
        from_member: str,
        question: str,
        actor_member: str | None = None,
        event=None,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        if actor_member and actor_member != from_member:
            return self._member_impersonation_result(actor_member, from_member)
        loaded = await self._load_mutable_run(run_id)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        if not self._member_exists(members, from_member):
            return self._member_missing_result(from_member)
        messages = list(self._value(run, "messages") or [])
        messages.append(
            {
                "from": from_member,
                "to": "local_agent",
                "content": question,
                "private": True,
            }
        )
        return await self._save_state(
            run,
            status="waiting_for_input",
            messages=messages,
            runtime_context=runtime_context,
        )

    async def record_workspace_file_read(
        self,
        run_id: str,
        member_name: str,
        path: str,
    ) -> AgentGroupRuntimeResult:
        loaded = await self._load_member_workspace_run(run_id, member_name)
        if not loaded.ok:
            return loaded
        run = loaded.data
        try:
            resolved_path, relative_path = self._resolve_workspace_file_path(
                run,
                path,
            )
        except ValueError as exc:
            return AgentGroupRuntimeResult.failure(
                INVALID_WORKSPACE,
                str(exc),
                {"path": path},
            )

        metadata = dict(self._run_metadata(run))
        file_versions = self._workspace_file_versions(metadata)
        member_versions = dict(file_versions.get(member_name) or {})
        member_versions[relative_path] = self._workspace_file_fingerprint(resolved_path)
        file_versions[member_name] = member_versions
        metadata["workspace_file_versions"] = file_versions
        return await self._save_state(run, metadata=metadata)

    async def resolve_workspace_file_path(
        self,
        run_id: str,
        member_name: str,
        path: str,
    ) -> AgentGroupRuntimeResult:
        loaded = await self._load_member_workspace_run(run_id, member_name)
        if not loaded.ok:
            return loaded
        try:
            resolved_path, relative_path = self._resolve_workspace_file_path(
                loaded.data,
                path,
            )
        except ValueError as exc:
            return AgentGroupRuntimeResult.failure(
                INVALID_WORKSPACE,
                str(exc),
                {"path": path},
            )
        return AgentGroupRuntimeResult.success(
            {"path": str(resolved_path), "relative_path": relative_path}
        )

    async def record_workspace_file_write(
        self,
        run_id: str,
        member_name: str,
        paths: list[str] | tuple[str, ...] | None = None,
    ) -> AgentGroupRuntimeResult:
        loaded = await self._load_member_workspace_run(run_id, member_name)
        if not loaded.ok:
            return loaded
        run = loaded.data
        metadata = dict(self._run_metadata(run))
        file_versions = self._workspace_file_versions(metadata)
        member_versions = dict(file_versions.get(member_name) or {})
        try:
            for path in paths or []:
                resolved_path, relative_path = self._resolve_workspace_file_path(
                    run,
                    path,
                )
                member_versions[relative_path] = self._workspace_file_fingerprint(
                    resolved_path
                )
        except ValueError as exc:
            return AgentGroupRuntimeResult.failure(
                INVALID_WORKSPACE,
                str(exc),
                {"path": path},
            )
        file_versions[member_name] = member_versions
        metadata["workspace_file_versions"] = file_versions
        return await self._save_state(run, metadata=metadata)

    async def acquire_workspace_write_lock(
        self,
        run_id: str,
        member_name: str,
        *,
        paths: list[str] | tuple[str, ...] | None = None,
    ) -> AgentGroupRuntimeResult:
        loaded = await self._load_member_workspace_run(run_id, member_name)
        if not loaded.ok:
            return loaded
        run = loaded.data
        workspace_id = self._value(run, "workspace_id")
        lock = self._workspace_write_locks.setdefault(workspace_id, asyncio.Lock())
        await lock.acquire()
        lease = _WorkspaceWriteLease(lock)

        reloaded = await self.db.get_agent_group_run(run_id)
        if reloaded is None:
            await lease.release()
            return AgentGroupRuntimeResult.failure(
                RUN_NOT_FOUND,
                "Agent group run was not found.",
            )
        if self._value(reloaded, "status") not in ACTIVE_RUN_STATUSES:
            await lease.release()
            return AgentGroupRuntimeResult.failure(
                RUN_NOT_ACTIVE,
                "Agent group run is not active.",
                {"status": self._value(reloaded, "status")},
            )
        conflict = self._workspace_version_conflict(
            reloaded,
            member_name,
            paths or [],
        )
        if conflict is not None:
            await lease.release()
            return conflict
        return AgentGroupRuntimeResult.success(lease)

    async def create_helper_subagent(
        self,
        run_id: str,
        *,
        from_member: str,
        helper_name: str,
        preset_name: str,
        actor_member: str | None = None,
        event=None,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        if actor_member and actor_member != from_member:
            return self._member_impersonation_result(actor_member, from_member)
        if not self._valid_helper_name(helper_name):
            return AgentGroupRuntimeResult.failure(
                INVALID_HELPER_NAME,
                "Helper SubAgent name is invalid.",
                {"helper_name": helper_name},
            )
        if self.subagent_runtime_manager is None:
            return AgentGroupRuntimeResult.failure(
                "subagent_runtime_unavailable",
                "SubAgent runtime manager is not available.",
            )
        loaded = await self._load_mutable_run(run_id)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        creator = self._find_member(members, from_member)
        if creator is None:
            return self._member_missing_result(from_member)

        metadata = dict(self._run_metadata(run))
        helpers = self._helper_subagents(metadata)
        helper_key = self._helper_key(from_member, helper_name)
        if helper_key in helpers:
            return AgentGroupRuntimeResult.failure(
                HELPER_SUBAGENT_EXISTS,
                "Helper SubAgent already exists for this member.",
                {"helper_name": helper_name},
            )

        instance_name = self._helper_instance_name(run_id, from_member, helper_name)
        create_result = await self.subagent_runtime_manager.create_instance(
            event,
            instance_name,
            preset_name,
            scope_type="conversation",
            overrides=self._helper_overrides(run_id, from_member, creator, preset_name),
        )
        if not getattr(create_result, "ok", False):
            return self._subagent_runtime_failure(create_result)

        helper = {
            "helper_name": helper_name,
            "creator_member": from_member,
            "preset_name": preset_name,
            "instance_name": instance_name,
            "instance_id": self._value(create_result.data, "instance_id"),
        }
        helpers[helper_key] = helper
        metadata["helper_subagents"] = helpers
        saved = await self._save_state(
            run,
            metadata=metadata,
            runtime_context=runtime_context,
        )
        if not saved.ok:
            return saved
        return AgentGroupRuntimeResult.success({"helper": helper, "run": saved.data})

    async def run_helper_subagent(
        self,
        run_id: str,
        *,
        from_member: str,
        helper_name: str,
        input_text: str,
        actor_member: str | None = None,
        event=None,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        if self.subagent_runtime_manager is None:
            return AgentGroupRuntimeResult.failure(
                "subagent_runtime_unavailable",
                "SubAgent runtime manager is not available.",
            )
        loaded = await self._load_helper(run_id, from_member, helper_name, actor_member)
        if not loaded.ok:
            return loaded
        helper = loaded.data["helper"]
        helper_event = _AgentGroupMemberEventView(
            event,
            {
                "agent_group_helper_context": {
                    "run_id": run_id,
                    "creator_member": from_member,
                    "helper_name": helper_name,
                },
                "subagent_runtime_context": runtime_context,
            },
        )
        result = await self.subagent_runtime_manager.run_instance(
            helper_event,
            helper["instance_name"],
            self._helper_input(run_id, from_member, helper_name, input_text),
            scope_type="conversation",
        )
        if not getattr(result, "ok", False):
            return self._subagent_runtime_failure(result)
        data = getattr(result, "data", {}) or {}
        return AgentGroupRuntimeResult.success(
            {
                "final_response": data.get("final_response"),
                "metadata": data.get("metadata") or {},
                "helper": helper,
            }
        )

    async def reset_helper_subagent(
        self,
        run_id: str,
        *,
        from_member: str,
        helper_name: str,
        actor_member: str | None = None,
        event=None,
    ) -> AgentGroupRuntimeResult:
        if self.subagent_runtime_manager is None:
            return AgentGroupRuntimeResult.failure(
                "subagent_runtime_unavailable",
                "SubAgent runtime manager is not available.",
            )
        loaded = await self._load_helper(run_id, from_member, helper_name, actor_member)
        if not loaded.ok:
            return loaded
        helper = loaded.data["helper"]
        result = await self.subagent_runtime_manager.reset_instance(
            event,
            helper["instance_name"],
            scope_type="conversation",
        )
        if not getattr(result, "ok", False):
            return self._subagent_runtime_failure(result)
        return AgentGroupRuntimeResult.success({"helper": helper})

    async def delete_helper_subagent(
        self,
        run_id: str,
        *,
        from_member: str,
        helper_name: str,
        actor_member: str | None = None,
        event=None,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        if self.subagent_runtime_manager is None:
            return AgentGroupRuntimeResult.failure(
                "subagent_runtime_unavailable",
                "SubAgent runtime manager is not available.",
            )
        loaded = await self._load_helper(run_id, from_member, helper_name, actor_member)
        if not loaded.ok:
            return loaded
        run = loaded.data["run"]
        metadata = dict(self._run_metadata(run))
        helpers = self._helper_subagents(metadata)
        helper_key = self._helper_key(from_member, helper_name)
        helper = helpers[helper_key]
        delete_result = await self.subagent_runtime_manager.delete_instance(
            event,
            helper["instance_name"],
            scope_type="conversation",
        )
        if not getattr(delete_result, "ok", False):
            return self._subagent_runtime_failure(delete_result)

        helpers.pop(helper_key, None)
        metadata["helper_subagents"] = helpers
        saved = await self._save_state(
            run,
            metadata=metadata,
            runtime_context=runtime_context,
        )
        if not saved.ok:
            return saved
        return AgentGroupRuntimeResult.success({"helper": helper, "run": saved.data})

    async def mark_complete(
        self,
        run_id: str,
        member_name: str,
        final_opinion: str,
        actor_member: str | None = None,
        event=None,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult:
        if actor_member and actor_member != member_name:
            return self._member_impersonation_result(actor_member, member_name)
        loaded = await self._load_mutable_run(run_id)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        member = self._find_member(members, member_name)
        if member is None:
            return self._member_missing_result(member_name)

        member["status"] = "completed"
        member["final_opinion"] = final_opinion
        final_opinions = dict(self._value(run, "final_opinions") or {})
        final_opinions[member_name] = final_opinion
        messages = list(self._value(run, "messages") or [])
        messages.append(
            {
                "from": member_name,
                "to": "group",
                "content": final_opinion,
                "private": False,
                "type": "final_opinion",
            }
        )

        status = "completed" if self._all_members_completed(members) else "active"
        summary = self._value(run, "summary")
        metadata = dict(self._run_metadata(run))
        token_usage = dict(self._value(run, "token_usage") or {})
        if status == "completed":
            summary_run = self._run_payload(run)
            summary_run.update(
                {
                    "members": members,
                    "messages": messages,
                    "final_opinions": final_opinions,
                    "metadata": metadata,
                }
            )
            summary_result = await self._execute_summary(
                event,
                summary_run,
                final_opinions,
                runtime_context=runtime_context,
            )
            summary = summary_result["summary"]
            metadata.update(summary_result.get("metadata") or {})
            summary_token_usage = summary_result.get("token_usage")
            if isinstance(summary_token_usage, int):
                token_usage["summary"] = (
                    token_usage.get("summary", 0) + summary_token_usage
                )
                token_usage["total"] = self._total_token_usage(token_usage)

        return await self._save_state(
            run,
            status=status,
            members=members,
            messages=messages,
            final_opinions=final_opinions,
            summary=summary,
            token_usage=token_usage,
            metadata=metadata,
            runtime_context=runtime_context,
        )

    async def revoke_complete(
        self,
        run_id: str,
        member_name: str,
        actor_member: str | None = None,
    ) -> AgentGroupRuntimeResult:
        if actor_member and actor_member != member_name:
            return self._member_impersonation_result(actor_member, member_name)
        loaded = await self._load_mutable_run(run_id, allow_terminal=True)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        member = self._find_member(members, member_name)
        if member is None:
            return self._member_missing_result(member_name)

        member["status"] = "active"
        member.pop("final_opinion", None)
        final_opinions = dict(self._value(run, "final_opinions") or {})
        final_opinions.pop(member_name, None)
        token_usage = dict(self._value(run, "token_usage") or {})
        token_usage.pop("summary", None)
        token_usage["total"] = self._total_token_usage(token_usage)
        return await self._save_state(
            run,
            status="active",
            members=members,
            final_opinions=final_opinions,
            summary=None,
            token_usage=token_usage,
        )

    async def _load_mutable_run(
        self,
        run_id: str,
        *,
        allow_terminal: bool = False,
    ) -> AgentGroupRuntimeResult:
        run = await self.db.get_agent_group_run(run_id)
        if run is None:
            return AgentGroupRuntimeResult.failure(
                RUN_NOT_FOUND,
                "Agent group run was not found.",
            )
        expired = await self._expire_if_time_limit_reached(run)
        if expired is not None:
            if allow_terminal:
                reloaded = await self.db.get_agent_group_run(run_id)
                return AgentGroupRuntimeResult.success(reloaded or run)
            return AgentGroupRuntimeResult.failure(
                RUN_NOT_ACTIVE,
                "Agent group run is not active.",
                {"status": "limit_reached"},
            )
        status = self._value(run, "status")
        if not allow_terminal and status in TERMINAL_RUN_STATUSES:
            return AgentGroupRuntimeResult.failure(
                RUN_NOT_ACTIVE,
                "Agent group run is not active.",
                {"status": status},
            )
        return AgentGroupRuntimeResult.success(run)

    async def _load_member_workspace_run(
        self,
        run_id: str,
        member_name: str,
    ) -> AgentGroupRuntimeResult:
        loaded = await self._load_mutable_run(run_id)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        if self._find_member(members, member_name) is None:
            return self._member_missing_result(member_name)
        return AgentGroupRuntimeResult.success(run)

    def _workspace_version_conflict(
        self,
        run,
        member_name: str,
        paths: list[str] | tuple[str, ...],
    ) -> AgentGroupRuntimeResult | None:
        metadata = self._run_metadata(run)
        member_versions = self._workspace_file_versions(metadata).get(member_name) or {}
        for path in paths:
            try:
                resolved_path, relative_path = self._resolve_workspace_file_path(
                    run,
                    path,
                )
            except ValueError as exc:
                return AgentGroupRuntimeResult.failure(
                    INVALID_WORKSPACE,
                    str(exc),
                    {"path": path},
                )
            expected = member_versions.get(relative_path)
            if expected is None:
                continue
            actual = self._workspace_file_fingerprint(resolved_path)
            if actual != expected:
                return AgentGroupRuntimeResult.failure(
                    VERSION_CONFLICT,
                    "Workspace file changed after this member last read it.",
                    {
                        "path": relative_path,
                        "expected": expected,
                        "actual": actual,
                    },
                )
        return None

    @staticmethod
    def _workspace_file_versions(metadata: dict[str, Any]) -> dict[str, Any]:
        file_versions = metadata.get("workspace_file_versions")
        return file_versions if isinstance(file_versions, dict) else {}

    def _resolve_workspace_file_path(self, run, path: str) -> tuple[Path, str]:
        metadata = self._run_metadata(run)
        workspace_path_value = metadata.get("workspace_path")
        if not workspace_path_value:
            raise ValueError("Agent group workspace path is not available.")
        workspace_path = Path(str(workspace_path_value)).resolve(strict=False)
        candidate = Path(str(path).strip()).expanduser()
        if not str(candidate):
            raise ValueError("Workspace file path must be non-empty.")
        if not candidate.is_absolute():
            candidate = workspace_path / candidate
        resolved_path = candidate.resolve(strict=False)
        if (
            resolved_path != workspace_path
            and workspace_path not in resolved_path.parents
        ):
            raise ValueError("Workspace file path escapes the agent group workspace.")
        return resolved_path, resolved_path.relative_to(workspace_path).as_posix()

    @staticmethod
    def _workspace_file_fingerprint(path: Path) -> dict[str, Any]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return {"exists": False}
        if not path.is_file():
            return {
                "exists": True,
                "kind": "non_file",
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
            }
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "exists": True,
            "kind": "file",
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "sha256": digest,
        }

    async def _save_state(
        self,
        run,
        *,
        status: str | None = None,
        members: list[dict] | None = None,
        messages: list[dict] | None = None,
        final_opinions: dict | None = None,
        summary: str | None | object = _UNSET,
        token_usage: dict | None = None,
        metadata: dict | None = None,
        runtime_context: Any = None,
        include_private: bool = False,
    ) -> AgentGroupRuntimeResult:
        previous_status = self._value(run, "status")
        next_status = status if status is not None else previous_status
        saved = await self.db.save_agent_group_state(
            self._value(run, "run_id"),
            status=next_status,
            members=members if members is not None else self._value(run, "members"),
            messages=messages if messages is not None else self._value(run, "messages"),
            final_opinions=final_opinions
            if final_opinions is not None
            else self._value(run, "final_opinions"),
            summary=summary if summary is not _UNSET else self._value(run, "summary"),
            token_usage=token_usage
            if token_usage is not None
            else self._value(run, "token_usage"),
            metadata=metadata if metadata is not None else self._run_metadata(run),
            expected_version=self._value(run, "version"),
        )
        if saved is None:
            return AgentGroupRuntimeResult.failure(
                VERSION_CONFLICT,
                "Agent group run state version conflict.",
            )
        payload = self._run_payload(saved, include_private=include_private)
        if previous_status not in TERMINAL_RUN_STATUSES and (
            next_status in TERMINAL_RUN_STATUSES
        ):
            self._schedule_helper_cleanup(payload)
        if previous_status != next_status and next_status in NOTIFIABLE_RUN_STATUSES:
            self._schedule_status_notification(runtime_context, payload)
        return AgentGroupRuntimeResult.success(payload)

    async def _expire_if_time_limit_reached(
        self,
        run,
        *,
        runtime_context: Any = None,
    ) -> AgentGroupRuntimeResult | None:
        if self._value(run, "status") not in ACTIVE_RUN_STATUSES:
            return None
        metadata = dict(self._run_metadata(run))
        deadline_at_epoch = self._float_or_none(metadata.get("deadline_at_epoch"))
        if deadline_at_epoch is None or self._now() < deadline_at_epoch:
            return None
        metadata["limit_reason"] = "time_limit"
        metadata["limit_reached_at_epoch"] = self._now()
        return await self._save_state(
            run,
            status="limit_reached",
            metadata=metadata,
            runtime_context=runtime_context,
        )

    async def _create_member_instances(
        self,
        event,
        run,
        preset: AgentGroupPreset,
        members: list[dict],
    ) -> AgentGroupRuntimeResult:
        if self.subagent_runtime_manager is None:
            return AgentGroupRuntimeResult.success()

        member_by_name = {member.name: member for member in preset.members}
        run_id = self._value(run, "run_id")
        for member_state in members:
            member_preset = member_by_name[member_state["name"]]
            instance_name = f"agent_group_{run_id}_{member_state['name']}"
            overrides = {
                "system_prompt_delta": self._member_prompt_delta(
                    preset,
                    member_preset,
                    run_id,
                ),
            }
            member_tools = self._member_tools(member_preset)
            if member_tools is not None:
                overrides["tools"] = member_tools

            if member_preset.source_type == "persona":
                result = (
                    await self.subagent_runtime_manager.create_instance_from_persona(
                        event,
                        instance_name,
                        member_preset.persona_id,
                        scope_type="conversation",
                        overrides=overrides,
                    )
                )
            else:
                result = await self.subagent_runtime_manager.create_instance(
                    event,
                    instance_name,
                    member_preset.subagent_preset,
                    scope_type="conversation",
                    overrides=overrides,
                )
            if not getattr(result, "ok", False):
                member_state["status"] = "failed"
                error = getattr(result, "error", None)
                return AgentGroupRuntimeResult.failure(
                    getattr(error, "error_code", "subagent_create_failed"),
                    getattr(error, "message", "Failed to create group member."),
                    getattr(error, "details", None),
                )
            member_state["instance_name"] = instance_name
            member_state["instance_id"] = self._value(result.data, "instance_id")
        return AgentGroupRuntimeResult.success()

    def _schedule_time_limit_watchdog(
        self,
        run_payload: dict[str, Any],
        *,
        runtime_context: Any = None,
    ) -> None:
        metadata = run_payload.get("metadata") or {}
        deadline_at_epoch = self._float_or_none(metadata.get("deadline_at_epoch"))
        if deadline_at_epoch is None:
            return

        delay = max(0.0, deadline_at_epoch - self._now())
        run_id = run_payload["run_id"]
        handle: asyncio.TimerHandle | None = None

        def start_expiry_task() -> None:
            if handle is not None:
                self._time_limit_handles.discard(handle)
            task = asyncio.create_task(
                self._expire_run_after_deadline(
                    run_id,
                    runtime_context=runtime_context,
                ),
                name=f"agent_group_time_limit_{run_id}",
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        loop = asyncio.get_running_loop()
        handle = loop.call_later(delay, start_expiry_task)
        self._time_limit_handles.add(handle)

    async def _expire_run_after_deadline(
        self,
        run_id: str,
        *,
        runtime_context: Any = None,
    ) -> None:
        run = await self.db.get_agent_group_run(run_id)
        if run is None:
            return
        await self._expire_if_time_limit_reached(
            run,
            runtime_context=runtime_context,
        )

    def _schedule_status_notification(
        self,
        runtime_context: Any,
        run_payload: dict[str, Any],
    ) -> None:
        if runtime_context is None or not hasattr(runtime_context, "send_message"):
            return
        task = asyncio.create_task(
            self._send_status_notification(runtime_context, run_payload),
            name=f"agent_group_notify_{run_payload.get('run_id')}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _send_status_notification(
        self,
        runtime_context: Any,
        run_payload: dict[str, Any],
    ) -> None:
        try:
            await runtime_context.send_message(
                run_payload["umo"],
                MessageChain().message(self._status_notification_text(run_payload)),
            )
        except Exception:
            return

    @staticmethod
    def _status_notification_text(run_payload: dict[str, Any]) -> str:
        run_id = run_payload.get("run_id")
        status = run_payload.get("status")
        if status == "completed":
            summary = run_payload.get("summary")
            if summary:
                return f"Agent group {run_id} completed.\n\n{summary}"
            return f"Agent group {run_id} completed."
        if status == "waiting_for_input":
            return f"Agent group {run_id} is waiting for Local Agent input."
        if status == "limit_reached":
            reason = (run_payload.get("metadata") or {}).get("limit_reason")
            suffix = f" ({reason})" if reason else ""
            return f"Agent group {run_id} reached its limit{suffix}."
        if status == "cancelled":
            return f"Agent group {run_id} was cancelled."
        if status == "failed":
            return f"Agent group {run_id} failed."
        return f"Agent group {run_id} status changed to {status}."

    def _schedule_helper_cleanup(self, run_payload: dict[str, Any]) -> None:
        helpers = (run_payload.get("metadata") or {}).get("helper_subagents") or {}
        if not helpers or self.subagent_runtime_manager is None:
            return
        task = asyncio.create_task(
            self._cleanup_helper_subagents(helpers),
            name=f"agent_group_helper_cleanup_{run_payload.get('run_id')}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _cleanup_helper_subagents(self, helpers: dict[str, Any]) -> None:
        delete_by_id = getattr(
            self.subagent_runtime_manager,
            "delete_instance_by_id",
            None,
        )
        if delete_by_id is None:
            return
        for helper in helpers.values():
            if not isinstance(helper, dict):
                continue
            instance_id = helper.get("instance_id")
            if instance_id:
                await delete_by_id(instance_id)

    def _schedule_initial_dispatch(
        self,
        event,
        run_payload: dict[str, Any],
        *,
        runtime_context: Any = None,
    ) -> None:
        if self.subagent_runtime_manager is None:
            return
        task = asyncio.create_task(
            self._dispatch_initial_recipients(
                event,
                run_payload,
                runtime_context=runtime_context,
            ),
            name=f"agent_group_dispatch_{run_payload.get('run_id')}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _schedule_member_dispatches(
        self,
        event,
        run_payload: dict[str, Any],
        member_names: list[str],
        *,
        runtime_context: Any = None,
    ) -> None:
        if event is None or self.subagent_runtime_manager is None:
            return
        recipients = list(dict.fromkeys(name for name in member_names if name))
        if not recipients:
            return
        task = asyncio.create_task(
            self._dispatch_members(
                event,
                run_payload["run_id"],
                recipients,
                runtime_context=runtime_context,
            ),
            name=f"agent_group_followup_{run_payload.get('run_id')}",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _dispatch_members(
        self,
        event,
        run_id: str,
        member_names: list[str],
        *,
        runtime_context: Any = None,
    ) -> None:
        if len(member_names) <= 1:
            for member_name in member_names:
                await self._dispatch_member(
                    event,
                    run_id,
                    member_name,
                    None,
                    runtime_context=runtime_context,
                )
            return
        await asyncio.gather(
            *(
                self._dispatch_member(
                    event,
                    run_id,
                    member_name,
                    None,
                    runtime_context=runtime_context,
                )
                for member_name in member_names
            )
        )

    async def _dispatch_initial_recipients(
        self,
        event,
        run_payload: dict[str, Any],
        *,
        runtime_context: Any = None,
    ) -> None:
        run_id = run_payload["run_id"]
        metadata = run_payload.get("metadata") or {}
        recipients = metadata.get("initial_recipients") or []
        task_text = run_payload.get("task") or ""
        if len(recipients) <= 1:
            for member_name in recipients:
                await self._dispatch_member(
                    event,
                    run_id,
                    member_name,
                    task_text,
                    runtime_context=runtime_context,
                )
            return
        await asyncio.gather(
            *(
                self._dispatch_member(
                    event,
                    run_id,
                    member_name,
                    task_text,
                    runtime_context=runtime_context,
                )
                for member_name in recipients
            )
        )

    async def _dispatch_member(
        self,
        event,
        run_id: str,
        member_name: str,
        task_text: str | None,
        *,
        runtime_context: Any = None,
    ) -> None:
        loaded = await self.db.get_agent_group_run(run_id)
        if loaded is None or self._value(loaded, "status") not in ACTIVE_RUN_STATUSES:
            return
        expired = await self._expire_if_time_limit_reached(
            loaded,
            runtime_context=runtime_context,
        )
        if expired is not None:
            return
        member = self._find_member(self._value(loaded, "members") or [], member_name)
        if member is None or not member.get("instance_name"):
            return

        message_indexes, run_payload = await self._claim_member_unread(
            run_id, member_name
        )
        if run_payload is None:
            return
        member_event = _AgentGroupMemberEventView(
            event,
            {
                "agent_group_member_context": {
                    "run_id": run_id,
                    "member_name": member_name,
                },
                "subagent_runtime_context": runtime_context,
            },
        )
        input_text = self._member_dispatch_input(
            run_payload,
            member_name,
            task_text,
            message_indexes,
        )
        result = await self.subagent_runtime_manager.run_instance(
            member_event,
            member["instance_name"],
            input_text,
            scope_type="conversation",
        )
        await self._record_member_dispatch_result(
            run_id,
            member_name,
            result,
            runtime_context=runtime_context,
        )

    async def _claim_member_unread(
        self,
        run_id: str,
        member_name: str,
    ) -> tuple[list[int], dict[str, Any] | None]:
        lock = self._run_state_locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            run = await self.db.get_agent_group_run(run_id)
            if run is None or self._value(run, "status") not in ACTIVE_RUN_STATUSES:
                return [], None
            run_payload = self._run_payload(run, include_private=True)
            metadata = dict(self._run_metadata(run))
            unread = self._normalized_unread(metadata.get("unread_by_member"))
            message_indexes = unread.pop(member_name, [])
            if not message_indexes:
                return [], run_payload

            if unread:
                metadata["unread_by_member"] = unread
            else:
                metadata.pop("unread_by_member", None)

            saved = await self._save_state(
                run,
                metadata=metadata,
                include_private=True,
            )
            if saved.ok:
                return message_indexes, saved.data
            return [], run_payload

    def _member_dispatch_input(
        self,
        run_payload: dict[str, Any],
        member_name: str,
        task_text: str | None,
        message_indexes: list[int],
    ) -> str:
        run_id = run_payload.get("run_id")
        task = task_text or run_payload.get("task") or ""
        lines = [
            f"Agent group run_id: {run_id}",
            f"Your member name: {member_name}",
            f"Task: {task}",
        ]
        if not message_indexes:
            lines.extend(
                [
                    "",
                    "Coordinate with the group and call mark_complete when your final "
                    "opinion is ready.",
                ]
            )
            return "\n".join(lines)

        messages = run_payload.get("messages") or []
        lines.extend(["", "New messages:"])
        for index in message_indexes:
            if 0 <= index < len(messages):
                lines.append(self._format_dispatch_message(messages[index]))
        lines.extend(
            [
                "",
                "Respond to the group or specific member if needed, and call "
                "mark_complete when your final opinion is ready.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_dispatch_message(message: dict[str, Any]) -> str:
        privacy = "private" if message.get("private") else "group"
        return (
            f"- [{privacy}] {message.get('from')} -> {message.get('to')}: "
            f"{message.get('content')}"
        )

    async def _record_member_dispatch_result(
        self,
        run_id: str,
        member_name: str,
        result: Any,
        *,
        runtime_context: Any = None,
    ) -> None:
        lock = self._run_state_locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            loaded = await self.db.get_agent_group_run(run_id)
            if (
                loaded is None
                or self._value(loaded, "status") not in ACTIVE_RUN_STATUSES
            ):
                return
            expired = await self._expire_if_time_limit_reached(
                loaded,
                runtime_context=runtime_context,
            )
            if expired is not None:
                return

            members = list(self._value(loaded, "members") or [])
            member = self._find_member(members, member_name)
            if member is None or member.get("status") == "completed":
                return

            messages = list(self._value(loaded, "messages") or [])
            metadata = dict(self._run_metadata(loaded))
            token_usage = dict(self._value(loaded, "token_usage") or {})
            member_usage = dict(token_usage.get("members") or {})
            status = self._value(loaded, "status")

            if getattr(result, "ok", False):
                data = getattr(result, "data", {}) or {}
                final_response = data.get("final_response")
                if final_response:
                    messages.append(
                        {
                            "from": member_name,
                            "to": "group",
                            "content": final_response,
                            "private": False,
                            "type": "member_response",
                        }
                    )
                metadata.setdefault("dispatch", {})[member_name] = "completed"
                usage = (data.get("metadata") or {}).get("token_usage")
                if isinstance(usage, int):
                    member_usage[member_name] = member_usage.get(member_name, 0) + usage
            else:
                member["status"] = "failed"
                error = getattr(result, "error", None)
                metadata.setdefault("dispatch", {})[member_name] = {
                    "error_code": getattr(error, "error_code", "dispatch_failed"),
                    "message": getattr(error, "message", "Member dispatch failed."),
                }
                status = "failed"

            token_usage["members"] = member_usage
            token_usage["total"] = self._total_token_usage(token_usage)
            token_limit = metadata.get("token_limit")
            if isinstance(token_limit, int) and token_usage["total"] >= token_limit:
                status = "limit_reached"
                metadata["limit_reason"] = "token_limit"
            await self._save_state(
                loaded,
                status=status,
                members=members,
                messages=messages,
                token_usage=token_usage,
                metadata=metadata,
                runtime_context=runtime_context,
            )

    def ensure_workspace_path(self, workspace_id: str) -> Path:
        if not _WORKSPACE_ID_RE.fullmatch(workspace_id):
            raise ValueError("Invalid workspace ID.")
        root = self.workspace_root.resolve()
        path = (self.workspace_root / workspace_id).resolve()
        if root != path and root not in path.parents:
            raise ValueError("Workspace path escapes the agent group workspace root.")
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def _resolve_workspace_id(
        self,
        event,
        preset: AgentGroupPreset,
        workspace_id: str | None,
    ) -> str:
        _ = preset
        workspace_id = (workspace_id or "").strip()
        if workspace_id:
            return workspace_id
        conversation_id = await self._resolve_conversation_id(event)
        return f"conversation-{conversation_id}"

    async def _resolve_conversation_id(self, event) -> str:
        umo = self._value(event, "unified_msg_origin")
        conversation_id = await self._maybe_await(
            self.conversation_manager.get_curr_conversation_id(umo)
        )
        if not conversation_id:
            conversation_id = await self._maybe_await(
                self.conversation_manager.new_conversation(
                    umo,
                    event.get_platform_id(),
                )
            )
        return conversation_id

    def _member_state(self, member: AgentGroupMemberPreset) -> dict[str, Any]:
        return {
            "name": member.name,
            "source_type": member.source_type,
            "subagent_preset": member.subagent_preset,
            "persona_id": member.persona_id,
            "status": "active",
            "instance_name": None,
            "instance_id": None,
        }

    async def _load_helper(
        self,
        run_id: str,
        from_member: str,
        helper_name: str,
        actor_member: str | None,
    ) -> AgentGroupRuntimeResult:
        if actor_member and actor_member != from_member:
            return self._member_impersonation_result(actor_member, from_member)
        loaded = await self._load_mutable_run(run_id)
        if not loaded.ok:
            return loaded
        run = loaded.data
        members = list(self._value(run, "members") or [])
        if self._find_member(members, from_member) is None:
            return self._member_missing_result(from_member)
        helpers = self._helper_subagents(self._run_metadata(run))
        helper_key = self._helper_key(from_member, helper_name)
        helper = helpers.get(helper_key)
        if helper is None:
            return AgentGroupRuntimeResult.failure(
                HELPER_SUBAGENT_NOT_FOUND,
                "Helper SubAgent was not found for this member.",
                {"helper_name": helper_name},
            )
        return AgentGroupRuntimeResult.success({"run": run, "helper": helper})

    def _helper_overrides(
        self,
        run_id: str,
        creator_member: str,
        creator: dict[str, Any],
        preset_name: str,
    ) -> dict[str, Any]:
        creator_tools = self._member_state_tools(creator)
        creator_skills = self._member_state_skills(creator)
        helper_tools = self._subagent_preset_tools(preset_name)
        helper_skills = self._subagent_preset_skills(preset_name)
        overrides = {
            "system_prompt_delta": (
                f"You are a temporary helper SubAgent for member `{creator_member}` "
                f"in agent group run `{run_id}`. Assist only that member and stay "
                "within the provided task context."
            )
        }
        narrowed_tools = self._narrow_capabilities(helper_tools, creator_tools)
        if narrowed_tools is not None:
            overrides["tools"] = narrowed_tools
        narrowed_skills = self._narrow_capabilities(helper_skills, creator_skills)
        if narrowed_skills is not None:
            overrides["skills"] = narrowed_skills
        return overrides

    @staticmethod
    def _narrow_capabilities(
        requested: list[str] | None,
        ceiling: list[str] | None,
    ) -> list[str] | None:
        if ceiling is None:
            return None if requested is None else list(requested)
        if requested is None:
            return list(ceiling)
        allowed = set(ceiling)
        return [name for name in requested if name in allowed]

    @staticmethod
    def _helper_input(
        run_id: str,
        creator_member: str,
        helper_name: str,
        input_text: str,
    ) -> str:
        return (
            f"Agent group run_id: {run_id}\n"
            f"Creator member: {creator_member}\n"
            f"Helper name: {helper_name}\n\n"
            f"{input_text}"
        )

    @staticmethod
    def _valid_helper_name(helper_name: str) -> bool:
        return bool(_HELPER_NAME_RE.fullmatch(str(helper_name or "")))

    @staticmethod
    def _helper_key(member_name: str, helper_name: str) -> str:
        return f"{member_name}:{helper_name}"

    @staticmethod
    def _helper_instance_name(
        run_id: str,
        member_name: str,
        helper_name: str,
    ) -> str:
        return f"agent_group_{run_id}_helper_{member_name}_{helper_name}"

    @staticmethod
    def _helper_subagents(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
        helpers = metadata.get("helper_subagents")
        if not isinstance(helpers, dict):
            return {}
        return {
            str(key): dict(value)
            for key, value in helpers.items()
            if isinstance(value, dict)
        }

    @staticmethod
    def _member_prompt_delta(
        preset: AgentGroupPreset,
        member: AgentGroupMemberPreset,
        run_id: str,
    ) -> str:
        parts = [
            f"You are member `{member.name}` in agent group run `{run_id}`.",
            "Use the agent group tools to communicate, and call mark_complete when your final opinion is ready.",
        ]
        if preset.collaboration_prompt:
            parts.append(f"Collaboration prompt: {preset.collaboration_prompt}")
        if preset.principles:
            parts.append(
                "Principles:\n" + "\n".join(f"- {p}" for p in preset.principles)
            )
        return "\n\n".join(parts)

    def _member_tools(self, member: AgentGroupMemberPreset) -> list[str] | None:
        base_tools = self._member_source_tools(member)
        if base_tools is None:
            return None
        tools = list(base_tools or [])
        for tool_name in MEMBER_TOOL_NAMES:
            if tool_name not in tools:
                tools.append(tool_name)
        return tools

    def _member_source_tools(self, member: AgentGroupMemberPreset) -> list[str] | None:
        if member.source_type == "persona":
            return self._persona_tools(member.persona_id)
        return self._subagent_preset_tools(member.subagent_preset)

    def _member_state_tools(self, member: dict[str, Any]) -> list[str] | None:
        if member.get("source_type") == "persona":
            return self._persona_tools(str(member.get("persona_id") or ""))
        return self._subagent_preset_tools(str(member.get("subagent_preset") or ""))

    def _member_state_skills(self, member: dict[str, Any]) -> list[str] | None:
        if member.get("source_type") == "persona":
            return self._persona_skills(str(member.get("persona_id") or ""))
        return self._subagent_preset_skills(str(member.get("subagent_preset") or ""))

    def _subagent_preset_tools(self, preset_name: str) -> list[str] | None:
        subagent_preset = None
        presets = getattr(self.subagent_runtime_manager, "presets", {})
        if isinstance(presets, dict):
            subagent_preset = presets.get(preset_name)
        base_tools = self._value(subagent_preset, "tools")
        if base_tools is None:
            return None
        return [str(tool) for tool in base_tools if tool]

    def _subagent_preset_skills(self, preset_name: str) -> list[str] | None:
        subagent_preset = None
        presets = getattr(self.subagent_runtime_manager, "presets", {})
        if isinstance(presets, dict):
            subagent_preset = presets.get(preset_name)
        base_skills = self._value(subagent_preset, "skills")
        if base_skills is None:
            return None
        return [str(skill) for skill in base_skills if skill]

    def _persona_tools(self, persona_id: str) -> list[str] | None:
        persona = self._persona(persona_id)
        tools = self._value(persona, "tools")
        if tools is None:
            return None
        return [str(tool) for tool in tools if tool]

    def _persona_skills(self, persona_id: str) -> list[str] | None:
        persona = self._persona(persona_id)
        skills = self._value(persona, "skills")
        if skills is None:
            return None
        return [str(skill) for skill in skills if skill]

    def _persona(self, persona_id: str) -> Any:
        persona_mgr = getattr(self.subagent_runtime_manager, "persona_mgr", None)
        if persona_mgr is None or not persona_id:
            return None
        getter = getattr(persona_mgr, "get_persona_v3_by_id", None)
        if getter is None:
            return None
        return getter(persona_id)

    def _all_active_runtime_tool_names(self) -> list[str]:
        tool_mgr = getattr(self.subagent_runtime_manager, "tool_mgr", None)
        tools = getattr(tool_mgr, "func_list", []) if tool_mgr is not None else []
        names = []
        for tool in tools:
            name = getattr(tool, "name", None)
            if name and getattr(tool, "active", True) and name not in names:
                names.append(name)
        return names

    def _all_active_runtime_skill_names(self) -> list[str]:
        skill_manager = getattr(self.subagent_runtime_manager, "skill_manager", None)
        if skill_manager is None:
            return []
        skills = skill_manager.list_skills(active_only=True)
        names = []
        for skill in skills:
            name = getattr(skill, "name", None)
            if name and name not in names:
                names.append(name)
        return names

    async def _execute_summary(
        self,
        event,
        run,
        final_opinions: dict[str, str],
        *,
        runtime_context: Any = None,
    ) -> dict[str, Any]:
        fallback = self._fallback_summary(final_opinions)
        if event is None or self.subagent_runtime_manager is None:
            return {"summary": fallback}

        run_id = self._value(run, "run_id")
        metadata = self._run_metadata(run)
        summary_preset = metadata.get("summary_preset") or DEFAULT_SUMMARY_PRESET
        instance_name = f"agent_group_{run_id}_summary"
        create_result = await self.subagent_runtime_manager.create_instance(
            event,
            instance_name,
            summary_preset,
            scope_type="conversation",
            overrides={
                "system_prompt_delta": self._summary_prompt_delta(run_id),
                "tools": [],
                "skills": [],
            },
        )
        if not getattr(create_result, "ok", False):
            return {
                "summary": fallback,
                "metadata": {
                    "summary_error": self._result_error_payload(create_result),
                },
            }

        summary_event = _AgentGroupMemberEventView(
            event,
            {"subagent_runtime_context": runtime_context},
        )
        run_result = await self.subagent_runtime_manager.run_instance(
            summary_event,
            instance_name,
            self._summary_input(run, final_opinions),
            scope_type="conversation",
        )
        if not getattr(run_result, "ok", False):
            return {
                "summary": fallback,
                "metadata": {
                    "summary_error": self._result_error_payload(run_result),
                },
            }

        data = getattr(run_result, "data", {}) or {}
        summary = data.get("final_response") or fallback
        usage = (data.get("metadata") or {}).get("token_usage")
        result = {
            "summary": summary,
            "metadata": {
                "summary_instance": instance_name,
                "summary_preset": summary_preset,
            },
        }
        if isinstance(usage, int):
            result["token_usage"] = usage
        return result

    @staticmethod
    def _total_token_usage(token_usage: dict[str, Any]) -> int:
        total = 0
        member_usage = token_usage.get("members") or {}
        if isinstance(member_usage, dict):
            total += sum(
                value for value in member_usage.values() if isinstance(value, int)
            )
        summary_usage = token_usage.get("summary")
        if isinstance(summary_usage, int):
            total += summary_usage
        return total

    @staticmethod
    def _fallback_summary(final_opinions: dict[str, str]) -> str:
        if not final_opinions:
            return ""
        return "\n".join(
            f"{member}: {opinion}" for member, opinion in final_opinions.items()
        )

    @staticmethod
    def _summary_prompt_delta(run_id: str) -> str:
        return (
            f"You are the Summary SubAgent for agent group run `{run_id}`. "
            "Produce a concise final result for the Local Agent. Use only the "
            "provided transcript and final opinions."
        )

    def _summary_input(self, run, final_opinions: dict[str, str]) -> str:
        metadata = self._run_metadata(run)
        include_private = bool(metadata.get("summary_include_private", False))
        lines = [
            f"Agent group run_id: {self._value(run, 'run_id')}",
            f"Task: {self._value(run, 'task')}",
            "",
            "Transcript:",
        ]
        for message in self._value(run, "messages") or []:
            if message.get("private") and not include_private:
                continue
            lines.append(
                f"- {message.get('from')} -> {message.get('to')}: {message.get('content')}"
            )
        lines.extend(["", "Final opinions:"])
        lines.extend(
            f"- {member}: {opinion}" for member, opinion in final_opinions.items()
        )
        return "\n".join(lines)

    @staticmethod
    def _result_error_payload(result: Any) -> dict[str, Any]:
        error = getattr(result, "error", None)
        return {
            "error_code": getattr(error, "error_code", "summary_failed"),
            "message": getattr(error, "message", "Summary SubAgent failed."),
            "details": getattr(error, "details", None),
        }

    @classmethod
    def _subagent_runtime_failure(cls, result: Any) -> AgentGroupRuntimeResult:
        error = getattr(result, "error", None)
        return AgentGroupRuntimeResult.failure(
            getattr(error, "error_code", "subagent_runtime_failed"),
            getattr(error, "message", "SubAgent runtime operation failed."),
            getattr(error, "details", None),
        )

    def _run_payload(self, run, *, include_private: bool = False) -> dict[str, Any]:
        messages = self._value(run, "messages") or []
        if not include_private:
            messages = [
                message
                for message in messages
                if not isinstance(message, dict) or not message.get("private")
            ]
        return {
            "run_id": self._value(run, "run_id"),
            "umo": self._value(run, "umo"),
            "conversation_id": self._value(run, "conversation_id"),
            "workspace_id": self._value(run, "workspace_id"),
            "preset_name": self._value(run, "preset_name"),
            "task": self._value(run, "task"),
            "status": self._value(run, "status"),
            "members": self._json_safe(self._value(run, "members") or []),
            "messages": self._json_safe(messages),
            "final_opinions": self._json_safe(self._value(run, "final_opinions") or {}),
            "summary": self._value(run, "summary"),
            "token_usage": self._json_safe(self._value(run, "token_usage") or {}),
            "metadata": self._json_safe(self._run_metadata(run)),
            "version": self._value(run, "version"),
        }

    @staticmethod
    def _find_member(members: list[dict], member_name: str) -> dict | None:
        return next(
            (member for member in members if member.get("name") == member_name),
            None,
        )

    @classmethod
    def _member_exists(cls, members: list[dict], member_name: str) -> bool:
        return (
            member_name == "local_agent"
            or cls._find_member(members, member_name) is not None
        )

    @staticmethod
    def _all_members_completed(members: list[dict]) -> bool:
        return bool(members) and all(
            member.get("status") == "completed" for member in members
        )

    @staticmethod
    def _active_member_names(
        members: list[dict],
        *,
        exclude: set[str] | None = None,
    ) -> list[str]:
        excluded = exclude or set()
        return [
            member.get("name")
            for member in members
            if member.get("name")
            and member.get("name") not in excluded
            and member.get("status") not in {"completed", "failed"}
        ]

    @classmethod
    def _mark_messages_unread(
        cls,
        metadata: dict[str, Any],
        recipients: list[str],
        message_indexes: list[int],
    ) -> None:
        if not recipients or not message_indexes:
            return
        unread = cls._normalized_unread(metadata.get("unread_by_member"))
        for recipient in recipients:
            recipient_unread = unread.setdefault(recipient, [])
            for message_index in message_indexes:
                if message_index not in recipient_unread:
                    recipient_unread.append(message_index)
        metadata["unread_by_member"] = unread

    @staticmethod
    def _normalized_unread(value: Any) -> dict[str, list[int]]:
        if not isinstance(value, dict):
            return {}
        unread: dict[str, list[int]] = {}
        for member_name, indexes in value.items():
            if not isinstance(indexes, list):
                continue
            normalized = []
            for index in indexes:
                try:
                    message_index = int(index)
                except (TypeError, ValueError):
                    continue
                if message_index >= 0 and message_index not in normalized:
                    normalized.append(message_index)
            if normalized:
                unread[str(member_name)] = normalized
        return unread

    @staticmethod
    def _member_missing_result(member_name: str) -> AgentGroupRuntimeResult:
        return AgentGroupRuntimeResult.failure(
            MEMBER_NOT_FOUND,
            "Agent group member was not found.",
            {"member_name": member_name},
        )

    @staticmethod
    def _member_impersonation_result(
        actor_member: str,
        requested_member: str,
    ) -> AgentGroupRuntimeResult:
        return AgentGroupRuntimeResult.failure(
            MEMBER_IMPERSONATION,
            "Agent group member tool call does not match the calling member.",
            {
                "actor_member": actor_member,
                "requested_member": requested_member,
            },
        )

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if item is not None]

    @classmethod
    def _optional_string_list(cls, raw: dict, key: str) -> list[str] | None:
        if key not in raw:
            return None
        return cls._string_list(raw.get(key))

    @classmethod
    def _optional_non_empty_string_list(cls, raw: dict, key: str) -> list[str] | None:
        values = cls._optional_string_list(raw, key)
        return values or None

    @staticmethod
    def _positive_int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _value(obj: Any, key: str) -> Any:
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    @classmethod
    def _run_metadata(cls, run) -> dict:
        result = cls._value(run, "metadata_json") or cls._value(run, "metadata")
        if isinstance(result, dict):
            return result
        return {}

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._json_safe(val) for key, val in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(item) for item in value]
        if hasattr(value, "model_dump"):
            return cls._json_safe(value.model_dump())
        return value

    @staticmethod
    async def _maybe_await(value):
        if inspect.isawaitable(value):
            return await value
        return value
