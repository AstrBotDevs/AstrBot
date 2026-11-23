"""Current defaults remain valid, isolated, and unchanged by migration."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

from astrbot import __version__
from astrbot.core.config.agent import get_runtime_config_default
from astrbot.core.config.default import (
    DB_PATH,
    DEFAULT_CONFIG,
    DEFAULT_VALUE_MAP,
    VERSION,
    WEBHOOK_SUPPORTED_PLATFORMS,
)
from astrbot.core.utils.migra_helper import migrate_config_on_load


class TestVersionConstant:
    """Tests for the VERSION constant."""

    def test_version_format(self):
        assert VERSION == __version__
        assert re.fullmatch(
            r"\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
            r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?",
            VERSION,
        )


class TestDBPath:
    """Tests for DB_PATH."""

    def test_db_path_uses_data_directory_and_current_filename(self):
        path = Path(DB_PATH)
        assert path.name == "data_v4.db"
        assert path.parent.name == "data"


class TestDEFAULT_VALUE_MAP:
    """Tests for DEFAULT_VALUE_MAP structure."""

    def test_contains_expected_types(self):
        expected = {
            "int",
            "float",
            "bool",
            "string",
            "text",
            "list",
            "file",
            "object",
            "dict",
            "template_list",
        }
        assert set(DEFAULT_VALUE_MAP.keys()) == expected

    def test_default_values_are_correct_types(self):
        assert isinstance(DEFAULT_VALUE_MAP["int"], int)
        assert isinstance(DEFAULT_VALUE_MAP["float"], float)
        assert isinstance(DEFAULT_VALUE_MAP["bool"], bool)
        assert isinstance(DEFAULT_VALUE_MAP["string"], str)
        assert isinstance(DEFAULT_VALUE_MAP["text"], str)
        assert isinstance(DEFAULT_VALUE_MAP["list"], list)
        assert isinstance(DEFAULT_VALUE_MAP["file"], list)
        assert isinstance(DEFAULT_VALUE_MAP["object"], dict)
        assert isinstance(DEFAULT_VALUE_MAP["dict"], dict)
        assert isinstance(DEFAULT_VALUE_MAP["template_list"], list)

    def test_specific_default_values(self):
        assert DEFAULT_VALUE_MAP["int"] == 0
        assert DEFAULT_VALUE_MAP["float"] == 0.0
        assert DEFAULT_VALUE_MAP["bool"] is False
        assert DEFAULT_VALUE_MAP["string"] == ""
        assert DEFAULT_VALUE_MAP["list"] == []
        assert DEFAULT_VALUE_MAP["object"] == {}
        assert DEFAULT_VALUE_MAP["dict"] == {}
        assert DEFAULT_VALUE_MAP["template_list"] == []


class TestWEBHOOK_SUPPORTED_PLATFORMS:
    """Tests for the webhook platforms list."""

    def test_is_list_of_strings(self):
        assert isinstance(WEBHOOK_SUPPORTED_PLATFORMS, list)
        for p in WEBHOOK_SUPPORTED_PLATFORMS:
            assert isinstance(p, str)

    def test_contains_key_platforms(self):
        assert "qq_official_webhook" in WEBHOOK_SUPPORTED_PLATFORMS
        assert "weixin_official_account" in WEBHOOK_SUPPORTED_PLATFORMS
        assert "slack" in WEBHOOK_SUPPORTED_PLATFORMS
        assert "lark" in WEBHOOK_SUPPORTED_PLATFORMS


class TestDEFAULT_CONFIGStructure:
    """Tests for the top-level keys and nested structure of DEFAULT_CONFIG."""

    def test_top_level_keys(self):
        expected_keys = {
            "config_version",
            "platform_settings",
            "provider_sources",
            "provider",
            "provider_settings",
            "agent",
            "provider_stt_settings",
            "provider_tts_settings",
            "provider_ltm_settings",
            "content_safety",
            "admins_id",
            "t2i",
            "http_proxy",
            "no_proxy",
            "dashboard",
            "platform",
            "platform_specific",
            "wake_prefix",
            "log_level",
            "persona",
            "timezone",
            "callback_api_base",
            "default_kb_collection",
            "plugin_set",
            "kb_names",
            "kb_fusion_top_k",
            "kb_final_top_k",
            "kb_agentic_mode",
            "disable_builtin_commands",
            "t2i_word_threshold",
            "t2i_strategy",
            "t2i_endpoint",
            "t2i_use_file_service",
            "t2i_active_template",
            "log_file_enable",
            "log_file_path",
            "log_file_max_mb",
            "temp_dir_max_size",
            "trace_enable",
            "trace_db_path",
            "trace_db_max_mb",
            "trace_retention_days",
            "pip_install_arg",
            "pypi_index_url",
        }
        for key in expected_keys:
            assert key in DEFAULT_CONFIG, f"Missing top-level key: {key}"

    def test_current_defaults_do_not_require_migration(self, tmp_path):
        config = deepcopy(DEFAULT_CONFIG)
        assert config["config_version"] == 6
        assert migrate_config_on_load(config, tmp_path / "config.json") is False
        assert config == DEFAULT_CONFIG
        assert not (tmp_path / "config.subagents-migration.json").exists()

    def test_platform_settings_structure(self):
        ps = DEFAULT_CONFIG["platform_settings"]
        assert "unique_session" in ps
        assert "rate_limit" in ps
        assert "reply_prefix" in ps
        assert isinstance(ps["rate_limit"], dict)
        assert ps["rate_limit"]["strategy"] in ("stall", "discard")

    def test_provider_ltm_settings_structure(self):
        ltm = DEFAULT_CONFIG["provider_ltm_settings"]
        assert "group_icl_enable" in ltm
        assert "group_message_max_cnt" in ltm
        assert "image_caption" in ltm
        assert "active_reply" in ltm
        assert isinstance(ltm["active_reply"], dict)
        assert ltm["active_reply"]["method"] == "possibility_reply"

    def test_dashboard_settings(self):
        dash = DEFAULT_CONFIG["dashboard"]
        assert dash["enable"] is True
        assert dash["username"] == "astrbot"
        assert dash["port"] == 6185
        assert "ssl" in dash

    def test_provider_settings_defaults(self):
        ps = DEFAULT_CONFIG["provider_settings"]
        assert ps["enable"] is True
        agent = DEFAULT_CONFIG["agent"]
        assert agent["runtime"] == "astrbot"
        assert agent["config"]["model"]["provider_id"] == ""
        assert agent["config"]["persona"]["safety_mode"] is True

    def test_admins_id_default(self):
        assert DEFAULT_CONFIG["admins_id"] == ["astrbot"]

    def test_wake_prefix_default(self):
        assert DEFAULT_CONFIG["wake_prefix"] == ["/"]

    def test_log_level_default(self):
        assert DEFAULT_CONFIG["log_level"] == "INFO"

    def test_platform_specific_contains_lark_telegram_discord(self):
        ps = DEFAULT_CONFIG["platform_specific"]
        assert "lark" in ps
        assert "telegram" in ps
        assert "discord" in ps

    def test_no_proxy_contains_localhost(self):
        assert "localhost" in DEFAULT_CONFIG["no_proxy"]

    def test_subagent_defaults_are_disabled_and_independent(self):
        defaults = get_runtime_config_default("astrbot")
        assert defaults["subagents"] == {
            "enabled": False,
            "config_ids": [],
            "max_concurrent_agents": 3,
            "task_timeout": 600,
        }
        defaults["subagents"]["config_ids"].append("test-agent")
        assert get_runtime_config_default("astrbot")["subagents"]["config_ids"] == []
        assert DEFAULT_CONFIG["agent"]["config"]["subagents"]["config_ids"] == []
        assert "subagent_orchestrator" not in DEFAULT_CONFIG

    def test_quoted_message_parser_defaults(self):
        qmp = DEFAULT_CONFIG["provider_settings"]["quoted_message_parser"]
        assert qmp["max_component_chain_depth"] == 4
        assert qmp["max_forward_node_depth"] == 6
        assert qmp["max_forward_fetch"] == 32

    def test_sandbox_defaults(self):
        sb = DEFAULT_CONFIG["provider_settings"]["sandbox"]
        assert sb["booter"] == "shipyard_neo"
        assert sb["shipyard_neo_ttl"] == 3600
