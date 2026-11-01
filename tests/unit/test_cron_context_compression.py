"""Regression tests for session compression in chat, Cron and background wakeups."""

import copy
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_main_agent import MainAgentBuildConfig
from astrbot.core.astr_main_agent_resources import (
    BACKGROUND_TASK_RESULT_WOKE_USER_PROMPT,
    PROACTIVE_AGENT_CRON_WOKE_USER_PROMPT,
)
from astrbot.core.config.agent_runner import (
    normalize_agent_runner,
    resolve_context_compression_config,
)
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.cron.manager import CronJobManager
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.utils.active_event_registry import active_event_registry


def test_explicit_build_settings_and_per_request_overrides_are_preserved():
    """Keep direct callers and dataclasses.replace independent of raw settings."""
    defaults = MainAgentBuildConfig(tool_call_timeout=60)
    assert defaults.max_context_length == 50
    assert defaults.dequeue_context_length == 10
    direct = MainAgentBuildConfig(
        tool_call_timeout=60, max_context_length=7, dequeue_context_length=2
    )
    assert direct.max_context_length == 7
    assert direct.dequeue_context_length == 2

    source = {"max_turns": 12, "trim_turns": 3, "provider_id": "summary-model"}
    configured = MainAgentBuildConfig(
        tool_call_timeout=60, **resolve_context_compression_config(source)
    )
    source["max_turns"] = 99
    per_request = replace(configured, streaming_response=False, max_context_length=8)
    assert configured.max_context_length == 12
    assert per_request.max_context_length == 8
    assert per_request.dequeue_context_length == 3
    assert per_request.llm_compress_provider_id == "summary-model"
    assert per_request.streaming_response is False


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["cron", "background"])
@pytest.mark.parametrize(
    ("compression", "expected"),
    [
        pytest.param(
            {
                "overflow_strategy": "llm_compress",
                "instruction": "Keep decisions and unfinished tasks.",
                "keep_recent_ratio": 0.3,
                "provider_id": "summary-model",
                "max_turns": 12,
                "trim_turns": 3,
                "fallback_max_tokens": 16384,
            },
            (
                "llm_compress",
                "Keep decisions and unfinished tasks.",
                0.3,
                "summary-model",
                12,
                3,
                16384,
            ),
            id="configured-summary-model",
        ),
        pytest.param(
            {},
            ("llm_compress", "", 0.15, "", -1, 1, 128000),
            id="empty-config",
        ),
        pytest.param(
            None,
            ("llm_compress", "", 0.15, "", -1, 1, 128000),
            id="missing-cron-compression-section",
        ),
        pytest.param(
            {"max_turns": 4, "trim_turns": 20},
            ("llm_compress", "", 0.15, "", 4, 3, 128000),
            id="trim-clamped-to-preserve-recent-turn",
        ),
        pytest.param(
            {"max_turns": 1, "trim_turns": 0},
            ("llm_compress", "", 0.15, "", 1, 1, 128000),
            id="single-turn-minimum-trim",
        ),
        pytest.param(
            {"max_turns": -1, "trim_turns": 5},
            ("llm_compress", "", 0.15, "", -1, 5, 128000),
            id="unlimited-turns",
        ),
        pytest.param(
            {"max_turns": -1, "trim_turns": -3},
            ("llm_compress", "", 0.15, "", -1, 1, 128000),
            id="unlimited-turns-minimum-trim",
        ),
    ],
)
async def test_wakeup_uses_same_compression_settings_as_chat(
    compression, expected, entrypoint, wakeup_pipeline
):
    """Resolve compression from the bound session without changing its history."""
    conf = copy.deepcopy(DEFAULT_CONFIG)
    conf["agent_runner"]["config"]["compression"] = compression or {}
    conf["agent_runner"]["config"]["model"]["request_max_retries"] = 2
    conf["agent_runner"]["config"]["misc"]["tool_schema_mode"] = "skills_like"
    conf["kb_agentic_mode"] = True
    conf["provider_settings"]["file_extract"] = {"enable": True, "provider": "test"}
    conf["provider_settings"]["proactive_capability"] = {"add_cron_tools": False}
    conf["provider_settings"]["max_quoted_fallback_images"] = 3
    ctx = MagicMock()
    ctx.get_platform_inst.return_value = SimpleNamespace(
        meta=lambda: PlatformMetadata(
            id="test", name="test_platform", description="Test"
        )
    )
    ctx.get_config.return_value = conf
    conf_for_chat = copy.deepcopy(conf)
    conf_for_chat["agent_runner"] = normalize_agent_runner(
        conf_for_chat["agent_runner"]
    )
    stage = InternalAgentSubStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config=conf_for_chat,
            plugin_manager=SimpleNamespace(context=ctx),
        )
    )
    if compression is None:
        del conf["agent_runner"]["config"]["compression"]
    original_conf = copy.deepcopy(conf)

    async def steps(max_step):
        if False:
            yield None

    runner = MagicMock()
    runner.step_until_done.side_effect = steps
    runner.get_final_llm_resp.return_value = LLMResponse(
        role="assistant", completion_text="Task completed."
    )
    history = [
        {"role": "user", "content": "An earlier request"},
        {"role": "assistant", "content": "An earlier answer"},
    ]
    conv = SimpleNamespace(history=json.dumps(history))
    manager = CronJobManager(MagicMock())
    manager.ctx = ctx
    ctx.get_config.reset_mock()
    with (
        patch(
            "astrbot.core.astr_main_agent.request._get_session_conv",
            AsyncMock(return_value=conv),
        ),
        patch(
            "astrbot.core.astr_main_agent.build_main_agent",
            AsyncMock(return_value=SimpleNamespace(agent_runner=runner)),
        ) as build,
        patch(
            "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.InternalAgentSubStage._save_to_history",
            AsyncMock(),
        ),
    ):
        if entrypoint == "cron":
            await wakeup_pipeline.execute(
                wakeup_pipeline(manager.ctx),
                umo="test:FriendMessage:user123",
                source="cron",
                user_prompt=PROACTIVE_AGENT_CRON_WOKE_USER_PROMPT.format(
                    cron_job=json.dumps(
                        ({"cron_job": {"id": "job-1"}, "cron_payload": {}}).get(
                            "cron_job", {}
                        ),
                        ensure_ascii=False,
                    )
                ),
            )
        else:
            event_extras: dict[str, object] = {}
            ctx.get_llm_tool_manager.return_value.get_builtin_tool.return_value = (
                FunctionTool(
                    name="send_message_to_user",
                    description="Send the background result.",
                    parameters={"type": "object", "properties": {}},
                )
            )
            wakeup_context = SimpleNamespace(
                context=SimpleNamespace(
                    event=SimpleNamespace(
                        unified_msg_origin="test:FriendMessage:user123",
                        role="member",
                        get_extra=event_extras.get,
                        set_extra=event_extras.__setitem__,
                    ),
                    context=ctx,
                ),
                tool_call_timeout=120,
            )
            await wakeup_pipeline.execute(
                wakeup_pipeline(wakeup_context.context.context),
                umo=wakeup_context.context.event.unified_msg_origin,
                source="background_task",
                user_prompt=BACKGROUND_TASK_RESULT_WOKE_USER_PROMPT.format(
                    background_task_result=json.dumps(
                        {
                            "task_id": "task-1",
                            "tool_name": "background-tool",
                            "result": "Task completed.",
                            "tool_args": {},
                        },
                        ensure_ascii=False,
                    )
                ),
                role=wakeup_context.context.event.role,
                stop_signal=active_event_registry.get_background_stop_signal(
                    wakeup_context.context.event
                ),
            )
            assert (
                build.await_args.kwargs["event"].get_extra("_background_stop_signal")
                is event_extras["_background_stop_signal"]
            )

    ctx.get_config.assert_called_once_with(umo="test:FriendMessage:user123")
    wakeup_config = build.await_args.kwargs["config"]
    fields = (
        "context_limit_reached_strategy",
        "llm_compress_instruction",
        "llm_compress_keep_recent_ratio",
        "llm_compress_provider_id",
        "max_context_length",
        "dequeue_context_length",
        "fallback_max_context_tokens",
    )
    assert tuple(getattr(wakeup_config, name) for name in fields) == expected
    assert tuple(getattr(stage.main_agent_cfg, name) for name in fields) == expected
    for name in (
        "request_max_retries",
        "tool_schema_mode",
        "kb_agentic_mode",
        "file_extract_enabled",
        "file_extract_prov",
        "add_cron_tools",
        "max_quoted_fallback_images",
        "provider_settings",
    ):
        assert getattr(wakeup_config, name) == getattr(stage.main_agent_cfg, name)
    assert wakeup_config.streaming_response is False
    assert wakeup_config.call_request_hook is True
    assert wakeup_config.validate_provider_endpoint is True
    assert "req" not in build.await_args.kwargs
    assert conf == original_conf
    assert json.loads(conv.history) == history
