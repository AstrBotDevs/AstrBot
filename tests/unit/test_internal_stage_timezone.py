"""Tests for profile-scoped timezone resolution in InternalAgentSubStage.

Bug 背景(#9706)：配置档(abconf) JSON 中保存了隐藏的 timezone 字段，
cron 调度读取它(cron_tools)，但 LLM 系统提示词的时间感知却始终读全局
配置(internal.py 原先写死 context.get_config())，两个子系统时区不一致。

修复：InternalAgentSubStage 初始化时从本 pipeline 自己的配置档读取
timezone；cron 唤醒路径同样传入会话配置档的 timezone。
"""

from unittest.mock import MagicMock

import pytest

from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    InternalAgentSubStage,
)


def _profile_settings() -> dict:
    return {
        "streaming_response": False,
        "unsupported_streaming_strategy": "reply",
        "max_agent_step": 30,
        "tool_call_timeout": 60,
        "tool_schema_mode": "full",
        "show_tool_use_status": True,
        "show_tool_call_result": False,
        "buffer_intermediate_messages": False,
        "display_reasoning_text": False,
        "sanitize_context_by_modalities": False,
        "max_context_length": 50,
        "dequeue_context_length": 20,
        "fallback_max_context_tokens": 128000,
        "llm_safety_mode": True,
        "safety_mode_strategy": "system_prompt",
        "file_extract": {},
        "proactive_capability": {},
        "sandbox": {},
    }


def _make_ctx(profile_conf: dict) -> PipelineContext:
    return PipelineContext(
        astrbot_config=profile_conf,
        plugin_manager=MagicMock(),
        astrbot_config_id="test-conf",
    )


@pytest.mark.asyncio
async def test_timezone_comes_from_profile_not_global():
    """pipeline 应使用自己配置档的 timezone，而不是全局配置的。"""
    profile_conf = {
        "provider_settings": _profile_settings(),
        "timezone": "America/New_York",
        "kb_agentic_mode": False,
    }
    global_conf = {
        "provider_settings": _profile_settings(),
        "timezone": "Asia/Shanghai",
    }

    stage = InternalAgentSubStage()
    ctx = _make_ctx(profile_conf)
    ctx.plugin_manager.context.get_config.return_value = global_conf

    await stage.initialize(ctx)

    assert stage.main_agent_cfg.timezone == "America/New_York"


@pytest.mark.asyncio
async def test_timezone_missing_in_profile_is_none():
    """配置档没有 timezone 字段时应为 None（由后续逻辑回退全局）。"""
    profile_conf = {
        "provider_settings": _profile_settings(),
        "kb_agentic_mode": False,
    }

    stage = InternalAgentSubStage()
    ctx = _make_ctx(profile_conf)

    await stage.initialize(ctx)

    assert stage.main_agent_cfg.timezone is None
