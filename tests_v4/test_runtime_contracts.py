"""Contract guards for the current public runtime/compat surface."""

from __future__ import annotations

from importlib import import_module

from astrbot_sdk.api.event import filter as compat_filter_namespace
from astrbot_sdk.protocol.descriptors import BUILTIN_CAPABILITY_SCHEMAS
from astrbot_sdk.runtime.capability_router import CapabilityRouter

EXPECTED_PUBLIC_BUILTIN_CAPABILITIES = {
    "llm.chat": False,
    "llm.chat_raw": False,
    "llm.stream_chat": True,
    "memory.search": False,
    "memory.save": False,
    "memory.get": False,
    "memory.delete": False,
    "db.get": False,
    "db.set": False,
    "db.delete": False,
    "db.list": False,
    "db.get_many": False,
    "db.set_many": False,
    "db.watch": True,
    "platform.send": False,
    "platform.send_image": False,
    "platform.send_chain": False,
    "platform.get_members": False,
}
EXPECTED_CANCELABLE_CAPABILITIES = {"llm.stream_chat", "db.watch"}
EXPECTED_PUBLIC_COMPAT_HOOKS = {
    "after_message_sent",
    "on_astrbot_loaded",
    "on_platform_loaded",
    "on_decorating_result",
    "on_llm_request",
    "on_llm_response",
    "on_waiting_llm_request",
    "on_using_llm_tool",
    "on_llm_tool_respond",
    "on_plugin_error",
    "on_plugin_loaded",
    "on_plugin_unloaded",
}


def test_builtin_capability_schema_registry_matches_public_contract():
    """协议层公开的内建 capability 集合必须保持稳定。"""
    assert set(BUILTIN_CAPABILITY_SCHEMAS) == set(EXPECTED_PUBLIC_BUILTIN_CAPABILITIES)


def test_capability_router_descriptors_match_public_contract():
    """Runtime 层内建 capability 的名字、stream 和 cancel 语义必须对齐契约。"""
    descriptors = {item.name: item for item in CapabilityRouter().descriptors()}

    assert set(descriptors) == set(EXPECTED_PUBLIC_BUILTIN_CAPABILITIES)
    assert {
        name: descriptor.supports_stream for name, descriptor in descriptors.items()
    } == EXPECTED_PUBLIC_BUILTIN_CAPABILITIES
    assert {
        name for name, descriptor in descriptors.items() if descriptor.cancelable
    } == EXPECTED_CANCELABLE_CAPABILITIES


def test_public_compat_hook_factories_remain_available():
    """兼容 hook 名称必须同时保留模块级和 namespace 级入口。"""
    compat_filter_module = import_module("astrbot_sdk.api.event.filter")

    for name in EXPECTED_PUBLIC_COMPAT_HOOKS:
        assert callable(getattr(compat_filter_module, name))
        assert callable(getattr(compat_filter_namespace, name))
