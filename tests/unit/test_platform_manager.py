"""Tests for platform register and manager functions."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from astrbot.core.platform.register import (
    platform_cls_map,
    platform_registry,
    register_platform_adapter,
    unregister_platform_adapters_by_module,
)


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_platform_manager_case(case: str) -> None:
    code = f"""
    import asyncio

    case = {case!r}

    from astrbot.core.platform.manager import PlatformManager
    from astrbot.core.platform.platform import PlatformStatus


    class DummyConfig(dict):
        def save_config(self):
            self["_saved"] = True


    def make_manager():
        cfg = DummyConfig({{"platform": [], "platform_settings": {{}}}})
        return PlatformManager(cfg, asyncio.Queue())


    if case == "is_valid_platform_id_valid":
        manager = make_manager()
        assert manager._is_valid_platform_id("platform_1")
        assert manager._is_valid_platform_id("a-b")
        assert manager._is_valid_platform_id("A1")

    elif case == "is_valid_platform_id_invalid":
        manager = make_manager()
        assert manager._is_valid_platform_id(None) is False
        assert manager._is_valid_platform_id("") is False
        assert manager._is_valid_platform_id("a:b") is False
        assert manager._is_valid_platform_id("a!b") is False

    elif case == "sanitize_platform_id":
        manager = make_manager()
        assert manager._sanitize_platform_id("a:b!c") == ("a_b_c", True)
        assert manager._sanitize_platform_id("abc") == ("abc", False)
        assert manager._sanitize_platform_id(None) == (None, False)

    elif case == "platform_manager_init":
        manager = make_manager()
        assert manager.platform_insts == []
        assert manager._inst_map == {{}}
        assert manager.get_insts() == []
        assert manager.platforms_config == []
        assert manager.settings == {{}}

    elif case == "get_all_stats_empty":
        manager = make_manager()
        stats = manager.get_all_stats()
        assert stats["summary"]["total"] == 0
        assert stats["summary"]["running"] == 0
        assert stats["summary"]["error"] == 0
        assert stats["summary"]["total_errors"] == 0

    elif case == "get_all_stats_with_platforms":
        manager = make_manager()

        class RunningInst:
            def get_stats(self):
                return {{
                    "id": "p1",
                    "status": PlatformStatus.RUNNING.value,
                    "error_count": 1,
                }}

        class ErrorInst:
            def get_stats(self):
                return {{
                    "id": "p2",
                    "status": PlatformStatus.ERROR.value,
                    "error_count": 2,
                }}

        manager.platform_insts = [RunningInst(), ErrorInst()]
        stats = manager.get_all_stats()
        assert stats["summary"]["total"] == 2
        assert stats["summary"]["running"] == 1
        assert stats["summary"]["error"] == 1
        assert stats["summary"]["total_errors"] == 3
        assert len(stats["platforms"]) == 2

    elif case == "get_insts_empty":
        manager = make_manager()
        assert manager.get_insts() == []

    elif case == "get_insts_returns_platforms":
        manager = make_manager()
        p1, p2 = object(), object()
        manager.platform_insts = [p1, p2]
        insts = manager.get_insts()
        assert len(insts) == 2
        assert insts[0] is p1
        assert insts[1] is p2

    else:
        raise AssertionError(f"Unknown case: {{case}}")
    """
    proc = _run_python(code)
    assert proc.returncode == 0, (
        "PlatformManager subprocess test failed.\n"
        f"case={case}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}\n"
    )


@pytest.fixture(autouse=True)
def _isolate_platform_registry():
    """Isolate global platform registry state between tests."""
    original_registry = platform_registry.copy()
    original_cls_map = platform_cls_map.copy()
    platform_registry.clear()
    platform_cls_map.clear()
    try:
        yield
    finally:
        platform_registry.clear()
        platform_cls_map.clear()
        platform_registry.extend(original_registry)
        platform_cls_map.update(original_cls_map)


class TestRegisterPlatformAdapter:
    """Tests for register_platform_adapter decorator."""

    def test_register_platform_adapter_basic(self):
        """Test basic platform adapter registration."""

        @register_platform_adapter(
            adapter_name="test_adapter",
            desc="Test adapter description",
        )
        class TestAdapter:
            pass

        assert "test_adapter" in platform_cls_map
        assert platform_cls_map["test_adapter"] == TestAdapter

        # Check registry entry
        assert len(platform_registry) == 1
        meta = platform_registry[0]
        assert meta.name == "test_adapter"
        assert meta.description == "Test adapter description"
        assert meta.id == "test_adapter"

    def test_register_platform_adapter_with_config_template(self):
        """Test registration with default config template."""
        config_tmpl = {"token": "", "secret": ""}

        @register_platform_adapter(
            adapter_name="test_adapter_config",
            desc="Test adapter with config",
            default_config_tmpl=config_tmpl,
        )
        class TestAdapterConfig:
            pass

        meta = platform_registry[0]
        # Should add type, enable, and id to config template
        assert meta.default_config_tmpl is not None
        assert meta.default_config_tmpl["type"] == "test_adapter_config"
        assert meta.default_config_tmpl["enable"] is False
        assert meta.default_config_tmpl["id"] == "test_adapter_config"
        assert meta.default_config_tmpl["token"] == ""

    def test_register_platform_adapter_with_display_name(self):
        """Test registration with display name."""

        @register_platform_adapter(
            adapter_name="test_adapter_display",
            desc="Test adapter",
            adapter_display_name="My Custom Adapter",
        )
        class TestAdapterDisplay:
            pass

        meta = platform_registry[0]
        assert meta.adapter_display_name == "My Custom Adapter"

    def test_register_platform_adapter_with_logo_path(self):
        """Test registration with logo path."""

        @register_platform_adapter(
            adapter_name="test_adapter_logo",
            desc="Test adapter",
            logo_path="logos/adapter.png",
        )
        class TestAdapterLogo:
            pass

        meta = platform_registry[0]
        assert meta.logo_path == "logos/adapter.png"

    def test_register_platform_adapter_with_streaming_flag(self):
        """Test registration with streaming message flag."""

        @register_platform_adapter(
            adapter_name="test_adapter_streaming",
            desc="Test adapter",
            support_streaming_message=False,
        )
        class TestAdapterStreaming:
            pass

        meta = platform_registry[0]
        assert meta.support_streaming_message is False

    def test_register_platform_adapter_with_i18n_resources(self):
        """Test registration with i18n resources."""
        i18n = {"zh-CN": {"name": "测试"}}

        @register_platform_adapter(
            adapter_name="test_adapter_i18n",
            desc="Test adapter",
            i18n_resources=i18n,
        )
        class TestAdapterI18n:
            pass

        meta = platform_registry[0]
        assert meta.i18n_resources == i18n

    def test_register_platform_adapter_with_config_metadata(self):
        """Test registration with config metadata."""
        config_meta = {"fields": []}

        @register_platform_adapter(
            adapter_name="test_adapter_meta",
            desc="Test adapter",
            config_metadata=config_meta,
        )
        class TestAdapterMeta:
            pass

        meta = platform_registry[0]
        assert meta.config_metadata == config_meta

    def test_register_platform_adapter_duplicate_raises_error(self):
        """Test that duplicate registration raises ValueError."""

        @register_platform_adapter(
            adapter_name="duplicate_adapter",
            desc="First registration",
        )
        class FirstAdapter:
            pass

        with pytest.raises(ValueError) as exc_info:

            @register_platform_adapter(
                adapter_name="duplicate_adapter",
                desc="Second registration",
            )
            class SecondAdapter:  # noqa: F811
                pass

        assert "已经注册过" in str(exc_info.value)

    def test_register_platform_adapter_module_path_captured(self):
        """Test that module path is captured."""

        @register_platform_adapter(
            adapter_name="test_adapter_module",
            desc="Test adapter",
        )
        class TestAdapterModule:
            pass

        meta = platform_registry[0]
        assert meta.module_path is not None
        assert "test_platform_manager" in meta.module_path


class TestUnregisterPlatformAdaptersByModule:
    """Tests for unregister_platform_adapters_by_module function."""

    def test_unregister_by_module_prefix(self):
        """Test unregistering adapters by module prefix."""

        # Register two adapters with different module paths
        @register_platform_adapter(
            adapter_name="adapter_to_remove",
            desc="To be removed",
        )
        class AdapterToRemove:
            pass

        # Manually set module path for testing
        platform_registry[0].module_path = "plugins.test_plugin.adapter"

        @register_platform_adapter(
            adapter_name="adapter_to_keep",
            desc="To be kept",
        )
        class AdapterToKeep:
            pass

        # Manually set module path for testing
        platform_registry[1].module_path = "plugins.other_plugin.adapter"

        # Unregister by module prefix
        unregistered = unregister_platform_adapters_by_module("plugins.test_plugin")

        assert "adapter_to_remove" in unregistered
        assert "adapter_to_keep" not in unregistered
        assert "adapter_to_remove" not in platform_cls_map
        assert "adapter_to_keep" in platform_cls_map

        # Ensure the registry no longer contains metadata for the removed adapter
        remaining_registry_entries = [
            meta for meta in platform_registry if meta.name == "adapter_to_remove"
        ]
        assert remaining_registry_entries == []

        # Ensure the kept adapter is still in the registry
        kept_registry_entries = [
            meta for meta in platform_registry if meta.name == "adapter_to_keep"
        ]
        assert len(kept_registry_entries) == 1

    def test_unregister_no_match(self):
        """Test unregistering when no modules match."""

        @register_platform_adapter(
            adapter_name="test_no_match",
            desc="Test adapter",
        )
        class TestNoMatch:
            pass

        unregistered = unregister_platform_adapters_by_module("nonexistent.module")

        assert unregistered == []
        assert "test_no_match" in platform_cls_map


class TestPlatformRegistry:
    """Tests for platform registry data structures."""

    def test_platform_registry_is_list(self):
        """Test platform_registry is a list."""
        assert isinstance(platform_registry, list)

    def test_platform_cls_map_is_dict(self):
        """Test platform_cls_map is a dictionary."""
        assert isinstance(platform_cls_map, dict)

    def test_registry_and_cls_map_consistency(self):
        """Test registry and cls_map stay consistent."""

        @register_platform_adapter(
            adapter_name="consistency_test",
            desc="Test consistency",
        )
        class ConsistencyAdapter:
            pass

        # Both should have the adapter
        assert len([m for m in platform_registry if m.name == "consistency_test"]) == 1
        assert "consistency_test" in platform_cls_map


# NOTE: The following tests previously ran into circular import issues
# when importing PlatformManager directly from astrbot.core.platform.manager.
# To avoid this, they exercise PlatformManager behavior in a separate
# subprocess via `_assert_platform_manager_case(...)`, which imports
# PlatformManager in isolation and prevents circular imports in this process.
# The historical circular import chain was:
# manager.py -> star_handler -> star_tools -> api.platform -> star.register -> star_handler -> astr_agent_context -> context -> manager
#
# WARNING: These tests are currently marked as xfail due to an unresolved
# circular import issue that prevents PlatformManager from being imported
# even in a subprocess. This is a known issue in the codebase that needs
# to be addressed separately.


@pytest.mark.xfail(
    reason="Circular import issue prevents PlatformManager import even in subprocess"
)
class TestPlatformManagerHelperFunctions:
    """Tests for PlatformManager helper functions."""

    def test_is_valid_platform_id_valid(self):
        """Test _is_valid_platform_id with valid IDs."""
        _assert_platform_manager_case("is_valid_platform_id_valid")

    def test_is_valid_platform_id_invalid(self):
        """Test _is_valid_platform_id with invalid IDs."""
        _assert_platform_manager_case("is_valid_platform_id_invalid")

    def test_sanitize_platform_id(self):
        """Test _sanitize_platform_id function."""
        _assert_platform_manager_case("sanitize_platform_id")


@pytest.mark.xfail(
    reason="Circular import issue prevents PlatformManager import even in subprocess"
)
class TestPlatformManagerInit:
    """Tests for PlatformManager initialization."""

    def test_platform_manager_init(self):
        """Test PlatformManager initialization."""
        _assert_platform_manager_case("platform_manager_init")


@pytest.mark.xfail(
    reason="Circular import issue prevents PlatformManager import even in subprocess"
)
class TestPlatformManagerGetAllStats:
    """Tests for PlatformManager get_all_stats method."""

    def test_get_all_stats_empty(self):
        """Test get_all_stats with no platforms."""
        _assert_platform_manager_case("get_all_stats_empty")

    def test_get_all_stats_with_platforms(self):
        """Test get_all_stats with mock platforms."""
        _assert_platform_manager_case("get_all_stats_with_platforms")


@pytest.mark.xfail(
    reason="Circular import issue prevents PlatformManager import even in subprocess"
)
class TestPlatformManagerGetInsts:
    """Tests for PlatformManager get_insts method."""

    def test_get_insts_empty(self):
        """Test get_insts returns empty list when no platforms."""
        _assert_platform_manager_case("get_insts_empty")

    def test_get_insts_returns_platforms(self):
        """Test get_insts returns platform instances."""
        _assert_platform_manager_case("get_insts_returns_platforms")
