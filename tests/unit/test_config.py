"""Tests for config module."""

import asyncio
import json
import os
import threading

import pytest

from astrbot.core.config.astrbot_config import AstrBotConfig, RateLimitStrategy
from astrbot.core.config.default import DEFAULT_VALUE_MAP
from astrbot.core.config.i18n_utils import ConfigMetadataI18n
from astrbot.core.utils.auth_password import (
    DEFAULT_DASHBOARD_PASSWORD,
    hash_dashboard_password,
    hash_md5_dashboard_password,
    validate_dashboard_password,
    verify_dashboard_password,
)


@pytest.fixture
def temp_config_path(tmp_path):
    """Create a temporary config path."""
    return str(tmp_path / "test_config.json")


@pytest.fixture
def minimal_default_config():
    """Create a minimal default config for testing."""
    return {
        "config_version": 2,
        "platform_settings": {
            "unique_session": False,
            "rate_limit": {
                "time": 60,
                "count": 30,
                "strategy": "stall",
            },
        },
        "provider_settings": {
            "enable": True,
            "default_provider_id": "",
        },
    }


class TestRateLimitStrategy:
    """Tests for RateLimitStrategy enum."""

    def test_stall_value(self):
        """Test stall enum value."""
        assert RateLimitStrategy.STALL.value == "stall"

    def test_discard_value(self):
        """Test discard enum value."""
        assert RateLimitStrategy.DISCARD.value == "discard"


class TestAstrBotConfigLoad:
    """Tests for AstrBotConfig loading and initialization."""

    def test_init_creates_file_if_not_exists(
        self, temp_config_path, minimal_default_config
    ):
        """Test that config file is created when it doesn't exist."""
        assert not os.path.exists(temp_config_path)

        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert os.path.exists(temp_config_path)
        assert config.config_version == 2
        assert config.platform_settings["unique_session"] is False

    def test_init_loads_existing_file(self, temp_config_path, minimal_default_config):
        """Test that existing config file is loaded."""
        existing_config = {
            "config_version": 2,
            "platform_settings": {"unique_session": True},
            "provider_settings": {"enable": False},
        }
        with open(temp_config_path, "w", encoding="utf-8-sig") as f:
            json.dump(existing_config, f)

        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert config.platform_settings["unique_session"] is True
        assert config.provider_settings["enable"] is False

    def test_first_deploy_flag(self, temp_config_path, minimal_default_config):
        """Test first_deploy flag is set for new config."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert hasattr(config, "first_deploy")
        assert config.first_deploy is True

    def test_init_with_schema(self, temp_config_path):
        """Test initialization with schema."""
        schema = {
            "test_field": {
                "type": "string",
                "default": "test_value",
            },
            "nested": {
                "type": "object",
                "items": {
                    "enabled": {"type": "bool"},
                    "count": {"type": "int"},
                },
            },
        }

        config = AstrBotConfig(config_path=temp_config_path, schema=schema)

        assert config.test_field == "test_value"
        assert config.nested["enabled"] is False
        assert config.nested["count"] == 0

    def test_dot_notation_access(self, temp_config_path, minimal_default_config):
        """Test accessing config values using dot notation."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert config.platform_settings is not None
        assert config.non_existent_field is None

    def test_setattr_updates_config(self, temp_config_path, minimal_default_config):
        """Test that setting attributes updates config."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        config.new_field = "new_value"

        assert config.new_field == "new_value"

    def test_delattr_removes_field(self, temp_config_path, minimal_default_config):
        """Test that deleting attributes removes them."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        config.temp_field = "temp"

        del config.temp_field

        # Accessing a deleted field returns None due to __getattr__
        assert config.temp_field is None
        # But the field is removed from the dict
        assert "temp_field" not in config

    def test_delattr_saves_config(self, temp_config_path, minimal_default_config):
        """Test that deleting attributes saves config to file."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        config.temp_field = "temp"
        del config.temp_field

        with open(temp_config_path, encoding="utf-8-sig") as f:
            loaded_config = json.load(f)

        assert "temp_field" not in loaded_config

    def test_check_exist(self, temp_config_path, minimal_default_config):
        """Test check_exist method."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert config.check_exist() is True

        # Create a path that definitely doesn't exist
        import pathlib

        temp_dir = pathlib.Path(temp_config_path).parent
        non_existent_path = str(temp_dir / "non_existent_config.json")

        # Check that the file doesn't exist before creating config
        assert not os.path.exists(non_existent_path)

        # Create config which will auto-create the file
        config2 = AstrBotConfig(
            config_path=non_existent_path, default_config=minimal_default_config
        )

        # Now it exists
        assert config2.check_exist() is True
        assert os.path.exists(non_existent_path)

    def test_empty_dashboard_password_generates_random_password(self, temp_config_path):
        """Test that an empty dashboard password is replaced with a random password."""
        default_config = {
            "dashboard": {
                "username": "astrbot",
                "password": "",
            },
        }

        config = AstrBotConfig(
            config_path=temp_config_path,
            default_config=default_config,
        )

        generated_password = getattr(config, "_generated_dashboard_password", None)
        assert isinstance(generated_password, str)
        validate_dashboard_password(generated_password)
        assert verify_dashboard_password(
            config["dashboard"]["pbkdf2_password"],
            generated_password,
        )
        assert config["dashboard"]["pbkdf2_password"].startswith(
            "pbkdf2_sha256$600000$"
        )
        assert config["dashboard"]["password_change_required"] is True
        assert config["dashboard"]["password_storage_upgraded"] is True
        assert (
            getattr(config, "_generated_dashboard_password_change_required", False)
            is True
        )
        assert not verify_dashboard_password(
            config["dashboard"]["pbkdf2_password"],
            DEFAULT_DASHBOARD_PASSWORD,
        )
        assert verify_dashboard_password(
            config["dashboard"]["password"],
            generated_password,
        )

    def test_empty_dashboard_password_uses_initial_password_env(
        self, temp_config_path, monkeypatch
    ):
        """Test that the generated dashboard password can be provided by env."""
        env_password = "CustomInitial123"
        monkeypatch.setenv("ASTRBOT_DASHBOARD_INITIAL_PASSWORD", env_password)
        default_config = {
            "dashboard": {
                "username": "astrbot",
                "password": "",
            },
        }

        config = AstrBotConfig(
            config_path=temp_config_path,
            default_config=default_config,
        )

        assert getattr(config, "_generated_dashboard_password", None) == env_password
        assert verify_dashboard_password(
            config["dashboard"]["pbkdf2_password"],
            env_password,
        )
        assert verify_dashboard_password(
            config["dashboard"]["password"],
            env_password,
        )
        assert config["dashboard"]["password_change_required"] is True

    def test_initial_dashboard_password_env_must_be_valid(
        self, temp_config_path, monkeypatch
    ):
        """Test that weak env-provided initial passwords fail fast."""
        monkeypatch.setenv("ASTRBOT_DASHBOARD_INITIAL_PASSWORD", "weak")
        default_config = {
            "dashboard": {
                "username": "astrbot",
                "password": "",
            },
        }

        with pytest.raises(ValueError, match="Password must be at least"):
            AstrBotConfig(
                config_path=temp_config_path,
                default_config=default_config,
            )

    def test_legacy_password_change_required_rotates_and_keeps_config_flag(
        self, temp_config_path
    ):
        """Test that the setup flag stays in dashboard config."""
        default_config = {
            "dashboard": {
                "username": "astrbot",
                "password": "",
                "pbkdf2_password": "",
            },
        }
        with open(temp_config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "dashboard": {
                        "username": "astrbot",
                        "password": "",
                        "pbkdf2_password": "pbkdf2_sha256$600000$00$00",
                        "password_change_required": True,
                    }
                },
                f,
            )

        config = AstrBotConfig(
            config_path=temp_config_path,
            default_config=default_config,
        )
        generated_password = getattr(config, "_generated_dashboard_password", None)

        assert isinstance(generated_password, str)
        assert config["dashboard"]["password_change_required"] is True
        assert config["dashboard"]["password_storage_upgraded"] is True
        assert (
            getattr(config, "_dashboard_password_change_required_from_config", False)
            is True
        )
        assert verify_dashboard_password(
            config["dashboard"]["pbkdf2_password"], generated_password
        )
        assert verify_dashboard_password(
            config["dashboard"]["password"], generated_password
        )

    def test_reset_dashboard_password_env_rotates_existing_password(
        self, temp_config_path, monkeypatch
    ):
        """Test startup reset flag rotates an already configured dashboard password."""
        old_password = "OldPassword123"
        default_config = {
            "dashboard": {
                "username": "astrbot",
                "password": "",
                "pbkdf2_password": "",
            },
        }
        with open(temp_config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "dashboard": {
                        "username": "astrbot",
                        "password": hash_md5_dashboard_password(old_password),
                        "pbkdf2_password": hash_dashboard_password(old_password),
                        "password_change_required": False,
                        "password_storage_upgraded": True,
                    }
                },
                f,
            )

        monkeypatch.setenv("ASTRBOT_RESET_DASHBOARD_PASSWORD", "1")
        config = AstrBotConfig(
            config_path=temp_config_path,
            default_config=default_config,
        )
        generated_password = getattr(config, "_generated_dashboard_password", None)

        assert isinstance(generated_password, str)
        assert config["dashboard"]["password_change_required"] is True
        assert config["dashboard"]["password_storage_upgraded"] is True
        assert "ASTRBOT_RESET_DASHBOARD_PASSWORD" not in os.environ
        assert verify_dashboard_password(
            config["dashboard"]["pbkdf2_password"], generated_password
        )
        assert not verify_dashboard_password(
            config["dashboard"]["pbkdf2_password"], old_password
        )
        assert verify_dashboard_password(
            config["dashboard"]["password"], generated_password
        )

    def test_legacy_astrbot_user_without_change_flag_keeps_legacy_password(
        self, temp_config_path
    ):
        """Test old MD5 configs keep legacy auth until the manual upgrade."""
        default_config = {
            "dashboard": {
                "username": "astrbot",
                "password": "",
                "pbkdf2_password": "",
            },
        }
        with open(temp_config_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "dashboard": {
                        "username": "astrbot",
                        "password": "77b90590a8945a7d36c963981a307dc9",
                    }
                },
                f,
            )

        config = AstrBotConfig(
            config_path=temp_config_path,
            default_config=default_config,
        )
        generated_password = getattr(config, "_generated_dashboard_password", None)

        assert generated_password is None
        assert config["dashboard"]["pbkdf2_password"] == ""
        assert verify_dashboard_password(
            config["dashboard"]["password"], DEFAULT_DASHBOARD_PASSWORD
        )

    def test_legacy_md5_password_requires_plain_password(self):
        """Test that a leaked legacy MD5 hash cannot be used as the login password."""
        legacy_hash = "77b90590a8945a7d36c963981a307dc9"

        assert verify_dashboard_password(legacy_hash, DEFAULT_DASHBOARD_PASSWORD)
        assert not verify_dashboard_password(legacy_hash, legacy_hash)


class TestConfigValidation:
    """Tests for config validation and integrity checking."""

    def test_insert_missing_config_items(
        self, temp_config_path, minimal_default_config
    ):
        """Test that missing config items are inserted with default values."""
        existing_config = {"config_version": 2}
        with open(temp_config_path, "w", encoding="utf-8-sig") as f:
            json.dump(existing_config, f)

        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert "platform_settings" in config
        assert "provider_settings" in config

    def test_replace_none_with_default(self, temp_config_path, minimal_default_config):
        """Test that None values are replaced with defaults."""
        existing_config = {
            "config_version": 2,
            "platform_settings": None,
            "provider_settings": None,
        }
        with open(temp_config_path, "w", encoding="utf-8-sig") as f:
            json.dump(existing_config, f)

        AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        # Reload to verify the values were replaced
        config2 = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert config2.platform_settings is not None
        assert config2.provider_settings is not None

    def test_reorder_config_keys(self, temp_config_path, minimal_default_config):
        """Test that config keys are reordered to match default."""
        existing_config = {
            "provider_settings": {"enable": True},
            "config_version": 2,
            "platform_settings": {"unique_session": False},
        }
        with open(temp_config_path, "w", encoding="utf-8-sig") as f:
            json.dump(existing_config, f)

        AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        with open(temp_config_path, encoding="utf-8-sig") as f:
            loaded_config = json.load(f)

        keys = list(loaded_config.keys())
        assert keys[0] == "config_version"
        assert keys[1] == "platform_settings"
        assert keys[2] == "provider_settings"

    def test_remove_unknown_config_keys(self, temp_config_path, minimal_default_config):
        """Test that unknown config keys are removed."""
        existing_config = {
            "config_version": 2,
            "platform_settings": {},
            "unknown_key": "should_be_removed",
        }
        with open(temp_config_path, "w", encoding="utf-8-sig") as f:
            json.dump(existing_config, f)

        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert "unknown_key" not in config

    def test_nested_config_validation(self, temp_config_path):
        """Test validation of nested config structures."""
        default_config = {
            "nested": {
                "level1": {
                    "level2": {
                        "value": 42,
                    },
                },
            },
        }

        existing_config = {
            "nested": {
                "level1": {},  # Missing level2
            },
        }
        with open(temp_config_path, "w", encoding="utf-8-sig") as f:
            json.dump(existing_config, f)

        config = AstrBotConfig(
            config_path=temp_config_path, default_config=default_config
        )

        assert "level2" in config.nested["level1"]
        assert config.nested["level1"]["level2"]["value"] == 42

    def test_integrity_log_does_not_include_inserted_secret_value(
        self, temp_config_path, monkeypatch
    ):
        """Default values may contain secrets and should not be logged."""
        from astrbot.core.config import astrbot_config

        existing_config = {}
        default_config = {"api_key": "secret-value"}
        messages = []
        with open(temp_config_path, "w", encoding="utf-8-sig") as f:
            json.dump(existing_config, f)

        def capture_info(message, *args):
            messages.append(message % args if args else message)

        monkeypatch.setattr(astrbot_config.logger, "info", capture_info)

        AstrBotConfig(config_path=temp_config_path, default_config=default_config)

        assert messages
        assert all("secret-value" not in message for message in messages)
        assert all("api_key" not in message for message in messages)
        assert any("Config key missing" in message for message in messages)


class TestConfigHotReload:
    """Tests for config hot reload functionality."""

    def test_save_config(self, temp_config_path, minimal_default_config):
        """Test saving config to file."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        config.new_field = "new_value"
        config.save_config()

        with open(temp_config_path, encoding="utf-8-sig") as f:
            loaded_config = json.load(f)

        assert loaded_config["new_field"] == "new_value"

    @pytest.mark.asyncio
    async def test_save_config_async_keeps_event_loop_responsive(
        self, temp_config_path, minimal_default_config, monkeypatch
    ):
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        write_started = threading.Event()
        finish_write = threading.Event()
        original_fsync = os.fsync

        def blocking_fsync(fd):
            write_started.set()
            assert finish_write.wait(timeout=5)
            original_fsync(fd)

        monkeypatch.setattr(os, "fsync", blocking_fsync)
        config["async_field"] = "saved"

        save_task = asyncio.create_task(config.save_config_async())
        assert await asyncio.to_thread(write_started.wait, 5)
        await asyncio.sleep(0)
        assert not save_task.done()

        finish_write.set()
        await save_task

        with open(temp_config_path, encoding="utf-8-sig") as f:
            assert json.load(f)["async_field"] == "saved"

    @pytest.mark.asyncio
    async def test_save_config_async_writes_stable_snapshot(
        self, temp_config_path, minimal_default_config, monkeypatch
    ):
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        dump_started = threading.Event()
        finish_dump = threading.Event()
        original_dump = json.dump

        def blocking_dump(snapshot, file_obj, **kwargs):
            dump_started.set()
            assert finish_dump.wait(timeout=5)
            original_dump(snapshot, file_obj, **kwargs)

        monkeypatch.setattr(json, "dump", blocking_dump)
        config["snapshot_field"] = "captured"

        save_task = asyncio.create_task(config.save_config_async())
        assert await asyncio.to_thread(dump_started.wait, 5)
        config["snapshot_field"] = "changed-after-save-started"
        finish_dump.set()
        await save_task

        with open(temp_config_path, encoding="utf-8-sig") as f:
            assert json.load(f)["snapshot_field"] == "captured"

    @pytest.mark.asyncio
    async def test_save_config_async_does_not_block_next_snapshot_during_replace(
        self, temp_config_path, minimal_default_config, monkeypatch
    ):
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        first_replace_started = threading.Event()
        finish_first_replace = threading.Event()
        replace_call_count = 0
        replace_call_lock = threading.Lock()
        original_replace = os.replace

        def blocking_replace(source, destination):
            nonlocal replace_call_count
            with replace_call_lock:
                replace_call_count += 1
                call_number = replace_call_count
            if call_number == 1:
                first_replace_started.set()
                if not finish_first_replace.wait(timeout=2):
                    raise TimeoutError("event loop could not prepare the next snapshot")
            original_replace(source, destination)

        monkeypatch.setattr(os, "replace", blocking_replace)
        config["replace_order"] = "older"
        older_save = asyncio.create_task(config.save_config_async())
        assert await asyncio.to_thread(first_replace_started.wait, 5)

        config["replace_order"] = "newer"
        newer_save = asyncio.create_task(config.save_config_async())
        await asyncio.sleep(0)
        finish_first_replace.set()
        await asyncio.gather(older_save, newer_save)

        with open(temp_config_path, encoding="utf-8-sig") as f:
            assert json.load(f)["replace_order"] == "newer"

    @pytest.mark.asyncio
    async def test_save_config_async_discards_older_late_write(
        self, temp_config_path, minimal_default_config, monkeypatch
    ):
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        first_write_started = threading.Event()
        finish_first_write = threading.Event()
        fsync_call_count = 0
        fsync_call_lock = threading.Lock()
        original_fsync = os.fsync

        def reorder_fsync(fd):
            nonlocal fsync_call_count
            with fsync_call_lock:
                fsync_call_count += 1
                call_number = fsync_call_count
            if call_number == 1:
                first_write_started.set()
                assert finish_first_write.wait(timeout=5)
            original_fsync(fd)

        monkeypatch.setattr(os, "fsync", reorder_fsync)
        config["save_order"] = "older"
        older_save = asyncio.create_task(config.save_config_async())
        assert await asyncio.to_thread(first_write_started.wait, 5)

        config["save_order"] = "newer"
        newer_save_committed = await config.save_config_async()
        finish_first_write.set()
        older_save_committed = await older_save

        assert newer_save_committed is True
        assert older_save_committed is False
        with open(temp_config_path, encoding="utf-8-sig") as f:
            assert json.load(f)["save_order"] == "newer"

    @pytest.mark.asyncio
    async def test_save_config_commits_older_snapshot_when_newer_write_fails(
        self, temp_config_path, minimal_default_config, monkeypatch
    ):
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        first_write_started = threading.Event()
        finish_first_write = threading.Event()
        fsync_call_count = 0
        fsync_call_lock = threading.Lock()
        original_fsync = os.fsync

        def fail_newer_fsync(fd):
            nonlocal fsync_call_count
            with fsync_call_lock:
                fsync_call_count += 1
                call_number = fsync_call_count
            if call_number == 1:
                first_write_started.set()
                assert finish_first_write.wait(timeout=5)
                original_fsync(fd)
                return
            raise OSError("simulated newer fsync failure")

        monkeypatch.setattr(os, "fsync", fail_newer_fsync)
        config["save_order"] = "older-valid"
        older_save = asyncio.create_task(asyncio.to_thread(config.save_config))
        assert await asyncio.to_thread(first_write_started.wait, 5)

        config["save_order"] = "newer-failed"
        with pytest.raises(OSError, match="simulated newer fsync failure"):
            await config.save_config_async()

        finish_first_write.set()
        await older_save

        with open(temp_config_path, encoding="utf-8-sig") as f:
            assert json.load(f)["save_order"] == "older-valid"

    def test_save_config_with_replace(self, temp_config_path, minimal_default_config):
        """Test saving config with replacement."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        replacement_config = {
            "replaced": True,
            "extra_field": "value",
        }
        config.save_config(replace_config=replacement_config)

        with open(temp_config_path, encoding="utf-8-sig") as f:
            loaded_config = json.load(f)

        # The replacement config is merged with existing config
        assert loaded_config["replaced"] is True
        assert loaded_config["extra_field"] == "value"
        # Original fields are preserved because update merges
        assert "platform_settings" in loaded_config

    def test_save_config_preserves_existing_file_when_write_fails(
        self, temp_config_path, minimal_default_config, monkeypatch
    ):
        """Config saves should not corrupt the existing file on write failure."""
        config = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        with open(temp_config_path, encoding="utf-8-sig") as f:
            original_content = f.read()

        def failing_dump(*args, **kwargs):
            file_obj = args[1]
            file_obj.write("{")
            raise RuntimeError("simulated interrupted write")

        config.new_field = "new_value"
        monkeypatch.setattr(
            "astrbot.core.config.astrbot_config.json.dump",
            failing_dump,
        )

        with pytest.raises(RuntimeError, match="simulated interrupted write"):
            config.save_config()

        with open(temp_config_path, encoding="utf-8-sig") as f:
            assert f.read() == original_content
        assert [
            entry.name
            for entry in os.scandir(os.path.dirname(temp_config_path))
            if entry.name != os.path.basename(temp_config_path)
        ] == []

    def test_modification_persists_after_reload(
        self, temp_config_path, minimal_default_config
    ):
        """Test that modifications persist after reloading."""
        config1 = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )
        config1.platform_settings["unique_session"] = True
        config1.save_config()

        config2 = AstrBotConfig(
            config_path=temp_config_path, default_config=minimal_default_config
        )

        assert config2.platform_settings["unique_session"] is True


class TestConfigSchemaToDefault:
    """Tests for schema to default config conversion."""

    def test_convert_schema_with_defaults(self, temp_config_path):
        """Test converting schema with explicit defaults."""
        schema = {
            "string_field": {"type": "string", "default": "custom"},
            "int_field": {"type": "int", "default": 100},
            "bool_field": {"type": "bool", "default": True},
        }

        config = AstrBotConfig(config_path=temp_config_path, schema=schema)

        assert config.string_field == "custom"
        assert config.int_field == 100
        assert config.bool_field is True

    def test_convert_schema_without_defaults(self, temp_config_path):
        """Test converting schema using default value map."""
        schema = {
            "string_field": {"type": "string"},
            "int_field": {"type": "int"},
            "bool_field": {"type": "bool"},
        }

        config = AstrBotConfig(config_path=temp_config_path, schema=schema)

        assert config.string_field == DEFAULT_VALUE_MAP["string"]
        assert config.int_field == DEFAULT_VALUE_MAP["int"]
        assert config.bool_field == DEFAULT_VALUE_MAP["bool"]

    def test_unsupported_schema_type_raises_error(self, temp_config_path):
        """Test that unsupported schema types raise error."""
        schema = {
            "field": {"type": "unsupported_type"},
        }

        with pytest.raises(TypeError, match="不受支持的配置类型"):
            AstrBotConfig(config_path=temp_config_path, schema=schema)

    def test_template_list_type(self, temp_config_path):
        """Test template_list schema type."""
        schema = {
            "templates": {"type": "template_list", "default": []},
        }

        config = AstrBotConfig(config_path=temp_config_path, schema=schema)

        assert config.templates == []

    def test_nested_object_schema(self, temp_config_path):
        """Test nested object schema conversion."""
        schema = {
            "nested": {
                "type": "object",
                "items": {
                    "field1": {"type": "string"},
                    "field2": {"type": "int"},
                },
            },
        }

        config = AstrBotConfig(config_path=temp_config_path, schema=schema)

        assert config.nested["field1"] == ""
        assert config.nested["field2"] == 0


class TestConfigMetadataI18n:
    """Tests for i18n utils."""

    def test_get_i18n_key(self):
        """Test generating i18n key."""
        key = ConfigMetadataI18n._get_i18n_key(
            group="ai_group",
            section="general",
            field="enable",
            attr="description",
        )

        assert key == "ai_group.general.enable.description"

    def test_get_i18n_key_without_field(self):
        """Test generating i18n key without field."""
        key = ConfigMetadataI18n._get_i18n_key(
            group="ai_group",
            section="general",
            field="",
            attr="description",
        )

        assert key == "ai_group.general.description"

    def test_convert_to_i18n_keys_simple(self):
        """Test converting simple metadata to i18n keys."""
        metadata = {
            "ai_group": {
                "name": "AI Settings",
                "metadata": {
                    "general": {
                        "description": "General settings",
                        "items": {
                            "enable": {
                                "description": "Enable feature",
                                "type": "bool",
                                "default": True,
                            },
                        },
                    },
                },
            },
        }

        result = ConfigMetadataI18n.convert_to_i18n_keys(metadata)

        assert result["ai_group"]["name"] == "ai_group.name"
        assert (
            result["ai_group"]["metadata"]["general"]["description"]
            == "ai_group.general.description"
        )
        assert (
            result["ai_group"]["metadata"]["general"]["items"]["enable"]["description"]
            == "ai_group.general.enable.description"
        )

    def test_convert_to_i18n_keys_with_hint(self):
        """Test converting metadata with hint."""
        metadata = {
            "group": {
                "metadata": {
                    "section": {
                        "hint": "This is a hint",
                        "items": {
                            "field": {
                                "hint": "Field hint",
                                "type": "string",
                            },
                        },
                    },
                },
            },
        }

        result = ConfigMetadataI18n.convert_to_i18n_keys(metadata)

        assert result["group"]["metadata"]["section"]["hint"] == "group.section.hint"
        assert (
            result["group"]["metadata"]["section"]["items"]["field"]["hint"]
            == "group.section.field.hint"
        )

    def test_convert_to_i18n_keys_with_labels(self):
        """Test converting metadata with labels."""
        metadata = {
            "group": {
                "metadata": {
                    "section": {
                        "items": {
                            "field": {
                                "labels": ["Label1", "Label2"],
                                "type": "string",
                            },
                        },
                    },
                },
            },
        }

        result = ConfigMetadataI18n.convert_to_i18n_keys(metadata)

        assert (
            result["group"]["metadata"]["section"]["items"]["field"]["labels"]
            == "group.section.field.labels"
        )

    def test_convert_to_i18n_keys_nested_items(self):
        """Test converting metadata with nested items."""
        metadata = {
            "group": {
                "metadata": {
                    "section": {
                        "items": {
                            "nested": {
                                "description": "Nested field",
                                "type": "object",
                                "items": {
                                    "inner": {
                                        "description": "Inner field",
                                        "type": "string",
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

        result = ConfigMetadataI18n.convert_to_i18n_keys(metadata)

        assert (
            result["group"]["metadata"]["section"]["items"]["nested"]["description"]
            == "group.section.nested.description"
        )
        assert (
            result["group"]["metadata"]["section"]["items"]["nested"]["items"]["inner"][
                "description"
            ]
            == "group.section.nested.inner.description"
        )

    def test_convert_to_i18n_keys_preserves_non_i18n_fields(self):
        """Test that non-i18n fields are preserved."""
        metadata = {
            "group": {
                "metadata": {
                    "section": {
                        "items": {
                            "field": {
                                "description": "Field description",
                                "type": "string",
                                "other_field": "preserve this",
                            },
                        },
                    },
                },
            },
        }

        result = ConfigMetadataI18n.convert_to_i18n_keys(metadata)

        assert (
            result["group"]["metadata"]["section"]["items"]["field"]["other_field"]
            == "preserve this"
        )

    def test_convert_to_i18n_keys_with_name(self):
        """Test converting metadata with name field."""
        metadata = {
            "group": {
                "metadata": {
                    "section": {
                        "items": {
                            "field": {
                                "name": "Field Name",
                                "type": "string",
                            },
                        },
                    },
                },
            },
        }

        result = ConfigMetadataI18n.convert_to_i18n_keys(metadata)

        assert (
            result["group"]["metadata"]["section"]["items"]["field"]["name"]
            == "group.section.field.name"
        )
