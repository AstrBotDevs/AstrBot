from collections.abc import MutableMapping

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    is_md5_dashboard_password,
)

PASSWORD_STORAGE_UPGRADED_KEY = "password_storage_upgraded"
PASSWORD_CHANGE_REQUIRED_KEY = "password_change_required"


async def _set_dashboard_flag(
    config: AstrBotConfig,
    key: str,
    value: bool,
) -> bool:
    if config["dashboard"].get(key) == bool(value):
        return True
    config["dashboard"][key] = bool(value)
    return await config.save_config_async()


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
    config: AstrBotConfig,
    *,
    persist: bool = True,
) -> bool:
    config_upgraded = _has_usable_pbkdf2_password(config)
    if (
        persist
        and config["dashboard"].get(PASSWORD_STORAGE_UPGRADED_KEY) != config_upgraded
    ):
        await _set_dashboard_flag(
            config,
            PASSWORD_STORAGE_UPGRADED_KEY,
            config_upgraded,
        )
    return config_upgraded


async def set_password_storage_upgraded(
    config: AstrBotConfig,
    upgraded: bool,
) -> bool:
    """Persist the password-storage capability flag.

    Returns:
        Whether the requested state was already durable or this write won the
        configuration revision race.
    """
    return await _set_dashboard_flag(config, PASSWORD_STORAGE_UPGRADED_KEY, upgraded)


async def is_password_change_required(
    config: AstrBotConfig,
    *,
    persist: bool = True,
) -> bool:
    stored = config["dashboard"].get(PASSWORD_CHANGE_REQUIRED_KEY, None)
    if stored is not None:
        return bool(stored)

    required = bool(
        getattr(config, "_generated_dashboard_password_change_required", False)
        or getattr(config, "_dashboard_password_change_required_from_config", False)
    )
    if required and persist:
        await _set_dashboard_flag(config, PASSWORD_CHANGE_REQUIRED_KEY, True)
    return required


async def set_password_change_required(
    config: AstrBotConfig,
    required: bool,
) -> bool:
    """Persist the Dashboard password-change requirement flag.

    Returns:
        Whether the requested state was already durable or this write won the
        configuration revision race.
    """
    return await _set_dashboard_flag(config, PASSWORD_CHANGE_REQUIRED_KEY, required)


def get_dashboard_password_hash(config: AstrBotConfig, *, upgraded: bool) -> str:
    if upgraded and _has_usable_pbkdf2_password(config):
        return config["dashboard"].get("pbkdf2_password", "")

    md5_password = config["dashboard"].get("password", "")
    if upgraded and not is_md5_dashboard_password(md5_password):
        return ""
    return md5_password


def set_dashboard_password_hashes(
    dashboard_config: MutableMapping[str, object],
    raw_password: str,
) -> None:
    """Set password hashes on a staged Dashboard configuration mapping."""
    dashboard_config["pbkdf2_password"] = hash_dashboard_password(raw_password)
    dashboard_config["password"] = ""


def set_dashboard_password_security_state(
    dashboard_config: MutableMapping[str, object],
) -> None:
    """Mark a staged Dashboard password update as fully upgraded."""
    dashboard_config[PASSWORD_STORAGE_UPGRADED_KEY] = True
    dashboard_config[PASSWORD_CHANGE_REQUIRED_KEY] = False
