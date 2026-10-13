"""Regression tests for stable system prefixes across proactive wakeups."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.agent.runners.base import AgentState
from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.tools.message_tools import SendMessageToUserTool


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["cron", "background"])
@pytest.mark.parametrize("change_history", [False, True])
async def test_wakeup_preserves_system_prefix_and_structured_history(
    entrypoint, change_history
):
    """Changing task data belongs in the last user turn, after the cacheable prefix."""
    ctx = MagicMock()
    ctx.get_config.return_value = {}
    ctx.get_llm_tool_manager.return_value.get_builtin_tool.return_value = (
        SendMessageToUserTool()
    )
    manager = CronJobManager(MagicMock())
    manager.ctx = ctx
    history = [
        {"role": "user", "content": "Earlier request"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "old-call",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "old-call", "content": "Earlier result"},
        {"role": "assistant", "content": "Earlier answer"},
    ]
    conv = SimpleNamespace(history=json.dumps(history))
    original_history = conv.history

    async def steps(max_step):
        if False:
            yield None

    runner = SimpleNamespace(
        state=AgentState.DONE,
        step_until_done=steps,
        get_final_llm_resp=lambda: None,
    )
    requests = []
    with (
        patch(
            "astrbot.core.astr_main_agent._get_session_conv",
            AsyncMock(return_value=conv),
        ),
        patch(
            "astrbot.core.astr_main_agent.build_main_agent",
            AsyncMock(return_value=SimpleNamespace(agent_runner=runner)),
        ) as build,
        patch("astrbot.core.cron.manager.persist_agent_history", AsyncMock()),
        patch("astrbot.core.astr_agent_tool_exec.persist_agent_history", AsyncMock()),
    ):
        for index in range(2):
            if change_history and index:
                history.extend(
                    [
                        {"role": "user", "content": "Next request"},
                        {"role": "assistant", "content": "Next answer"},
                    ]
                )
                conv.history = json.dumps(history)
            if entrypoint == "cron":
                payload = {
                    "id": f"job-{index}",
                    "run_started_at": f"2026-09-28T12:0{index}:00",
                    "note": f"Send reminder {index}",
                    "session": "test:FriendMessage:user123",
                }
                heading = "# CRON JOB CONTEXT\n"
                await manager._woke_main_agent(
                    message=payload["note"],
                    session_str=payload["session"],
                    extras={"cron_job": payload, "cron_payload": {}},
                    delivery_session_str=payload["session"],
                )
            else:
                payload = {
                    "task_id": f"task-{index}",
                    "tool_name": "lookup",
                    "result": f"Result {index}",
                    "tool_args": {"query": f"Search {index}"},
                    "status": "completed",
                }
                heading = "# BACKGROUND TASK CONTEXT\n"
                await FunctionToolExecutor._wake_main_agent_for_background_result(
                    SimpleNamespace(
                        context=SimpleNamespace(
                            event=SimpleNamespace(
                                unified_msg_origin="test:FriendMessage:user123",
                                role="member",
                            ),
                            context=ctx,
                        ),
                        tool_call_timeout=120,
                    ),
                    task_id=payload["task_id"],
                    tool_name=payload["tool_name"],
                    result_text=payload["result"],
                    tool_args=payload["tool_args"],
                    note="Background task finished",
                    summary_name="BackgroundTask",
                    extra_result_fields={"status": "completed"},
                )
            request = build.await_args.kwargs["req"]
            requests.append(request)
            assert request.contexts == history
            assert "Earlier request" not in request.system_prompt
            assert "Earlier result" not in request.prompt
            assert "send_message_to_user" in request.system_prompt
            assert heading not in request.system_prompt
            task_json = request.prompt.split(heading, 1)[1].split("\n", 1)[1]
            assert json.loads(task_json) == payload
            assert request.func_tool.names() == ["send_message_to_user"]
            assert json.loads(conv.history) == history

    assert requests[0].system_prompt == requests[1].system_prompt
    assert requests[0].prompt != requests[1].prompt
    assert (
        requests[0].func_tool.get_func_desc_openai_style()
        == requests[1].func_tool.get_func_desc_openai_style()
    )
    assert requests[0].contexts == json.loads(original_history)
