"""Public plugin context routes configuration and replaces API registrations."""

from asyncio import Queue
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.star import context as context_module
from astrbot.core.star.context import Context
from astrbot.core.star.star import StarMetadata


@pytest.fixture
def context():
    context = Context(
        event_queue=Queue(),
        config={"profile": "default"},
        db=object(),
        provider_manager=SimpleNamespace(llm_tools=object()),
        platform_manager=object(),
        conversation_manager=object(),
        message_history_manager=object(),
        persona_manager=object(),
        astrbot_config_mgr=SimpleNamespace(
            get_conf=Mock(return_value={"profile": "session"})
        ),
        knowledge_base_manager=object(),
        cron_manager=object(),
        agent_runtimes={},
    )
    context.registered_web_apis = []
    return context


def test_configuration_reads_preserve_session_scope(context):
    assert context.get_config() is context._config
    context.astrbot_config_mgr.get_conf.assert_not_called()
    assert context.get_config("test:FriendMessage:alice") == {"profile": "session"}
    context.astrbot_config_mgr.get_conf.assert_called_once_with(
        "test:FriendMessage:alice"
    )


def test_service_accessors_preserve_identity(context):
    assert context.conversation_manager is context.conversations
    assert context.get_event_queue() is context._event_queue
    assert context.get_llm_tool_manager() is context.provider_manager.llm_tools


def test_plugin_lookup_returns_exact_registered_metadata(context, monkeypatch):
    registered = [StarMetadata(name="weather"), StarMetadata(name="notes")]
    monkeypatch.setattr(context_module, "star_registry", registered)
    assert context.get_all_stars() is registered
    assert context.get_registered_star("notes") is registered[1]
    assert context.get_registered_star("missing") is None


def test_web_api_reload_replaces_only_matching_route_and_methods(context):
    async def original():
        return "original"

    async def replacement():
        return "replacement"

    context.register_web_api("/probe", original, ["GET"], "old")
    context.register_web_api("/probe", original, ["POST"], "post")
    context.register_web_api("/probe", replacement, ["GET"], "new")
    assert context.registered_web_apis == [
        ("/probe", replacement, ["GET"], "new"),
        ("/probe", original, ["POST"], "post"),
    ]
