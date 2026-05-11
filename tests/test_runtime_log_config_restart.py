from astrbot.dashboard.routes.config import (
    _runtime_log_config_changed,
    _system_config_save_requires_restart,
)


def test_log_level_change_does_not_require_restart():
    old_config = {"log_level": "INFO", "timezone": "Asia/Shanghai"}
    new_config = {"log_level": "DEBUG", "timezone": "Asia/Shanghai"}

    assert _runtime_log_config_changed(old_config, new_config)
    assert not _system_config_save_requires_restart(old_config, new_config)


def test_legacy_log_file_change_does_not_require_restart():
    old_config = {
        "timezone": "Asia/Shanghai",
        "log_file": {"enable": False, "path": "logs/astrbot.log"},
    }
    new_config = {
        "timezone": "Asia/Shanghai",
        "log_file": {"enable": True, "path": "logs/astrbot.log"},
    }

    assert _runtime_log_config_changed(old_config, new_config)
    assert not _system_config_save_requires_restart(old_config, new_config)


def test_non_log_config_change_requires_restart():
    old_config = {"log_level": "INFO", "timezone": "Asia/Shanghai"}
    new_config = {"log_level": "INFO", "timezone": "UTC"}

    assert not _runtime_log_config_changed(old_config, new_config)
    assert _system_config_save_requires_restart(old_config, new_config)


def test_no_config_change_does_not_require_restart():
    config = {"log_level": "INFO", "timezone": "Asia/Shanghai"}

    assert not _runtime_log_config_changed(config, config)
    assert not _system_config_save_requires_restart(config, config)
