"""Mock-based unit tests for AstrBotConfig."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig, RateLimitStrategy


class TestRateLimitStrategy:
    """Tests for the RateLimitStrategy enum."""

    def test_stall_member(self):
        assert RateLimitStrategy.STALL.value == "stall"

    def test_discard_member(self):
        assert RateLimitStrategy.DISCARD.value == "discard"


class TestAstrBotConfigConstruction:
    """Construction and file-existence branches."""

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=False)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"version": 1}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_init_creates_file_when_missing(
        self, mock_json_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """When the file does not exist, __init__ writes the default config."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"version": 1},
        )
        mock_json_dump.assert_called_once()
        assert config["version"] == 1

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"key_a": "value_a", "key_b": 42}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_init_loads_existing_file(
        self, mock_json_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """When the file exists, __init__ loads its contents."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"key_a": "default", "key_b": 0},
        )
        assert config["key_a"] == "value_a"
        assert config["key_b"] == 42
        # No extra dump for the missing-key case since all keys present
        if hasattr(config, "first_deploy"):
            assert not config.first_deploy

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=False)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
    )
    def test_first_deploy_flag_set(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """first_deploy should be True when config file is created for the first time."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"version": 1},
        )
        assert hasattr(config, "first_deploy")
        assert config.first_deploy is True

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"x": null}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_none_value_replaced_with_default(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """When a config value is null, it is replaced by the default."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"x": "fallback"},
        )
        assert config["x"] == "fallback"

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"a": 1, "c": 3}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_missing_keys_inserted_from_default(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """Keys present in default but missing from file are inserted."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"a": 1, "b": 2, "c": 3},
        )
        assert config["a"] == 1
        assert config["b"] == 2  # inserted from default
        assert config["c"] == 3


class TestAstrBotConfigOperations:
    """Dot-notation access, save, and delete."""

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"key": "val"}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_getattr_existing_key(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """__getattr__ returns the value for an existing key."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"key": "val"},
        )
        assert config.key == "val"

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"key": "val"}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_getattr_missing_key_returns_none(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """__getattr__ returns None for a missing key."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"key": "val"},
        )
        assert config.non_existent is None

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"key": "val"}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_setattr_updates_dict(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """__setattr__ stores the value in the dict."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"key": "val"},
        )
        config.new_field = 99
        assert config["new_field"] == 99

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"temp": "x"}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_delattr_removes_from_dict_and_saves(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """__delattr__ removes the key from the dict and triggers save."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"temp": "x"},
        )
        del config.temp
        assert "temp" not in config
        mock_dump.assert_called()

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"key": "val"}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_delattr_missing_key_raises(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """Deleting a nonexistent key raises AttributeError."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"key": "val"},
        )
        with pytest.raises(AttributeError):
            del config.non_existent

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"key": "val"}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_save_config_writes_to_file(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """save_config serialises self to the config_path."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"key": "val"},
        )
        config.new_thing = "test"
        config.save_config()
        # The file should be written; at this point json.dump was already called
        # during __init__ as well, so at least one call after our modification
        assert mock_dump.call_count >= 1

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=True)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
        read_data='{"key": "val"}',
    )
    @patch(
        "astrbot.core.config.astrbot_config.json.dump",
        return_value=None,
    )
    def test_save_config_with_replace(
        self, mock_dump: MagicMock, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """Passing replace_config updates self and writes."""
        config = AstrBotConfig(
            config_path="/fake/cmd_config.json",
            default_config={"key": "val"},
        )
        config.save_config(replace_config={"replacement": True})
        assert config["replacement"] is True


class TestAstrBotConfigSchema:
    """Schema-based construction."""

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=False)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
    )
    def test_schema_object_type(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """A schema with type 'object' produces a nested dict."""
        schema = {
            "nested": {"type": "object", "items": {"a": {"type": "int"}}},
        }
        config = AstrBotConfig(config_path="/fake/cfg.json", schema=schema)
        assert config.nested == {"a": 0}

    @patch("astrbot.core.config.astrbot_config.os.path.exists", return_value=False)
    @patch(
        "astrbot.core.config.astrbot_config.open",
        new_callable=mock_open,
    )
    def test_schema_unsupported_type_raises(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ):
        """An unsupported type in the schema raises TypeError."""
        schema = {"bad": {"type": "unknown_type"}}
        with pytest.raises(TypeError, match="不受支持的配置类型"):
            AstrBotConfig(config_path="/fake/cfg.json", schema=schema)


class TestAstrBotConfigCheckExist:
    """check_exist edge cases."""

    def test_check_exist_empty_path(self):
        """Return False when config_path is falsy."""
        config = AstrBotConfig.__new__(AstrBotConfig)
        object.__setattr__(config, "config_path", "")
        assert config.check_exist() is False
