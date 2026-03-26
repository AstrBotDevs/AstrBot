# ruff: noqa: E402
"""Session 管理客户端 Core Bridge 集成测试。

测试覆盖 01_context_api.md 中 ctx.session_plugins 和 ctx.session_services 的所有方法：

SessionPluginManager:
- is_plugin_enabled_for_session(): 检查插件在会话中是否启用
- filter_handlers_by_session(): 根据会话过滤 handler

SessionServiceManager:
- is_llm_enabled_for_session(): 检查 LLM 是否启用
- set_llm_status_for_session(): 设置 LLM 状态
- is_tts_enabled_for_session(): 检查 TTS 是否启用
- set_tts_status_for_session(): 设置 TTS 状态
"""
from __future__ import annotations

import pytest

from tests.test_sdk.unit._context_api_roundtrip import build_roundtrip_runtime


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_session_plugins_is_enabled_defaults_true(
    tmp_path, monkeypatch
):
    """默认情况下，插件在会话中是启用的。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    enabled = await ctx.session_plugins.is_plugin_enabled_for_session(
        "qq:private:user-123",
        "plugin-a"
    )

    assert enabled is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_session_plugins_respects_disabled(tmp_path, monkeypatch):
    """当插件被禁用时，is_plugin_enabled_for_session 返回 False。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    # 设置会话插件配置：禁用 plugin-a
    runtime.set_session_plugin_config(
        "qq:private:user-456",
        disabled_plugins=["plugin-a"]
    )

    enabled = await ctx.session_plugins.is_plugin_enabled_for_session(
        "qq:private:user-456",
        "plugin-a"
    )

    assert enabled is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_session_services_llm_enabled_round_trip(
    tmp_path, monkeypatch
):
    """LLM 状态可以设置和读取。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    session = "qq:group:111222"

    # 默认启用
    assert await ctx.session_services.is_llm_enabled_for_session(session) is True

    # 禁用 LLM
    await ctx.session_services.set_llm_status_for_session(session, enabled=False)
    assert await ctx.session_services.is_llm_enabled_for_session(session) is False

    # 重新启用
    await ctx.session_services.set_llm_status_for_session(session, enabled=True)
    assert await ctx.session_services.is_llm_enabled_for_session(session) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_session_services_tts_enabled_round_trip(
    tmp_path, monkeypatch
):
    """TTS 状态可以设置和读取。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    session = "qq:private:user-789"

    # 默认启用
    assert await ctx.session_services.is_tts_enabled_for_session(session) is True

    # 禁用 TTS
    await ctx.session_services.set_tts_status_for_session(session, enabled=False)
    assert await ctx.session_services.is_tts_enabled_for_session(session) is False

    # 重新启用
    await ctx.session_services.set_tts_status_for_session(session, enabled=True)
    assert await ctx.session_services.is_tts_enabled_for_session(session) is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_session_services_should_process_llm(tmp_path, monkeypatch):
    """should_process_llm_request 检查 LLM 状态。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    session = "qq:group:333444"

    # 默认可以处理
    assert await ctx.session_services.should_process_llm_request(session) is True

    # 禁用后不应处理
    await ctx.session_services.set_llm_status_for_session(session, enabled=False)
    assert await ctx.session_services.should_process_llm_request(session) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_session_services_should_process_tts(tmp_path, monkeypatch):
    """should_process_tts_request 检查 TTS 状态。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    session = "qq:private:user-999"

    # 默认可以处理
    assert await ctx.session_services.should_process_tts_request(session) is True

    # 禁用后不应处理
    await ctx.session_services.set_tts_status_for_session(session, enabled=False)
    assert await ctx.session_services.should_process_tts_request(session) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_context_session_services_different_sessions_isolated(
    tmp_path, monkeypatch
):
    """不同会话的 LLM/TTS 状态是隔离的。"""
    runtime = build_roundtrip_runtime(monkeypatch, tmp_path=tmp_path)
    ctx = runtime.make_context("plugin-a")

    session_a = "qq:private:user-a"
    session_b = "qq:private:user-b"

    # 禁用 session_a 的 LLM
    await ctx.session_services.set_llm_status_for_session(session_a, enabled=False)

    # session_b 的 LLM 仍然启用
    assert await ctx.session_services.is_llm_enabled_for_session(session_a) is False
    assert await ctx.session_services.is_llm_enabled_for_session(session_b) is True
