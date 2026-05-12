from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db import BaseDatabase
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_legacy_dashboard_password,
)

DASHBOARD_PREF_SCOPE = "global"
DASHBOARD_PREF_SCOPE_ID = "global"
PASSWORD_STORAGE_UPGRADED_KEY = "dashboard_password_storage_upgraded"
PASSWORD_CHANGE_REQUIRED_KEY = "dashboard_password_change_required"


async def _get_pref(db: BaseDatabase, key: str, default=None):
    pref = await db.get_preference(
        DASHBOARD_PREF_SCOPE,
        DASHBOARD_PREF_SCOPE_ID,
        key,
    )
    if not pref:
        return default
    if not isinstance(pref.value, dict):
        return default
    return pref.value.get("val", default)


async def _set_pref(db: BaseDatabase, key: str, value) -> None:
    await db.insert_preference_or_update(
        DASHBOARD_PREF_SCOPE,
        DASHBOARD_PREF_SCOPE_ID,
        key,
        {"val": value},
    )


async def is_password_storage_upgraded(
    db: BaseDatabase,
    config: AstrBotConfig,
) -> bool:
    stored = await _get_pref(db, PASSWORD_STORAGE_UPGRADED_KEY, None)
    if stored is not None:
        return bool(stored)

    upgraded = bool(config["dashboard"].get("pbkdf2_password"))
    await set_password_storage_upgraded(db, upgraded)
    return upgraded


async def set_password_storage_upgraded(db: BaseDatabase, upgraded: bool) -> None:
    await _set_pref(db, PASSWORD_STORAGE_UPGRADED_KEY, bool(upgraded))


async def is_password_change_required(
    db: BaseDatabase,
    config: AstrBotConfig,
) -> bool:
    stored = await _get_pref(db, PASSWORD_CHANGE_REQUIRED_KEY, None)
    if stored is not None:
        return bool(stored)

    required = bool(
        getattr(config, "_generated_dashboard_password_change_required", False)
        or getattr(config, "_dashboard_password_change_required_from_config", False)
        or config["dashboard"].get("password_change_required", False)
    )
    await set_password_change_required(db, required)
    return required


async def set_password_change_required(db: BaseDatabase, required: bool) -> None:
    await _set_pref(db, PASSWORD_CHANGE_REQUIRED_KEY, bool(required))


def get_dashboard_password_hash(config: AstrBotConfig, *, upgraded: bool) -> str:
    if upgraded:
        return config["dashboard"].get("pbkdf2_password", "")
    return config["dashboard"].get("password", "")


def set_dashboard_password_hashes(config: AstrBotConfig, raw_password: str) -> None:
    config["dashboard"]["pbkdf2_password"] = hash_dashboard_password(raw_password)
    config["dashboard"]["password"] = hash_legacy_dashboard_password(raw_password)
