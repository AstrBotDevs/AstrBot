import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.agent_group_runtime import (
    MEMBER_TOOL_NAMES,
    MEMBER_NOT_FOUND,
    PRESET_NOT_FOUND,
    RUN_EXISTS,
    RUN_NOT_FOUND,
    AgentGroupRuntimeManager,
)


class FakeDB:
    def __init__(self):
        self.runs = {}
        self.created_runs = []
        self.saved_states = []

    async def create_agent_group_run(self, **kwargs):
        run = SimpleNamespace(run_id=f"run-{len(self.runs) + 1}", version=1, **kwargs)
        self.runs[run.run_id] = run
        self.created_runs.append(run)
        return run

    async def get_agent_group_run(self, run_id):
        return self.runs.get(run_id)

    async def get_active_agent_group_run_for_workspace(self, workspace_id):
        for run in self.runs.values():
            if run.workspace_id == workspace_id and run.status in {
                "active",
                "waiting_for_input",
            }:
                return run
        return None

    async def list_agent_group_runs(
        self,
        *,
        umo=None,
        workspace_id=None,
        status=None,
    ):
        runs = list(self.runs.values())
        if umo is not None:
            runs = [run for run in runs if run.umo == umo]
        if workspace_id is not None:
            runs = [run for run in runs if run.workspace_id == workspace_id]
        if status is not None:
            runs = [run for run in runs if run.status == status]
        return runs

    async def save_agent_group_state(
        self,
        run_id,
        *,
        status,
        members,
        messages,
        final_opinions,
        summary,
        token_usage,
        metadata,
        expected_version,
    ):
        run = self.runs.get(run_id)
        if run is None or run.version != expected_version:
            return None
        run.status = status
        run.members = members
        run.messages = messages
        run.final_opinions = final_opinions
        run.summary = summary
        run.token_usage = token_usage
        run.metadata = metadata
        run.version += 1
        self.saved_states.append((run_id, status, expected_version))
        return run


class SlowConflictDB(FakeDB):
    async def get_active_agent_group_run_for_workspace(self, workspace_id):
        await asyncio.sleep(0)
        return await super().get_active_agent_group_run_for_workspace(workspace_id)

    async def create_agent_group_run(self, **kwargs):
        await asyncio.sleep(0)
        return await super().create_agent_group_run(**kwargs)


class CopyingFakeDB(FakeDB):
    @staticmethod
    def _copy_run(run):
        if run is None:
            return None
        return SimpleNamespace(**deepcopy(vars(run)))

    async def create_agent_group_run(self, **kwargs):
        run = await super().create_agent_group_run(**kwargs)
        return self._copy_run(run)

    async def get_agent_group_run(self, run_id):
        return self._copy_run(await super().get_agent_group_run(run_id))

    async def get_active_agent_group_run_for_workspace(self, workspace_id):
        return self._copy_run(
            await super().get_active_agent_group_run_for_workspace(workspace_id)
        )

    async def list_agent_group_runs(
        self,
        *,
        umo=None,
        workspace_id=None,
        status=None,
    ):
        return [
            self._copy_run(run)
            for run in await super().list_agent_group_runs(
                umo=umo,
                workspace_id=workspace_id,
                status=status,
            )
        ]

    async def save_agent_group_state(self, *args, **kwargs):
        await asyncio.sleep(0)
        return self._copy_run(await super().save_agent_group_state(*args, **kwargs))


class FakeConversationManager:
    def __init__(self):
        self.current = {}

    def get_curr_conversation_id(self, umo):
        return self.current.get(umo)

    def new_conversation(self, umo, platform_id):
        conversation_id = "conversation-1"
        self.current[umo] = conversation_id
        return conversation_id


class FakeSubAgentRuntime:
    runtime_enabled = True

    def __init__(self):
        self.created_instances = []
        self.created_persona_instances = []
        self.run_calls = []
        self.reset_calls = []
        self.delete_calls = []
        self.deleted_instance_ids = []
        self.presets = {
            "planner_preset": SimpleNamespace(
                tools=["base_search"],
                skills=["planning"],
            ),
            "reviewer_preset": SimpleNamespace(tools=["review_tool"], skills=[]),
            "all_tools_preset": SimpleNamespace(tools=None, skills=None),
            "agent_group_summary": SimpleNamespace(tools=[], skills=[]),
        }

    async def create_instance(
        self, event, name, preset_name, scope_type=None, overrides=None
    ):
        self.created_instances.append(
            {
                "event": event,
                "name": name,
                "preset_name": preset_name,
                "scope_type": scope_type,
                "overrides": overrides or {},
            }
        )
        return SimpleNamespace(ok=True, data=SimpleNamespace(instance_id=f"{name}-id"))

    async def create_instance_from_persona(
        self,
        event,
        name,
        persona_id,
        scope_type=None,
        overrides=None,
    ):
        self.created_persona_instances.append(
            {
                "event": event,
                "name": name,
                "persona_id": persona_id,
                "scope_type": scope_type,
                "overrides": overrides or {},
            }
        )
        return SimpleNamespace(ok=True, data=SimpleNamespace(instance_id=f"{name}-id"))

    async def run_instance(
        self,
        event,
        name,
        input_text,
        scope_type=None,
    ):
        self.run_calls.append(
            {
                "event": event,
                "name": name,
                "input_text": input_text,
                "scope_type": scope_type,
            }
        )
        return SimpleNamespace(
            ok=True,
            data={
                "final_response": f"{name} acknowledged",
                "metadata": {"token_usage": 5},
            },
        )

    async def reset_instance(self, event, name, scope_type=None):
        self.reset_calls.append(
            {"event": event, "name": name, "scope_type": scope_type}
        )
        return SimpleNamespace(ok=True, data=SimpleNamespace(name=name))

    async def delete_instance(self, event, name, scope_type=None):
        self.delete_calls.append(
            {"event": event, "name": name, "scope_type": scope_type}
        )
        return SimpleNamespace(ok=True, data=SimpleNamespace(name=name))

    async def delete_instance_by_id(self, instance_id):
        self.deleted_instance_ids.append(instance_id)
        return SimpleNamespace(ok=True, data={"instance_id": instance_id})


class FailingSubAgentRuntime(FakeSubAgentRuntime):
    async def run_instance(
        self,
        event,
        name,
        input_text,
        scope_type=None,
    ):
        self.run_calls.append(
            {
                "event": event,
                "name": name,
                "input_text": input_text,
                "scope_type": scope_type,
            }
        )
        return SimpleNamespace(
            ok=False,
            error=SimpleNamespace(
                error_code="dispatch_failed",
                message="dispatch failed",
                details=None,
            ),
        )


class BlockingSubAgentRuntime(FakeSubAgentRuntime):
    def __init__(self):
        super().__init__()
        self.release = asyncio.Event()
        self.started_two = asyncio.Event()
        self.running = 0
        self.max_running = 0

    async def run_instance(
        self,
        event,
        name,
        input_text,
        scope_type=None,
    ):
        self.run_calls.append(
            {
                "event": event,
                "name": name,
                "input_text": input_text,
                "scope_type": scope_type,
            }
        )
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        if len(self.run_calls) >= 2:
            self.started_two.set()
        try:
            await self.release.wait()
        finally:
            self.running -= 1
        return SimpleNamespace(
            ok=True,
            data={
                "final_response": f"{name} acknowledged",
                "metadata": {"token_usage": 5},
            },
        )


class FakeEvent:
    unified_msg_origin = "webchat:FriendMessage:user"

    def get_platform_id(self):
        return "webchat"


class FakeRuntimeContext:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, session, message_chain):
        self.sent_messages.append((session, message_chain))
        return True


def manager(config=None, *, db=None, subagent_runtime=None):
    return AgentGroupRuntimeManager(
        db or FakeDB(),
        subagent_runtime or FakeSubAgentRuntime(),
        FakeConversationManager(),
        config=config,
    )


def enabled_config():
    return {
        "presets": [
            {
                "name": "review_team",
                "enabled": True,
                "members": [
                    {
                        "name": "planner",
                        "source_type": "subagent",
                        "subagent_preset": "planner_preset",
                        "role": "Plan work",
                        "tools": ["base_search", "search"],
                        "skills": ["planning", "outside_skill"],
                    },
                    {
                        "name": "disabled_member",
                        "subagent_preset": "writer_preset",
                        "enabled": False,
                    },
                    {
                        "name": "reviewer",
                        "source_type": "persona",
                        "persona_id": "review_persona",
                    },
                ],
                "initial_recipients": ["planner"],
                "principles": ["Be concise"],
                "collaboration_prompt": "Coordinate in the group chat.",
                "summary_include_private": True,
                "token_limit": 1200,
                "time_limit_seconds": 300,
            },
            {
                "name": "disabled_team",
                "enabled": False,
                "members": [],
            },
        ]
    }


def test_reload_from_config_normalizes_enabled_presets_and_members():
    runtime = manager(enabled_config())

    presets = runtime.list_presets()

    assert [preset.name for preset in presets] == ["review_team"]
    preset = presets[0]
    assert [member.name for member in preset.members] == ["planner", "reviewer"]
    assert [
        (
            member.name,
            member.source_type,
            member.subagent_preset,
            member.persona_id,
        )
        for member in preset.members
    ] == [
        ("planner", "subagent", "planner_preset", ""),
        ("reviewer", "persona", "", "review_persona"),
    ]
    assert not hasattr(preset, "workspace_id")
    assert not hasattr(preset.members[0], "role")
    assert not hasattr(preset.members[0], "tools")
    assert not hasattr(preset.members[0], "skills")
    assert preset.initial_recipients == ["planner"]
    assert preset.principles == ["Be concise"]
    assert preset.summary_include_private is True


def test_default_config_registers_agent_group_summary_preset():
    summary_agents = [
        agent
        for agent in DEFAULT_CONFIG["subagent_orchestrator"]["agents"]
        if agent.get("name") == "agent_group_summary"
    ]

    assert DEFAULT_CONFIG["agent_group"]["summary_preset"] == "agent_group_summary"
    assert len(summary_agents) == 1
    assert summary_agents[0]["runtime_mode"] == "persistent"
    assert summary_agents[0]["tools"] == []
    assert summary_agents[0]["skills"] == []


@pytest.mark.asyncio
async def test_start_run_creates_persistent_member_instances_and_run_record(tmp_path):
    subagent_runtime = FakeSubAgentRuntime()
    runtime = manager(enabled_config(), subagent_runtime=subagent_runtime)
    runtime.workspace_root = tmp_path

    result = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review this patch",
        workspace_id="code-review",
    )

    assert result.ok is True
    assert result.data["run_id"] == "run-1"
    assert result.data["status"] == "active"
    assert result.data["workspace_id"] == "code-review"
    assert (tmp_path / "code-review").is_dir()
    assert [call["preset_name"] for call in subagent_runtime.created_instances] == [
        "planner_preset",
    ]
    assert [
        call["persona_id"] for call in subagent_runtime.created_persona_instances
    ] == ["review_persona"]
    assert subagent_runtime.created_instances[0]["overrides"]["tools"] == [
        "base_search",
        *MEMBER_TOOL_NAMES,
    ]
    assert "skills" not in subagent_runtime.created_instances[0]["overrides"]
    assert "Plan work" not in subagent_runtime.created_instances[0]["overrides"][
        "system_prompt_delta"
    ]
    assert runtime.db.created_runs[0].members[0]["source_type"] == "subagent"
    assert runtime.db.created_runs[0].members[0]["subagent_preset"] == "planner_preset"
    assert "role" not in runtime.db.created_runs[0].members[0]
    assert runtime.db.created_runs[0].members[1]["source_type"] == "persona"
    assert runtime.db.created_runs[0].members[1]["persona_id"] == "review_persona"
    assert runtime.db.created_runs[0].messages[0]["content"] == "Review this patch"
    assert not hasattr(runtime.db.created_runs[0], "runtime_context")
    assert runtime.db.created_runs[0].metadata["started_at_epoch"] > 0
    assert runtime.db.created_runs[0].metadata["deadline_at_epoch"] > (
        runtime.db.created_runs[0].metadata["started_at_epoch"]
    )
    await asyncio.sleep(0)
    assert subagent_runtime.run_calls[0]["name"] == "agent_group_run-1_planner"
    assert subagent_runtime.run_calls[0]["event"].get_extra(
        "agent_group_member_context"
    ) == {"run_id": "run-1", "member_name": "planner"}


@pytest.mark.asyncio
async def test_start_run_preserves_all_tools_subagent_preset_capabilities():
    config = enabled_config()
    planner = config["presets"][0]["members"][0]
    planner["subagent_preset"] = "all_tools_preset"
    planner.pop("tools", None)
    planner.pop("skills", None)
    subagent_runtime = FakeSubAgentRuntime()
    runtime = manager(config, subagent_runtime=subagent_runtime)

    result = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    assert result.ok is True
    assert "tools" not in subagent_runtime.created_instances[0]["overrides"]
    assert "skills" not in subagent_runtime.created_instances[0]["overrides"]


@pytest.mark.asyncio
async def test_start_run_ignores_legacy_preset_workspace_and_uses_conversation_fallback():
    config = enabled_config()
    config["presets"][0]["workspace_id"] = "legacy-workspace"
    runtime = manager(config)

    result = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Task",
        dispatch_initial=False,
    )

    assert result.ok is True
    assert result.data["workspace_id"] == "conversation-conversation-1"


@pytest.mark.asyncio
async def test_start_run_rejects_missing_preset_and_active_workspace_conflict():
    runtime = manager(enabled_config())

    missing = await runtime.start_run(FakeEvent(), "missing", "Task")
    created = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Task one",
        dispatch_initial=False,
    )
    duplicate = await runtime.start_run(FakeEvent(), "review_team", "Task two")

    assert missing.ok is False
    assert missing.error.error_code == PRESET_NOT_FOUND
    assert created.ok is True
    assert duplicate.ok is False
    assert duplicate.error.error_code == RUN_EXISTS


@pytest.mark.asyncio
async def test_list_runs_returns_filtered_run_payloads():
    runtime = manager(enabled_config())
    first = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Task one",
        workspace_id="code-review",
        dispatch_initial=False,
    )
    await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Task two",
        workspace_id="other-workspace",
        dispatch_initial=False,
    )

    listed = await runtime.list_runs(workspace_id="code-review")

    assert listed.ok is True
    assert [run["run_id"] for run in listed.data["runs"]] == [first.data["run_id"]]
    assert listed.data["runs"][0]["workspace_id"] == "code-review"


@pytest.mark.asyncio
async def test_start_run_serializes_active_workspace_check():
    runtime = manager(enabled_config(), db=SlowConflictDB())

    first, second = await asyncio.gather(
        runtime.start_run(
            FakeEvent(),
            "review_team",
            "Task one",
            dispatch_initial=False,
        ),
        runtime.start_run(
            FakeEvent(),
            "review_team",
            "Task two",
            dispatch_initial=False,
        ),
    )

    assert [first.ok, second.ok].count(True) == 1
    failed = second if first.ok else first
    assert failed.error.error_code == RUN_EXISTS


@pytest.mark.asyncio
async def test_workspace_write_lock_serializes_member_write_operations(tmp_path):
    runtime = manager(enabled_config())
    runtime.workspace_root = tmp_path
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    first = await runtime.acquire_workspace_write_lock(
        started.data["run_id"],
        "planner",
    )
    second_task = asyncio.create_task(
        runtime.acquire_workspace_write_lock(
            started.data["run_id"],
            "reviewer",
        )
    )
    await asyncio.sleep(0)

    assert first.ok is True
    assert second_task.done() is False

    await first.data.release()
    second = await asyncio.wait_for(second_task, timeout=1)

    assert second.ok is True
    await second.data.release()


@pytest.mark.asyncio
async def test_workspace_file_write_conflicts_when_file_changed_after_member_read(
    tmp_path,
):
    runtime = manager(enabled_config())
    runtime.workspace_root = tmp_path
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )
    target = Path(started.data["metadata"]["workspace_path"]) / "notes.txt"
    target.write_text("initial", encoding="utf-8")
    read = await runtime.record_workspace_file_read(
        started.data["run_id"],
        "planner",
        str(target),
    )
    target.write_text("changed elsewhere", encoding="utf-8")

    write = await runtime.acquire_workspace_write_lock(
        started.data["run_id"],
        "planner",
        paths=[str(target)],
    )

    assert read.ok is True
    assert write.ok is False
    assert write.error.error_code == "version_conflict"
    assert write.error.details["path"] == "notes.txt"


@pytest.mark.asyncio
async def test_workspace_file_write_allows_reread_current_version(tmp_path):
    runtime = manager(enabled_config())
    runtime.workspace_root = tmp_path
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )
    target = Path(started.data["metadata"]["workspace_path"]) / "notes.txt"
    target.write_text("current", encoding="utf-8")
    read = await runtime.record_workspace_file_read(
        started.data["run_id"],
        "planner",
        str(target),
    )

    write = await runtime.acquire_workspace_write_lock(
        started.data["run_id"],
        "planner",
        paths=[str(target)],
    )

    assert read.ok is True
    assert write.ok is True
    await write.data.release()


@pytest.mark.asyncio
async def test_dispatch_records_token_usage_and_marks_limit_reached():
    config = enabled_config()
    config["presets"][0]["token_limit"] = 5
    runtime = manager(config)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    await runtime._dispatch_member(
        FakeEvent(),
        started.data["run_id"],
        "planner",
        "Review",
    )
    status = await runtime.get_status(run_id=started.data["run_id"])

    assert status.ok is True
    assert status.data["status"] == "limit_reached"
    assert status.data["token_usage"] == {"members": {"planner": 5}, "total": 5}
    assert status.data["metadata"]["limit_reason"] == "token_limit"


@pytest.mark.asyncio
async def test_get_status_expires_active_run_after_time_limit():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )
    run = runtime.db.runs[started.data["run_id"]]
    run.metadata["deadline_at_epoch"] = 0

    status = await runtime.get_status(run_id=started.data["run_id"])

    assert status.ok is True
    assert status.data["status"] == "limit_reached"
    assert status.data["metadata"]["limit_reason"] == "time_limit"


@pytest.mark.asyncio
async def test_start_run_ignores_expired_workspace_run():
    runtime = manager(enabled_config())
    first = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Old review",
        dispatch_initial=False,
    )
    runtime.db.runs[first.data["run_id"]].metadata["deadline_at_epoch"] = 0

    second = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "New review",
        dispatch_initial=False,
    )

    assert second.ok is True
    assert second.data["run_id"] == "run-2"
    assert runtime.db.runs[first.data["run_id"]].status == "limit_reached"


@pytest.mark.asyncio
async def test_completed_run_sends_status_notification():
    runtime = manager(enabled_config())
    runtime_context = FakeRuntimeContext()
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
        runtime_context=runtime_context,
    )

    await runtime.mark_complete(
        started.data["run_id"],
        "planner",
        "Plan done",
        event=FakeEvent(),
        runtime_context=runtime_context,
    )
    await runtime.mark_complete(
        started.data["run_id"],
        "reviewer",
        "Looks good",
        event=FakeEvent(),
        runtime_context=runtime_context,
    )
    await asyncio.sleep(0)

    assert len(runtime_context.sent_messages) == 1
    session, message_chain = runtime_context.sent_messages[0]
    assert session == FakeEvent.unified_msg_origin
    assert "completed" in message_chain.chain[0].text
    assert started.data["run_id"] in message_chain.chain[0].text


@pytest.mark.asyncio
async def test_waiting_cancelled_failed_and_time_limit_transitions_notify():
    runtime_context = FakeRuntimeContext()
    runtime = manager(enabled_config(), subagent_runtime=FailingSubAgentRuntime())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
        runtime_context=runtime_context,
    )

    waiting = await runtime.ask_local_agent(
        started.data["run_id"],
        from_member="planner",
        question="Need input",
        runtime_context=runtime_context,
    )
    cancelled = await runtime.cancel_run(
        started.data["run_id"],
        runtime_context=runtime_context,
    )
    second = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review again",
        workspace_id="other-workspace",
        dispatch_initial=False,
        runtime_context=runtime_context,
    )
    await runtime._dispatch_member(
        FakeEvent(),
        second.data["run_id"],
        "planner",
        "Review again",
        runtime_context=runtime_context,
    )
    third = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review before timeout",
        workspace_id="timeout-workspace",
        dispatch_initial=False,
        runtime_context=runtime_context,
    )
    run = runtime.db.runs[third.data["run_id"]]
    run.metadata["deadline_at_epoch"] = 0
    await runtime._expire_run_after_deadline(
        third.data["run_id"],
        runtime_context=runtime_context,
    )
    await asyncio.sleep(0)

    assert waiting.ok is True
    assert cancelled.ok is True
    texts = [chain.chain[0].text for _, chain in runtime_context.sent_messages]
    assert any("waiting for Local Agent input" in text for text in texts)
    assert any("cancelled" in text for text in texts)
    assert any("failed" in text for text in texts)
    assert any("time_limit" in text for text in texts)


@pytest.mark.asyncio
async def test_member_creates_runs_resets_and_deletes_group_helper_subagent():
    subagent_runtime = FakeSubAgentRuntime()
    runtime = manager(enabled_config(), subagent_runtime=subagent_runtime)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    created = await runtime.create_helper_subagent(
        started.data["run_id"],
        from_member="planner",
        helper_name="analysis",
        preset_name="all_tools_preset",
        actor_member="planner",
        event=FakeEvent(),
    )
    ran = await runtime.run_helper_subagent(
        started.data["run_id"],
        from_member="planner",
        helper_name="analysis",
        input_text="Check the implementation",
        actor_member="planner",
        event=FakeEvent(),
    )
    reset = await runtime.reset_helper_subagent(
        started.data["run_id"],
        from_member="planner",
        helper_name="analysis",
        actor_member="planner",
        event=FakeEvent(),
    )
    deleted = await runtime.delete_helper_subagent(
        started.data["run_id"],
        from_member="planner",
        helper_name="analysis",
        actor_member="planner",
        event=FakeEvent(),
    )

    helper_instance_name = "agent_group_run-1_helper_planner_analysis"
    helper_create = subagent_runtime.created_instances[-1]
    assert created.ok is True
    assert created.data["helper"]["instance_name"] == helper_instance_name
    assert helper_create["name"] == helper_instance_name
    assert helper_create["preset_name"] == "all_tools_preset"
    assert helper_create["overrides"]["tools"] == ["base_search"]
    assert helper_create["overrides"]["skills"] == ["planning"]
    assert ran.ok is True
    assert ran.data["final_response"] == f"{helper_instance_name} acknowledged"
    assert "Check the implementation" in subagent_runtime.run_calls[-1]["input_text"]
    assert reset.ok is True
    assert subagent_runtime.reset_calls[-1]["name"] == helper_instance_name
    assert deleted.ok is True
    assert subagent_runtime.delete_calls[-1]["name"] == helper_instance_name
    status = await runtime.get_status(run_id=started.data["run_id"])
    assert status.data["metadata"].get("helper_subagents", {}) == {}


@pytest.mark.asyncio
async def test_group_helper_subagent_requires_creator_identity_and_existing_helper():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    impersonated = await runtime.create_helper_subagent(
        started.data["run_id"],
        from_member="planner",
        helper_name="analysis",
        preset_name="reviewer_preset",
        actor_member="reviewer",
        event=FakeEvent(),
    )
    missing = await runtime.run_helper_subagent(
        started.data["run_id"],
        from_member="planner",
        helper_name="missing",
        input_text="hello",
        actor_member="planner",
        event=FakeEvent(),
    )

    assert impersonated.ok is False
    assert impersonated.error.error_code == "member_impersonation"
    assert missing.ok is False
    assert missing.error.error_code == "helper_subagent_not_found"


@pytest.mark.asyncio
async def test_group_helper_subagents_are_cleaned_when_run_finishes():
    subagent_runtime = FakeSubAgentRuntime()
    runtime = manager(enabled_config(), subagent_runtime=subagent_runtime)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )
    created = await runtime.create_helper_subagent(
        started.data["run_id"],
        from_member="planner",
        helper_name="analysis",
        preset_name="all_tools_preset",
        actor_member="planner",
        event=FakeEvent(),
    )

    await runtime.mark_complete(
        started.data["run_id"],
        "planner",
        "Plan done",
        event=FakeEvent(),
    )
    await runtime.mark_complete(
        started.data["run_id"],
        "reviewer",
        "Looks good",
        event=FakeEvent(),
    )
    await asyncio.sleep(0)

    assert created.ok is True
    assert subagent_runtime.deleted_instance_ids == [
        created.data["helper"]["instance_id"]
    ]


@pytest.mark.asyncio
async def test_mark_complete_finishes_run_after_all_enabled_members_complete():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    first = await runtime.mark_complete(started.data["run_id"], "planner", "Plan done")
    second = await runtime.mark_complete(
        started.data["run_id"],
        "reviewer",
        "Looks good",
    )

    assert first.ok is True
    assert first.data["status"] == "active"
    assert second.ok is True
    assert second.data["status"] == "completed"
    assert second.data["final_opinions"] == {
        "planner": "Plan done",
        "reviewer": "Looks good",
    }
    assert "planner: Plan done" in second.data["summary"]
    assert runtime.db.saved_states[-1][1] == "completed"


@pytest.mark.asyncio
async def test_mark_complete_runs_summary_subagent_after_all_members_complete():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    first = await runtime.mark_complete(
        started.data["run_id"],
        "planner",
        "Plan done",
        event=FakeEvent(),
    )
    second = await runtime.mark_complete(
        started.data["run_id"],
        "reviewer",
        "Looks good",
        event=FakeEvent(),
    )

    summary_create = runtime.subagent_runtime_manager.created_instances[-1]
    summary_run = runtime.subagent_runtime_manager.run_calls[-1]
    assert first.data["summary"] is None
    assert second.ok is True
    assert second.data["summary"] == "agent_group_run-1_summary acknowledged"
    assert summary_create["name"] == "agent_group_run-1_summary"
    assert summary_create["preset_name"] == "agent_group_summary"
    assert summary_create["overrides"]["tools"] == []
    assert summary_create["overrides"]["skills"] == []
    assert summary_run["name"] == "agent_group_run-1_summary"
    assert "Final opinions" in summary_run["input_text"]
    assert "planner: Plan done" in summary_run["input_text"]
    assert "reviewer: Looks good" in summary_run["input_text"]


@pytest.mark.asyncio
async def test_revoke_complete_reopens_run_and_resets_summary_token_usage():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )
    await runtime.mark_complete(
        started.data["run_id"],
        "planner",
        "Plan done",
        event=FakeEvent(),
    )
    completed = await runtime.mark_complete(
        started.data["run_id"],
        "reviewer",
        "Looks good",
        event=FakeEvent(),
    )

    revoked = await runtime.revoke_complete(started.data["run_id"], "planner")
    recompleted = await runtime.mark_complete(
        started.data["run_id"],
        "planner",
        "Updated plan",
        event=FakeEvent(),
    )

    assert completed.data["status"] == "completed"
    assert completed.data["token_usage"]["summary"] == 5
    assert revoked.ok is True
    assert revoked.data["status"] == "active"
    assert revoked.data["summary"] is None
    assert "planner" not in revoked.data["final_opinions"]
    assert "summary" not in revoked.data["token_usage"]
    assert revoked.data["token_usage"]["total"] == 0
    assert recompleted.data["status"] == "completed"
    assert recompleted.data["token_usage"]["summary"] == 5
    assert recompleted.data["token_usage"]["total"] == 5


@pytest.mark.asyncio
async def test_summary_prompt_hides_private_messages_by_default():
    config = enabled_config()
    config["presets"][0]["summary_include_private"] = False
    runtime = manager(config)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )
    await runtime.msg_to_agent(
        started.data["run_id"],
        from_member="planner",
        to_member="reviewer",
        content="private implementation detail",
    )
    await runtime.msg_to_group(
        started.data["run_id"],
        from_member="planner",
        content="public recommendation",
    )

    await runtime.mark_complete(
        started.data["run_id"],
        "planner",
        "Plan done",
        event=FakeEvent(),
    )
    await runtime.mark_complete(
        started.data["run_id"],
        "reviewer",
        "Looks good",
        event=FakeEvent(),
    )

    summary_input = runtime.subagent_runtime_manager.run_calls[-1]["input_text"]
    assert "public recommendation" in summary_input
    assert "private implementation detail" not in summary_input


@pytest.mark.asyncio
async def test_get_status_hides_private_messages_by_default_and_can_include_them():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )
    await runtime.msg_to_agent(
        started.data["run_id"],
        from_member="planner",
        to_member="reviewer",
        content="private implementation detail",
    )
    await runtime.msg_to_group(
        started.data["run_id"],
        from_member="planner",
        content="public recommendation",
    )

    public_status = await runtime.get_status(run_id=started.data["run_id"])
    private_status = await runtime.get_status(
        run_id=started.data["run_id"],
        include_private=True,
    )

    public_messages = [message["content"] for message in public_status.data["messages"]]
    private_messages = [
        message["content"] for message in private_status.data["messages"]
    ]
    assert "public recommendation" in public_messages
    assert "private implementation detail" not in public_messages
    assert "private implementation detail" in private_messages


@pytest.mark.asyncio
async def test_msg_to_agent_schedules_target_member_with_unread_message():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    result = await runtime.msg_to_agent(
        started.data["run_id"],
        from_member="planner",
        to_member="reviewer",
        content="private implementation detail",
        event=FakeEvent(),
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert result.ok is True
    assert runtime.subagent_runtime_manager.run_calls[-1]["name"] == (
        "agent_group_run-1_reviewer"
    )
    assert "private implementation detail" in (
        runtime.subagent_runtime_manager.run_calls[-1]["input_text"]
    )
    status = await runtime.get_status(run_id=started.data["run_id"])
    assert "reviewer" not in status.data["metadata"].get("unread_by_member", {})


@pytest.mark.asyncio
async def test_msg_to_group_schedules_active_uncompleted_members_except_sender():
    config = enabled_config()
    config["presets"][0]["members"].append(
        {"name": "observer", "subagent_preset": "reviewer_preset"}
    )
    runtime = manager(config)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )
    await runtime.mark_complete(started.data["run_id"], "reviewer", "Done")

    result = await runtime.msg_to_group(
        started.data["run_id"],
        from_member="planner",
        content="Please review this update",
        event=FakeEvent(),
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert result.ok is True
    dispatched = {
        call["name"] for call in runtime.subagent_runtime_manager.run_calls
    }
    assert "agent_group_run-1_observer" in dispatched
    assert "agent_group_run-1_planner" not in dispatched
    assert "agent_group_run-1_reviewer" not in dispatched


@pytest.mark.asyncio
async def test_followup_dispatch_runs_triggered_members_in_parallel():
    subagent_runtime = BlockingSubAgentRuntime()
    config = enabled_config()
    config["presets"][0]["members"].append(
        {"name": "observer", "subagent_preset": "reviewer_preset"}
    )
    runtime = manager(config, subagent_runtime=subagent_runtime)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    dispatch_task = asyncio.create_task(
        runtime._dispatch_members(
            FakeEvent(),
            started.data["run_id"],
            ["reviewer", "observer"],
        )
    )
    try:
        await asyncio.wait_for(subagent_runtime.started_two.wait(), timeout=0.2)
    finally:
        subagent_runtime.release.set()
        await dispatch_task

    assert subagent_runtime.max_running == 2


@pytest.mark.asyncio
async def test_initial_recipients_dispatch_in_parallel():
    subagent_runtime = BlockingSubAgentRuntime()
    config = enabled_config()
    config["presets"][0]["initial_recipients"] = ["planner", "reviewer"]
    runtime = manager(config, subagent_runtime=subagent_runtime)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    dispatch_task = asyncio.create_task(
        runtime._dispatch_initial_recipients(
            FakeEvent(),
            started.data,
        )
    )
    try:
        await asyncio.wait_for(subagent_runtime.started_two.wait(), timeout=0.2)
    finally:
        subagent_runtime.release.set()
        await dispatch_task

    assert subagent_runtime.max_running == 2


@pytest.mark.asyncio
async def test_start_run_dispatches_initial_task_to_every_enabled_member():
    subagent_runtime = FakeSubAgentRuntime()
    config = enabled_config()
    config["presets"][0]["initial_recipients"] = ["planner"]
    runtime = manager(config, subagent_runtime=subagent_runtime)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    assert started.ok is True
    assert started.data["metadata"]["initial_recipients"] == ["planner", "reviewer"]

    await runtime._dispatch_initial_recipients(
        FakeEvent(),
        started.data,
    )

    assert [call["name"] for call in subagent_runtime.run_calls] == [
        "agent_group_run-1_planner",
        "agent_group_run-1_reviewer",
    ]
    assert all("Task: Review" in call["input_text"] for call in subagent_runtime.run_calls)


@pytest.mark.asyncio
async def test_parallel_dispatch_records_all_member_results_with_independent_db_rows():
    subagent_runtime = BlockingSubAgentRuntime()
    config = enabled_config()
    config["presets"][0]["initial_recipients"] = ["planner", "reviewer"]
    db = CopyingFakeDB()
    runtime = manager(config, db=db, subagent_runtime=subagent_runtime)
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    dispatch_task = asyncio.create_task(
        runtime._dispatch_initial_recipients(
            FakeEvent(),
            started.data,
        )
    )
    try:
        await asyncio.wait_for(subagent_runtime.started_two.wait(), timeout=0.2)
    finally:
        subagent_runtime.release.set()
        await dispatch_task

    status = await runtime.get_status(run_id=started.data["run_id"])
    contents = [message["content"] for message in status.data["messages"]]
    assert "agent_group_run-1_planner acknowledged" in contents
    assert "agent_group_run-1_reviewer acknowledged" in contents
    assert status.data["token_usage"]["members"] == {
        "planner": 5,
        "reviewer": 5,
    }


@pytest.mark.asyncio
async def test_send_input_schedules_all_active_uncompleted_members():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    result = await runtime.send_input(
        started.data["run_id"],
        "Additional requirements",
        event=FakeEvent(),
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert result.ok is True
    dispatched = [
        call["name"] for call in runtime.subagent_runtime_manager.run_calls
    ]
    assert dispatched == [
        "agent_group_run-1_planner",
        "agent_group_run-1_reviewer",
    ]


@pytest.mark.asyncio
async def test_group_messages_validate_members_and_update_state():
    runtime = manager(enabled_config())
    started = await runtime.start_run(
        FakeEvent(),
        "review_team",
        "Review",
        dispatch_initial=False,
    )

    missing = await runtime.msg_to_agent(
        started.data["run_id"],
        from_member="planner",
        to_member="missing",
        content="hello",
    )
    posted = await runtime.msg_to_group(
        started.data["run_id"],
        from_member="planner",
        content="Plan is ready",
    )

    assert missing.ok is False
    assert missing.error.error_code == MEMBER_NOT_FOUND
    assert posted.ok is True
    assert posted.data["messages"][-1]["from"] == "planner"
    assert posted.data["messages"][-1]["to"] == "group"


@pytest.mark.asyncio
async def test_get_and_cancel_run_report_missing_run():
    runtime = manager(enabled_config())

    status = await runtime.get_status(run_id="missing")
    cancel = await runtime.cancel_run("missing")

    assert status.ok is False
    assert status.error.error_code == RUN_NOT_FOUND
    assert cancel.ok is False
    assert cancel.error.error_code == RUN_NOT_FOUND
