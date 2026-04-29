"""Tests for astrbot.core.provider.register.

Covers register_provider_adapter decorator, provider_registry list,
provider_cls_map dict, llm_tools import, duplicate registration,
and default config template processing.
"""

import pytest

from astrbot.core.provider.entities import ProviderMetaData, ProviderType
from astrbot.core.provider.register import (
    llm_tools,
    provider_cls_map,
    provider_registry,
    register_provider_adapter,
)


# =========================================================================
# Fixtures — fresh state per test
# =========================================================================


@pytest.fixture(autouse=True)
def _clear_registries():
    """Clear global registries before and after each test to avoid cross-test pollution."""
    before_keys = set(provider_cls_map.keys())
    before_len = len(provider_registry)

    yield

    # Restore: remove any keys/items added during the test
    added_keys = set(provider_cls_map.keys()) - before_keys
    for k in added_keys:
        provider_cls_map.pop(k, None)

    added_items = len(provider_registry) - before_len
    for _ in range(added_items):
        if provider_registry:
            provider_registry.pop()


# =========================================================================
# register_provider_adapter
# =========================================================================


class TestRegisterProviderAdapter:
    def test_basic_registration(self):
        @register_provider_adapter("test_provider", "A test provider")
        class FakeProvider:
            pass

        assert "test_provider" in provider_cls_map
        pmd = provider_cls_map["test_provider"]
        assert isinstance(pmd, ProviderMetaData)
        assert pmd.type == "test_provider"
        assert pmd.desc == "A test provider"
        assert pmd.cls_type is FakeProvider
        assert pmd.provider_type == ProviderType.CHAT_COMPLETION  # default
        # Should also be in the registry list
        assert pmd in provider_registry

    def test_registration_with_custom_provider_type(self):
        @register_provider_adapter(
            "stt_provider",
            "STT provider",
            provider_type=ProviderType.SPEECH_TO_TEXT,
        )
        class FakeSTT:
            pass

        pmd = provider_cls_map["stt_provider"]
        assert pmd.provider_type == ProviderType.SPEECH_TO_TEXT

    def test_registration_with_display_name(self):
        @register_provider_adapter(
            "disp_provider",
            "Display test",
            provider_display_name="My Display Name",
        )
        class DispProvider:
            pass

        pmd = provider_cls_map["disp_provider"]
        assert pmd.provider_display_name == "My Display Name"

    def test_registration_with_default_config_tmpl(self):
        @register_provider_adapter(
            "tmpl_provider",
            "Template test",
            default_config_tmpl={"key1": "val1"},
        )
        class TmplProvider:
            pass

        pmd = provider_cls_map["tmpl_provider"]
        assert pmd.default_config_tmpl is not None
        # The decorator adds mandatory fields
        assert pmd.default_config_tmpl["type"] == "tmpl_provider"
        assert pmd.default_config_tmpl["enable"] is False
        assert pmd.default_config_tmpl["id"] == "tmpl_provider"
        assert pmd.default_config_tmpl["key1"] == "val1"

    def test_default_config_tmpl_preserves_existing_type(self):
        @register_provider_adapter(
            "tmpl2",
            "desc",
            default_config_tmpl={"type": "custom_type", "custom": True},
        )
        class T2:
            pass

        pmd = provider_cls_map["tmpl2"]
        # should NOT override existing type
        assert pmd.default_config_tmpl["type"] == "custom_type"
        assert pmd.default_config_tmpl["enable"] is False
        assert pmd.default_config_tmpl["id"] == "tmpl2"
        assert pmd.default_config_tmpl["custom"] is True

    def test_default_config_tmpl_preserves_existing_enable(self):
        @register_provider_adapter(
            "tmpl3", "desc", default_config_tmpl={"enable": True, "extra": "x"}
        )
        class T3:
            pass

        pmd = provider_cls_map["tmpl3"]
        assert pmd.default_config_tmpl["enable"] is True
        assert pmd.default_config_tmpl["type"] == "tmpl3"
        assert pmd.default_config_tmpl["extra"] == "x"

    def test_default_config_tmpl_preserves_existing_id(self):
        @register_provider_adapter(
            "tmpl4",
            "desc",
            default_config_tmpl={"id": "custom_id"},
        )
        class T4:
            pass

        pmd = provider_cls_map["tmpl4"]
        assert pmd.default_config_tmpl["id"] == "custom_id"

    def test_default_config_tmpl_none(self):
        @register_provider_adapter("no_tmpl", "No template")
        class NoTmpl:
            pass

        pmd = provider_cls_map["no_tmpl"]
        assert pmd.default_config_tmpl is None

    def test_duplicate_registration_raises(self):
        @register_provider_adapter("dup_provider", "First")
        class FirstProvider:
            pass

        with pytest.raises(ValueError, match="已经注册"):
            @register_provider_adapter("dup_provider", "Second")
            class SecondProvider:
                pass

        # The original registration should remain intact
        assert provider_cls_map["dup_provider"].desc == "First"
        assert provider_cls_map["dup_provider"].cls_type is FirstProvider

    def test_multiple_registrations(self):
        @register_provider_adapter("p1", "First provider")
        class P1:
            pass

        @register_provider_adapter("p2", "Second provider")
        class P2:
            pass

        assert len(provider_cls_map) == 2
        assert provider_cls_map["p1"].cls_type is P1
        assert provider_cls_map["p2"].cls_type is P2
        assert len(provider_registry) >= 2

    def test_decorator_returns_the_class(self):
        @register_provider_adapter("return_test", "Check return")
        class ReturnClass:
            pass

        # The decorator should return the class unchanged so it can be used normally
        instance = ReturnClass()
        assert isinstance(instance, ReturnClass)


# =========================================================================
# llm_tools / FuncCall
# =========================================================================


class TestLlmTools:
    def test_llm_tools_is_importable(self):
        from astrbot.core.provider.register import llm_tools as lt

        assert lt is not None

    def test_llm_tools_function_tool_manager_type(self):
        from astrbot.core.provider.func_tool_manager import FunctionToolManager

        assert isinstance(llm_tools, FunctionToolManager)

    def test_llm_tools_starts_empty(self):
        assert llm_tools.empty() is True

    def test_llm_tools_add_and_get(self):
        async def fake_handler(**kwargs):
            return "done"

        llm_tools.add_func(
            name="test_func",
            func_args=[{"name": "arg1", "type": "string", "description": "An arg"}],
            desc="A test function",
            handler=fake_handler,
        )
        tool = llm_tools.get_func("test_func")
        assert tool is not None
        assert tool.name == "test_func"
        llm_tools.remove_func("test_func")
        assert llm_tools.get_func("test_func") is None

    def test_llm_tools_remove_nonexistent(self):
        """Removing a function that does not exist should not raise."""
        llm_tools.remove_func("nonexistent_tool")  # should not raise


# =========================================================================
# Registry list / map invariants
# =========================================================================


class TestRegistryInvariants:
    def test_meta_id_is_default_in_registry(self):
        @register_provider_adapter("invariant_test", "check id")
        class InvProvider:
            pass

        pmd = provider_cls_map["invariant_test"]
        assert pmd.id == "default"
        assert pmd.model is None
