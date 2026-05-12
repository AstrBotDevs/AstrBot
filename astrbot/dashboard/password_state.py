from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_legacy_dashboard_password,
    is_legacy_dashboard_password,
)

PASSWORD_STORAGE_UPGRADED_KEY = "password_storage_upgraded"
PASSWORD_CHANGE_REQUIRED_KEY = "password_change_required"


def _set_dashboard_flag(config: AstrBotConfig, key: str, value: bool) -> None:
    if config["dashboard"].get(key) == bool(value):
        return
    config["dashboard"][key] = bool(value)
    config.save_config()


def _has_usable_pbkdf2_password(config: AstrBotConfig) -> bool:
    password = config["dashboard"].get("pbkdf2_password", "")
    if not isinstance(password, str) or not password.startswith("pbkdf2_sha256$"):
        return False

    parts = password.split("$")
    if len(parts) != 4:
        return False

    _, iterations, salt, digest = parts
    try:
        int(iterations)
        bytes.fromhex(salt)
        bytes.fromhex(digest)
    except ValueError:
        return False
    return True


async def is_password_storage_upgraded(
    db: BaseDatabase,
    config: AstrBotConfig,
) -> bool:
    config_upgraded = _has_usable_pbkdf2_password(config)
    if config["dashboard"].get(PASSWORD_STORAGE_UPGRADED_KEY) != config_upgraded:
        _set_dashboard_flag(config, PASSWORD_STORAGE_UPGRADED_KEY, config_upgraded)
    return config_upgraded


async def set_password_storage_upgraded(
    db: BaseDatabase,
    config: AstrBotConfig,
    upgraded: bool,
) -> None:
    _set_dashboard_flag(config, PASSWORD_STORAGE_UPGRADED_KEY, upgraded)


async def is_password_change_required(
    db: BaseDatabase,
    config: AstrBotConfig,
) -> bool:
    stored = config["dashboard"].get(PASSWORD_CHANGE_REQUIRED_KEY, None)
    if stored is not None:
        return bool(stored)

    required = bool(
        getattr(config, "_generated_dashboard_password_change_required", False)
        or getattr(config, "_dashboard_password_change_required_from_config", False)
    )
    if required:
        _set_dashboard_flag(config, PASSWORD_CHANGE_REQUIRED_KEY, True)
    return required


async def set_password_change_required(
    db: BaseDatabase,
    config: AstrBotConfig,
    required: bool,
) -> None:
    _set_dashboard_flag(config, PASSWORD_CHANGE_REQUIRED_KEY, required)


def get_dashboard_password_hash(config: AstrBotConfig, *, upgraded: bool) -> str:
    if upgraded and _has_usable_pbkdf2_password(config):
        return config["dashboard"].get("pbkdf2_password", "")

    legacy_password = config["dashboard"].get("password", "")
    if upgraded and not is_legacy_dashboard_password(legacy_password):
        return ""
    return legacy_password


def set_dashboard_password_hashes(config: AstrBotConfig, raw_password: str) -> None:
    config["dashboard"]["pbkdf2_password"] = hash_dashboard_password(raw_password)
    config["dashboard"]["password"] = hash_legacy_dashboard_password(raw_password)
