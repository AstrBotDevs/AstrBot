"""Tests for provider lookup diagnostics in the plugin context."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.core import astr_main_agent
from astrbot.core.provider import Provider
from astrbot.core.star.context import Context


def _decision_provider(provider_id: str, *, enable: bool = True) -> dict:
    return {
        "id": provider_id,
        "type": "system_one_decision",
        "provider_type": "decision",
        "api_base": "https://decision.test/v1/systemone",
        "model": "jev-latest",
        "key": "",
        "enable": enable,
    }


def _context(inst_map: dict, providers_config: list[dict]) -> Context:
    context = Context.__new__(Context)
    context.provider_manager = SimpleNamespace(
        inst_map=inst_map,
        providers_config=providers_config,
    )
    return context


def test_get_provider_by_id_reports_disabled_provider(caplog):
    context = _context({}, [_decision_provider("disabled_provider", enable=False)])

    with caplog.at_level(logging.WARNING):
        assert context.get_provider_by_id("disabled_provider") is None

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "Provider disabled_provider is disabled" in message for message in messages
    )
    assert not any("may have been changed" in message for message in messages)


def test_get_provider_by_id_reports_not_loaded_and_keeps_unknown_wording(caplog):
    context = _context({}, [_decision_provider("not_loaded_provider")])

    with caplog.at_level(logging.WARNING):
        assert context.get_provider_by_id("not_loaded_provider") is None
        assert context.get_provider_by_id("missing_provider") is None

    messages = {record.getMessage() for record in caplog.records}
    not_loaded = next(
        message for message in messages if "not_loaded_provider" in message
    )
    assert "configured but was not loaded" in not_loaded
    assert "may have been changed" not in not_loaded
    assert (
        "Provider missing_provider was not found. Its provider or model ID "
        "may have been changed."
    ) in messages


@pytest.mark.asyncio
async def test_compress_and_fallback_lookup_report_disabled_provider(caplog):
    context = _context({}, [_decision_provider("disabled_provider", enable=False)])
    config = astr_main_agent.MainAgentBuildConfig(
        tool_call_timeout=60,
        context_limit_reached_strategy="llm_compress",
        llm_compress_provider_id="disabled_provider",
    )
    primary = MagicMock(spec=Provider)
    primary.provider_config = {"id": "primary_provider"}

    with caplog.at_level(logging.WARNING):
        compress_provider = await astr_main_agent._get_compress_provider(
            config, context
        )
        fallback_providers = astr_main_agent._get_fallback_chat_providers(
            primary, context, ["disabled_provider"]
        )

    assert compress_provider is None
    assert fallback_providers == []
    messages = [record.getMessage() for record in caplog.records]
    disabled_messages = [
        message
        for message in messages
        if "Provider disabled_provider is disabled" in message
    ]
    assert len(disabled_messages) == 2
    assert not any("may have been changed" in message for message in messages)
