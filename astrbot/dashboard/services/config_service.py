import asyncio
import copy
import inspect
import os
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    CONFIG_METADATA_3_SYSTEM,
    DEFAULT_CONFIG,
    DEFAULT_VALUE_MAP,
)
from astrbot.core.config.i18n_utils import ConfigMetadataI18n
from astrbot.core.core_runtime import CoreControl
from astrbot.core.db.protocols import DatabaseSessionStore
from astrbot.core.file_token_service import FileTokenService
from astrbot.core.platform.catalog import PlatformCatalog
from astrbot.core.platform.discovery import discover_platform_adapter
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.provider.catalog import ProviderCatalog
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.star.plugin_lifecycle import PluginLifecycle
from astrbot.core.star.star import PluginRegistry
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.llm_metadata import LLMMetadataCatalog
from astrbot.core.utils.totp import (
    TotpRuntimeState,
    is_totp_enabled,
    revoke_user_trusted_devices,
)
from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config
from astrbot.dashboard.async_utils import run_maybe_async
from astrbot.dashboard.responses import ApiError, DashboardValidationError
from astrbot.dashboard.upload_utils import save_upload_to_path

PROTECTED_2FA_CONFIG_PATHS = (
    ("dashboard", "totp", "enable"),
    ("dashboard", "totp", "secret"),
    ("dashboard", "totp", "recovery_code_hash"),
)
MAX_FILE_BYTES = 500 * 1024 * 1024
REDACTED_SECRET_PLACEHOLDER = "__ASTRBOT_REDACTED__"
SENSITIVE_CONFIG_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "app_secret",
        "client_secret",
        "jwt_secret",
        "key",
        "password",
        "pbkdf2_password",
        "recovery_code_hash",
        "refresh_token",
        "secret",
        "secret_key",
        "signing_secret",
        "token",
        "wecomaibot_ws_secret",
    }
)
SENSITIVE_CONFIG_SUFFIXES = (
    "_api_key",
    "_key",
    "_password",
    "_secret",
    "_token",
)


def _ensure_dashboard_platform_metadata_loaded(
    platform_catalog: PlatformCatalog,
) -> None:
    """Load platform adapters whose config metadata must be visible in the dashboard.

    Built-in platform templates in `CONFIG_METADATA_2` cover legacy adapters, but
    newer adapters such as NapCat rely on registration-time metadata injection.
    The dashboard can be opened before such adapters are enabled, so their modules
    may never have been imported through `PlatformManager.load_platform()`.
    """
    if platform_catalog.get("napcat") is not None:
        return

    try:
        discover_platform_adapter("napcat", platform_catalog)
    except Exception as exc:
        logger.warning("Failed to load NapCat platform metadata for dashboard: %s", exc)


def try_cast(value: Any, type_: str):
    if type_ == "int":
        try:
            return int(value)
        except ValueError, TypeError:
            return None
    elif (
        type_ == "float"
        and isinstance(value, str)
        and value.replace(".", "", 1).isdigit()
    ) or (type_ == "float" and isinstance(value, int)):
        return float(value)
    elif type_ == "float":
        try:
            return float(value)
        except ValueError, TypeError:
            return None


def _expect_type(value, expected_type, path_key, errors, expected_name=None) -> bool:
    if not isinstance(value, expected_type):
        errors.append(
            f"错误的类型 {path_key}: 期望是 {expected_name or expected_type.__name__}, "
            f"得到了 {type(value).__name__}"
        )
        return False
    return True


def _is_sensitive_config_key(key: str | None) -> bool:
    if not key:
        return False
    normalized = key.lower()
    if normalized in SENSITIVE_CONFIG_KEYS:
        return True
    return normalized.endswith(SENSITIVE_CONFIG_SUFFIXES)


def _redact_sensitive_config(value: Any, *, key_name: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_sensitive_config(item, key_name=key)
            for key, item in value.items()
        }

    if isinstance(value, list):
        if key_name and _is_sensitive_config_key(key_name):
            return [
                REDACTED_SECRET_PLACEHOLDER if isinstance(item, str) and item else item
                for item in value
            ]
        return [_redact_sensitive_config(item, key_name=key_name) for item in value]

    if key_name and _is_sensitive_config_key(key_name):
        if isinstance(value, str) and value:
            return REDACTED_SECRET_PLACEHOLDER

    return value


def _restore_redacted_sensitive_config(
    posted_value: Any,
    current_value: Any,
    *,
    key_name: str | None = None,
) -> Any:
    if isinstance(posted_value, dict) and isinstance(current_value, dict):
        for key, item in posted_value.items():
            if key not in current_value:
                continue
            posted_value[key] = _restore_redacted_sensitive_config(
                item,
                current_value[key],
                key_name=key,
            )
        return posted_value

    if isinstance(posted_value, list) and isinstance(current_value, list):
        if key_name and _is_sensitive_config_key(key_name):
            restored_items = []
            for idx, item in enumerate(posted_value):
                if (
                    item == REDACTED_SECRET_PLACEHOLDER
                    and idx < len(current_value)
                    and isinstance(current_value[idx], str)
                ):
                    restored_items.append(current_value[idx])
                else:
                    restored_items.append(item)
            return restored_items

        for idx, item in enumerate(posted_value):
            if idx >= len(current_value):
                break
            posted_value[idx] = _restore_redacted_sensitive_config(
                item,
                current_value[idx],
                key_name=key_name,
            )
        return posted_value

    if (
        key_name
        and _is_sensitive_config_key(key_name)
        and posted_value == REDACTED_SECRET_PLACEHOLDER
    ):
        return current_value

    return posted_value


def _validate_template_list(value, meta, path_key, errors, validate_fn) -> None:
    if not _expect_type(value, list, path_key, errors, "list"):
        return

    templates = meta.get("templates")
    if not isinstance(templates, dict):
        templates = {}

    for idx, item in enumerate(value):
        item_path = f"{path_key}[{idx}]"
        if not _expect_type(item, dict, item_path, errors, "dict"):
            continue

        template_key = item.get("__template_key") or item.get("template")
        if not template_key:
            errors.append(f"缺少模板选择 {item_path}: 需要 __template_key")
            continue

        template_meta = templates.get(template_key)
        if not template_meta:
            errors.append(f"未知模板 {item_path}: {template_key}")
            continue

        validate_fn(
            item,
            template_meta.get("items", {}),
            path=f"{path_key}.templates.{template_key}.",
        )


def sanitize_path_segment(segment: str) -> str:
    cleaned = []
    for ch in segment:
        if (
            ("a" <= ch <= "z")
            or ("A" <= ch <= "Z")
            or ch.isdigit()
            or ch
            in {
                "-",
                "_",
            }
        ):
            cleaned.append(ch)
        else:
            cleaned.append("_")
    result = "".join(cleaned).strip("_")
    return result or "_"


def _config_key_to_folder(key_path: str) -> str:
    parts = [sanitize_path_segment(part) for part in key_path.split(".") if part]
    return "/".join(parts) if parts else "_"


def config_key_to_folder(key_path: str) -> str:
    return _config_key_to_folder(key_path)


def _normalize_rel_path(path: object) -> str | None:
    if not isinstance(path, str):
        return None
    rel = path.replace("\\", "/").lstrip("/")
    if not rel:
        return None
    parts = [part for part in rel.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        return None
    if rel.startswith("../") or "/../" in rel:
        return None
    return "/".join(parts)


def normalize_rel_path(path: str | None) -> str | None:
    return _normalize_rel_path(path)


def _get_schema_item(schema: dict | None, key_path: str) -> dict | None:
    if not isinstance(schema, dict) or not key_path:
        return None
    if key_path in schema:
        return schema.get(key_path)

    parts = key_path.split(".")
    current = schema
    idx = 0
    while idx < len(parts):
        part = parts[idx]
        if part not in current:
            return None
        meta = current.get(part)
        if idx == len(parts) - 1:
            return meta
        if not isinstance(meta, dict) or meta.get("type") != "object":
            if not isinstance(meta, dict) or meta.get("type") != "template_list":
                return None
            if idx + 2 >= len(parts) or parts[idx + 1] != "templates":
                return None
            template_meta = meta.get("templates", {}).get(parts[idx + 2])
            if not isinstance(template_meta, dict):
                return None
            if idx + 2 == len(parts) - 1:
                return template_meta
            current = template_meta.get("items", {})
            idx += 3
            continue
        current = meta.get("items", {})
        idx += 1
    return None


def get_schema_item(schema: dict | None, key_path: str) -> dict | None:
    return _get_schema_item(schema, key_path)


def _sanitize_filename(name: str) -> str:
    cleaned = os.path.basename(name).strip()
    if not cleaned or cleaned in {".", ".."}:
        return ""
    for sep in (os.sep, os.altsep):
        if sep:
            cleaned = cleaned.replace(sep, "_")
    return cleaned


def sanitize_filename(name: str) -> str:
    return _sanitize_filename(name)


def validate_config(data, schema: dict, is_core: bool) -> tuple[list[str], dict]:
    errors = []

    def validate(data: dict, metadata: dict = schema, path="") -> None:
        for key, value in data.items():
            if key not in metadata:
                continue
            meta = metadata[key]
            if "type" not in meta:
                logger.debug(f"配置项 {path}{key} 没有类型定义, 跳过校验")
                continue
            if value is None:
                data[key] = copy.deepcopy(DEFAULT_VALUE_MAP[meta["type"]])
                continue

            if meta["type"] == "template_list":
                _validate_template_list(value, meta, f"{path}{key}", errors, validate)
                continue

            if meta["type"] == "file":
                if not _expect_type(value, list, f"{path}{key}", errors, "list"):
                    continue
                for idx, item in enumerate(value):
                    if not isinstance(item, str):
                        errors.append(
                            f"Invalid type {path}{key}[{idx}]: expected string, got {type(item).__name__}",
                        )
                        continue
                    normalized = _normalize_rel_path(item)
                    if not normalized or not normalized.startswith("files/"):
                        errors.append(
                            f"Invalid file path {path}{key}[{idx}]: {item}",
                        )
                        continue
                    key_path = f"{path}{key}"
                    expected_folder = _config_key_to_folder(key_path)
                    expected_prefix = f"files/{expected_folder}/"
                    if not normalized.startswith(expected_prefix):
                        errors.append(
                            f"Invalid file path {path}{key}[{idx}]: {item}",
                        )
                        continue
                    value[idx] = normalized
                continue

            if meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif (
                meta["type"] == "list"
                and isinstance(value, list)
                and value
                and "items" in meta
                and isinstance(value[0], dict)
            ):
                for item in value:
                    validate(item, meta["items"], path=f"{path}{key}.")
            elif meta["type"] == "object" and isinstance(value, dict):
                validate(value, meta["items"], path=f"{path}{key}.")

            if meta["type"] == "int" and not isinstance(value, int):
                casted = try_cast(value, "int")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 int, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "float" and not isinstance(value, float):
                casted = try_cast(value, "float")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 float, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "bool" and not isinstance(value, bool):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 bool, 得到了 {type(value).__name__}",
                )
            elif meta["type"] in ["string", "text"] and not isinstance(value, str):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 string, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "list" and not isinstance(value, list):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "object" and not isinstance(value, dict):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 dict, 得到了 {type(value).__name__}",
                )

    if is_core:
        meta_all = {
            **schema["platform_group"]["metadata"],
            **schema["provider_group"]["metadata"],
            **schema["misc_config_group"]["metadata"],
        }
        validate(data, meta_all)
    else:
        validate(data, schema)

    return errors, data


def _log_computer_config_changes(
    old_config: dict,
    new_config: dict,
    *,
    log_info=None,
) -> None:
    log_info = log_info or logger.info
    old_ps = old_config.get("provider_settings", {})
    new_ps = new_config.get("provider_settings", {})

    old_runtime = old_ps.get("computer_use_runtime", "none")
    new_runtime = new_ps.get("computer_use_runtime", "none")
    if old_runtime != new_runtime:
        log_info(
            "[Computer] Config changed: computer_use_runtime %s -> %s",
            old_runtime,
            new_runtime,
        )

    old_sandbox = old_ps.get("sandbox", {})
    new_sandbox = new_ps.get("sandbox", {})
    all_keys = set(old_sandbox.keys()) | set(new_sandbox.keys())
    for key in sorted(all_keys):
        old_val = old_sandbox.get(key)
        new_val = new_sandbox.get(key)
        if old_val == new_val:
            continue
        if "token" in key or "secret" in key:
            old_display = "***" if old_val else "(empty)"
            new_display = "***" if new_val else "(empty)"
        else:
            old_display = old_val
            new_display = new_val
        log_info(
            "[Computer] Config changed: sandbox.%s %s -> %s",
            key,
            old_display,
            new_display,
        )


def _get_nested_value(data: dict, path: tuple[str, ...]) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _set_nested_value(data: dict, path: tuple[str, ...], value: Any) -> None:
    current = data
    for key in path[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[path[-1]] = value


def _protected_2fa_config_changed(old_config: dict, new_config: dict) -> bool:
    return any(
        _get_nested_value(old_config, path) != _get_nested_value(new_config, path)
        for path in PROTECTED_2FA_CONFIG_PATHS
    )


async def _validate_neo_connectivity(post_config: dict) -> str | None:
    ps = post_config.get("provider_settings", {})
    runtime = ps.get("computer_use_runtime", "none")
    sandbox = ps.get("sandbox", {})
    booter = sandbox.get("booter", "")

    if runtime != "sandbox" or booter != "shipyard_neo":
        return None

    endpoint = sandbox.get("shipyard_neo_endpoint", "").rstrip("/")
    if not endpoint:
        return "⚠️ Shipyard Neo endpoint 未设置"

    access_token = sandbox.get("shipyard_neo_access_token", "")
    if not access_token:
        from astrbot.core.computer.computer_client import _discover_bay_credentials

        access_token = _discover_bay_credentials(endpoint)

    if not access_token:
        return (
            "⚠️ 未找到 Bay API Key。请填写访问令牌，"
            "或确保 Bay 的 credentials.json 可被自动发现。"
        )

    import aiohttp

    health_url = f"{endpoint}/health"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                health_url,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return (
                        f"⚠️ Bay 健康检查失败 (HTTP {resp.status})，"
                        f"请确认 Bay 正在运行: {endpoint}"
                    )
    except Exception:
        return f"⚠️ 无法连接 Bay ({endpoint})，请确认 Bay 已启动。"

    return None


async def save_config_async(
    post_config: dict,
    config: AstrBotConfig,
    is_core: bool = False,
) -> bool:
    """Validate and persist a Dashboard configuration update.

    The configuration snapshot is prepared synchronously by ``AstrBotConfig``
    before its file write is moved off the event loop. Callers must await this
    function before reloading runtime state that consumes the new values.
    """
    if isinstance(post_config, dict):
        post_config = copy.deepcopy(dict(post_config))
    else:
        post_config = copy.deepcopy(post_config)
    current_config = dict(config) if isinstance(config, dict) else {}
    _restore_redacted_sensitive_config(post_config, current_config)

    if is_core:
        _log_computer_config_changes(current_config, post_config)

    try:
        if is_core:
            errors, post_config = validate_config(
                post_config,
                CONFIG_METADATA_2,
                is_core,
            )
        else:
            errors, post_config = validate_config(
                post_config,
                getattr(config, "schema", {}),
                is_core,
            )
    except Exception as exc:
        logger.error(traceback.format_exc())
        logger.warning(f"验证配置时出现异常: {exc}")
        raise DashboardValidationError("验证配置时出现异常，请检查配置或服务端日志")
    if errors:
        raise DashboardValidationError(f"格式校验未通过: {errors}")

    return await config.save_config_async(post_config)


def _require_config_save_commit(committed: bool) -> None:
    """Raise a conflict when a newer configuration revision won the write race."""
    if not committed:
        raise ApiError(
            "Configuration save was superseded by a newer update.",
            status_code=409,
        )


class ConfigProfileService:
    def __init__(
        self,
        config_manager: AstrBotConfigManager,
        config_router: UmopConfigRouter,
        core_control: CoreControl,
        totp_runtime_state: TotpRuntimeState,
        db: DatabaseSessionStore | None = None,
    ) -> None:
        self.core_control = core_control
        self.acm = config_manager
        self.config_router = config_router
        self.db = db
        self.totp_runtime_state = totp_runtime_state

    def get_profile_schema(self) -> dict:
        return {
            "config": DEFAULT_CONFIG,
            "metadata": ConfigMetadataI18n.convert_to_i18n_keys(CONFIG_METADATA_3),
        }

    def get_system_schema(self) -> dict:
        return {
            "config": self.acm.confs["default"],
            "metadata": ConfigMetadataI18n.convert_to_i18n_keys(
                CONFIG_METADATA_3_SYSTEM
            ),
        }

    def get_system_config(self) -> dict:
        data = self.get_system_schema()
        server_utc_time = datetime.now(UTC)
        timezone_name = str(data["config"].get("timezone") or "").strip()
        effective_timezone_name: str | None = None
        if timezone_name:
            try:
                configured_time = server_utc_time.astimezone(ZoneInfo(timezone_name))
                effective_timezone_name = timezone_name
            except ValueError, ZoneInfoNotFoundError:
                configured_time = server_utc_time.astimezone()
        else:
            configured_time = server_utc_time.astimezone()

        utc_offset = configured_time.utcoffset()
        data["server_utc_time"] = server_utc_time.isoformat()
        data["server_utc_offset_minutes"] = (
            int(utc_offset.total_seconds() / 60) if utc_offset else 0
        )
        data["server_timezone"] = effective_timezone_name
        return data

    def list_profiles(self) -> dict:
        return {"info_list": self.acm.get_conf_list()}

    async def create_profile(
        self,
        name: str | None,
        config: dict | None,
        *,
        allow_admin_id_change: bool = True,
    ) -> dict:
        if (
            not allow_admin_id_change
            and isinstance(config, dict)
            and "admins_id" in config
        ):
            raise ApiError(
                "config:edit_admin scope is required to set admins_id",
                status_code=403,
            )
        conf_id = await self.acm.create_conf(name=name, config=config or DEFAULT_CONFIG)
        await self.core_control.reload_pipeline_scheduler(conf_id)
        return {"conf_id": conf_id}

    def get_profile(self, config_id: str) -> dict:
        if config_id not in self.acm.confs:
            raise DashboardValidationError(f"Config file {config_id} does not exist")
        return {
            "config": self.acm.confs[config_id],
            "metadata": ConfigMetadataI18n.convert_to_i18n_keys(CONFIG_METADATA_3),
        }

    async def update_profile(
        self,
        config_id: str,
        config: dict,
        *,
        subject: str,
        two_factor_code: str | None = None,
        allow_admin_id_change: bool = True,
    ) -> str | None:
        if config_id not in self.acm.confs:
            raise DashboardValidationError(f"Config file {config_id} does not exist")
        config = copy.deepcopy(config)
        if config_id == "default":
            default_conf = getattr(self.acm, "default_conf", self.acm.confs["default"])
            for key in ("provider_sources", "provider", "platform"):
                config[key] = default_conf.get(key, [])

        current_config = self.acm.confs[config_id]
        if (
            not allow_admin_id_change
            and "admins_id" in config
            and config.get("admins_id") != current_config.get("admins_id")
        ):
            raise ApiError(
                "config:edit_admin scope is required to change admins_id",
                status_code=403,
            )
        protected_2fa_changed = _protected_2fa_config_changed(current_config, config)
        if (
            is_totp_enabled(current_config)
            and protected_2fa_changed
            and not await self._verify_config_2fa(
                subject,
                current_config,
                two_factor_code,
            )
        ):
            raise ApiError(
                "需要 TOTP 验证",
                status_code=401,
                data={"totp_required": True},
            )

        if not _get_nested_value(config, ("dashboard", "totp", "enable")):
            _set_nested_value(config, ("dashboard", "totp", "secret"), "")
            _set_nested_value(config, ("dashboard", "totp", "recovery_code_hash"), "")

        committed = await save_config_async(
            config,
            self.acm.confs[config_id],
            is_core=True,
        )
        if not committed:
            raise ApiError(
                "Configuration save was superseded by a newer update.",
                status_code=409,
            )
        if protected_2fa_changed:
            await self.totp_runtime_state.clear_all()
            if self.db is not None:
                await revoke_user_trusted_devices(self.db)
        await self.core_control.reload_pipeline_scheduler(config_id)
        warning = await _validate_neo_connectivity(config)
        if warning:
            return f"保存成功。{warning}"
        return "保存成功~"

    async def _verify_config_2fa(
        self,
        subject: str,
        current_config: dict,
        two_factor_code: str | None,
    ) -> bool:
        code = (two_factor_code or "").strip()
        if not code:
            return False
        return bool(
            await self.totp_runtime_state.verify_configured_2fa_code(
                current_config,
                code,
                subject=subject,
                include_pending=True,
                allow_recovery=False,
            )
        )

    async def rename_profile(self, config_id: str, name: str | None) -> None:
        if not await self.acm.update_conf_info(config_id, name=name):
            raise DashboardValidationError("Failed to update config profile")

    async def delete_profile(self, config_id: str) -> None:
        if not await self.acm.delete_conf(config_id):
            raise DashboardValidationError("Failed to delete config profile")
        await self.core_control.remove_pipeline_scheduler(config_id)
        ucr = self.config_router
        next_routing = {
            umo: mapped_conf_id
            for umo, mapped_conf_id in ucr.umop_to_conf_id.items()
            if mapped_conf_id != config_id
        }
        if next_routing != ucr.umop_to_conf_id:
            await ucr.update_routing_data(next_routing)


class ConfigRoutingService:
    def __init__(self, config_router: UmopConfigRouter) -> None:
        self.ucr = config_router

    def list_routes(self) -> dict:
        return {"routing": self.ucr.umop_to_conf_id}

    async def replace_route_mapping(self, routing: dict[str, str]) -> None:
        await self.ucr.update_routing_data(routing)

    async def set_route(self, umo: str, config_id: str) -> None:
        if config_id == "default":
            await self.delete_route_by_umo(umo)
            return
        await self.ucr.update_route(umo, config_id)

    async def delete_route_by_umo(self, umo: str) -> None:
        if umo in self.ucr.umop_to_conf_id:
            del self.ucr.umop_to_conf_id[umo]
            await self.ucr.update_routing_data(self.ucr.umop_to_conf_id)


class ConfigDisplayService:
    def __init__(
        self,
        config: AstrBotConfig,
        platform_catalog: PlatformCatalog,
        provider_catalog: ProviderCatalog,
        plugin_catalog: PluginRegistry,
        file_token_service: FileTokenService,
    ) -> None:
        self.config = config
        self.platform_catalog = platform_catalog
        self.provider_catalog = provider_catalog
        self.plugin_catalog = plugin_catalog
        self.file_token_service = file_token_service
        self._logo_token_cache: dict[str, str] = {}

    async def get_configs(self, plugin_name: str | None = None) -> dict:
        if not plugin_name:
            return await self.get_astrbot_config()
        return self.get_plugin_config(plugin_name)

    async def get_astrbot_config(self) -> dict:
        _ensure_dashboard_platform_metadata_loaded(self.platform_catalog)
        metadata = copy.deepcopy(CONFIG_METADATA_2)
        platform_i18n = ConfigMetadataI18n.convert_to_i18n_keys(
            {
                "platform_group": {
                    "metadata": {
                        "platform": metadata["platform_group"]["metadata"]["platform"]
                    }
                }
            }
        )
        metadata["platform_group"]["metadata"]["platform"] = platform_i18n[
            "platform_group"
        ]["metadata"]["platform"]

        platform_default_tmpl = metadata["platform_group"]["metadata"]["platform"][
            "config_template"
        ]
        platform_i18n_translations = {}
        logo_registration_tasks = []

        for platform in self.platform_catalog.metadata():
            if not platform.default_config_tmpl:
                continue

            platform_default_tmpl[platform.name] = copy.deepcopy(
                platform.default_config_tmpl
            )
            if platform.config_metadata:
                self.inject_platform_metadata_with_i18n(
                    platform,
                    metadata,
                    platform_i18n_translations,
                )
            if platform.logo_path:
                logo_registration_tasks.append(
                    self.register_platform_logo(platform, platform_default_tmpl),
                )

        if logo_registration_tasks:
            await asyncio.gather(*logo_registration_tasks, return_exceptions=True)

        provider_default_tmpl = metadata["provider_group"]["metadata"]["provider"][
            "config_template"
        ]
        for provider in self.provider_catalog.metadata():
            if provider.default_config_tmpl:
                provider_default_tmpl[provider.type] = provider.default_config_tmpl

        return {
            "metadata": metadata,
            "config": _redact_sensitive_config(copy.deepcopy(dict(self.config))),
            "platform_i18n_translations": platform_i18n_translations,
        }

    def get_plugin_config(self, plugin_name: str) -> dict:
        result: dict = {"metadata": None, "config": None, "i18n": {}}

        for plugin_md in self.plugin_catalog.all():
            if plugin_md.name != plugin_name:
                continue
            if not plugin_md.config:
                break
            result["config"] = plugin_md.config
            result["metadata"] = {
                plugin_name: {
                    "description": f"{plugin_name} 配置",
                    "type": "object",
                    "items": plugin_md.config.schema,
                },
            }
            result["i18n"] = plugin_md.i18n
            break

        return result

    async def register_platform_logo(self, platform, platform_default_tmpl) -> None:
        if not platform.logo_path:
            return

        try:
            cache_key = f"{platform.name}:{platform.logo_path}"
            if cache_key in self._logo_token_cache:
                self._set_platform_logo_token(
                    platform_default_tmpl,
                    platform.name,
                    self._logo_token_cache[cache_key],
                )
                logger.debug(f"Using cached logo token for platform {platform.name}")
                return

            registration = self.platform_catalog.get(platform.name)
            if registration is None:
                logger.warning(f"Platform class not found for {platform.name}")
                return
            platform_cls = registration.cls_type

            module_file = inspect.getfile(platform_cls)
            plugin_dir = os.path.dirname(module_file)
            logo_file_path = os.path.join(plugin_dir, platform.logo_path)

            if not os.path.exists(logo_file_path):
                logger.warning(
                    f"Platform {platform.name} logo file not found: {logo_file_path}",
                )
                return

            logo_token = await self.file_token_service.register_file(
                logo_file_path,
                ttl_seconds=3600,
            )
            self._set_platform_logo_token(
                platform_default_tmpl,
                platform.name,
                logo_token,
            )
            self._logo_token_cache[cache_key] = logo_token
            logger.debug(f"Logo token registered for platform {platform.name}")

        except (ImportError, AttributeError) as exc:
            logger.warning(
                f"Failed to import required modules for platform {platform.name}: {exc}",
            )
        except OSError as exc:
            logger.warning(
                f"File system error for platform {platform.name} logo: {exc}"
            )
        except Exception as exc:
            logger.warning(
                f"Unexpected error registering logo for platform {platform.name}: {exc}",
            )

    @staticmethod
    def _set_platform_logo_token(
        platform_default_tmpl: dict,
        platform_name: str,
        logo_token: str,
    ) -> None:
        if platform_name not in platform_default_tmpl or not isinstance(
            platform_default_tmpl[platform_name],
            dict,
        ):
            platform_default_tmpl[platform_name] = {}
        platform_default_tmpl[platform_name]["logo_token"] = logo_token

    @staticmethod
    def inject_platform_metadata_with_i18n(
        platform,
        metadata,
        platform_i18n_translations: dict,
    ) -> None:
        metadata["platform_group"]["metadata"]["platform"].setdefault("items", {})
        platform_items_to_inject = copy.deepcopy(platform.config_metadata)

        if platform.i18n_resources:
            i18n_prefix = f"platform_group.platform.{platform.name}"

            for lang, lang_data in platform.i18n_resources.items():
                if lang not in {"zh-CN", "en-US"}:
                    continue
                platform_i18n_translations.setdefault(lang, {}).setdefault(
                    "platform_group", {}
                ).setdefault("platform", {})[platform.name] = lang_data

            for field_key, field_value in platform_items_to_inject.items():
                for key in ("description", "hint", "labels"):
                    if key in field_value:
                        field_value[key] = f"{i18n_prefix}.{field_key}.{key}"

        metadata["platform_group"]["metadata"]["platform"]["items"].update(
            platform_items_to_inject
        )


class ConfigFileService:
    def __init__(
        self,
        plugin_catalog: PluginRegistry,
        plugin_lifecycle: PluginLifecycle,
    ) -> None:
        self.plugin_catalog = plugin_catalog
        self.plugin_lifecycle = plugin_lifecycle

    def get_plugin_metadata_by_name(self, plugin_name: str):
        return self.plugin_catalog.get_by_name(plugin_name)

    def resolve_config_file_scope(
        self,
        *,
        scope: str | None,
        name: str | None,
        key_path: str | None,
    ):
        scope = scope or "plugin"
        if scope != "plugin":
            raise DashboardValidationError(f"Unsupported scope: {scope}")
        if not name or not key_path:
            raise DashboardValidationError("Missing name or key parameter")

        metadata = self.get_plugin_metadata_by_name(name)
        if not metadata or not metadata.config:
            raise DashboardValidationError(f"Plugin {name} not found or has no config")

        return scope, name, key_path, metadata, metadata.config

    async def save_plugin_configs(
        self,
        post_configs: dict,
        plugin_name: str,
    ) -> None:
        metadata = self.get_plugin_metadata_by_name(plugin_name)
        if not metadata:
            raise DashboardValidationError(f"插件 {plugin_name} 不存在")
        if not metadata.config:
            raise DashboardValidationError(f"插件 {plugin_name} 没有注册配置")

        errors, post_configs = validate_config(
            post_configs,
            getattr(metadata.config, "schema", {}),
            is_core=False,
        )
        if errors:
            raise DashboardValidationError(f"格式校验未通过: {errors}")
        committed = await metadata.config.save_config_async(post_configs)
        _require_config_save_commit(committed)
        await self.plugin_lifecycle.reload(plugin_name)

    async def upload_config_file(
        self,
        *,
        scope: str | None,
        name: str | None,
        key_path: str | None,
        files: list,
    ) -> dict:
        _, name, key_path, _, config = self.resolve_config_file_scope(
            scope=scope,
            name=name,
            key_path=key_path,
        )
        meta = _get_schema_item(getattr(config, "schema", None), key_path)
        if not meta or meta.get("type") != "file":
            raise DashboardValidationError("Config item not found or not file type")
        if not files:
            raise DashboardValidationError("No files uploaded")

        allowed_exts = self._allowed_file_extensions(meta)
        plugin_root_path = self._plugin_root_path(name)
        plugin_root_path.mkdir(parents=True, exist_ok=True)

        uploaded: list[str] = []
        errors: list[str] = []
        folder = _config_key_to_folder(key_path)

        for file in files:
            filename = _sanitize_filename(file.filename or "")
            if not filename:
                errors.append("Invalid filename")
                continue

            ext = os.path.splitext(filename)[1].lstrip(".").lower()
            if allowed_exts and ext not in allowed_exts:
                errors.append(f"Unsupported file type: {filename}")
                continue

            rel_path = f"files/{folder}/{filename}"
            save_path = self._safe_plugin_path(plugin_root_path, rel_path)
            if save_path is None:
                errors.append(f"Invalid path: {filename}")
                continue

            save_path.parent.mkdir(parents=True, exist_ok=True)
            await save_upload_to_path(file, save_path)
            if save_path.is_file() and save_path.stat().st_size > MAX_FILE_BYTES:
                save_path.unlink()
                errors.append(f"File too large: {filename}")
                continue
            uploaded.append(rel_path)

        if not uploaded:
            raise DashboardValidationError(
                "Upload failed: " + ", ".join(errors) if errors else "Upload failed"
            )

        return {"uploaded": uploaded, "errors": errors}

    def delete_config_file(
        self,
        *,
        scope: str | None,
        name: str | None,
        rel_path: str | None,
    ) -> None:
        if not name:
            raise DashboardValidationError("Missing name parameter")
        if (scope or "plugin") != "plugin":
            raise DashboardValidationError(f"Unsupported scope: {scope}")

        rel_path = _normalize_rel_path(rel_path)
        if not rel_path or not rel_path.startswith("files/"):
            raise DashboardValidationError("Invalid path parameter")

        metadata = self.get_plugin_metadata_by_name(name)
        if not metadata:
            raise DashboardValidationError(f"Plugin {name} not found")

        plugin_root_path = self._plugin_root_path(name)
        target_path = self._safe_plugin_path(plugin_root_path, rel_path)
        if target_path is None:
            raise DashboardValidationError("Invalid path parameter")
        if target_path.is_file():
            target_path.unlink()

    def list_config_files(
        self,
        *,
        scope: str | None,
        name: str | None,
        key_path: str | None,
    ) -> dict:
        _, name, key_path, _, config = self.resolve_config_file_scope(
            scope=scope,
            name=name,
            key_path=key_path,
        )
        meta = _get_schema_item(getattr(config, "schema", None), key_path)
        if not meta or meta.get("type") != "file":
            raise DashboardValidationError("Config item not found or not file type")

        plugin_root_path = self._plugin_root_path(name)
        target_dir = self._safe_plugin_path(
            plugin_root_path,
            f"files/{_config_key_to_folder(key_path)}",
        )
        if target_dir is None:
            raise DashboardValidationError("Invalid path parameter")
        if not target_dir.exists() or not target_dir.is_dir():
            return {"files": []}

        files: list[str] = []
        for path in target_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel_path = path.relative_to(plugin_root_path).as_posix()
            except ValueError:
                continue
            if rel_path.startswith("files/"):
                files.append(rel_path)
        return {"files": files}

    @staticmethod
    def _allowed_file_extensions(meta: dict) -> list[str]:
        file_types = meta.get("file_types")
        if not isinstance(file_types, list):
            return []
        return [str(ext).lstrip(".").lower() for ext in file_types if str(ext).strip()]

    @staticmethod
    def _plugin_root_path(name: str) -> Path:
        storage_root_path = Path(get_astrbot_plugin_data_path()).resolve(strict=False)
        plugin_root_path = (storage_root_path / name).resolve(strict=False)
        try:
            plugin_root_path.relative_to(storage_root_path)
        except ValueError as exc:
            raise DashboardValidationError("Invalid name parameter") from exc
        return plugin_root_path

    @staticmethod
    def _safe_plugin_path(plugin_root_path: Path, rel_path: str) -> Path | None:
        target_path = (plugin_root_path / rel_path).resolve(strict=False)
        try:
            target_path.relative_to(plugin_root_path)
        except ValueError:
            return None
        return target_path


class BotConfigService:
    def __init__(
        self,
        config: AstrBotConfig,
        platform_catalog: PlatformCatalog,
        platform_manager: PlatformManager,
    ) -> None:
        self.config = config
        self.platform_catalog = platform_catalog
        self.platform_manager = platform_manager

    def list_bot_types(self) -> dict:
        _ensure_dashboard_platform_metadata_loaded(self.platform_catalog)
        bot_types = []
        for platform in self.platform_catalog.metadata():
            registration = self.platform_catalog.get(platform.name)
            platform_cls = registration.cls_type if registration is not None else None
            bot_types.append(
                {
                    "type": platform.name,
                    "id": platform.id,
                    "description": platform.description,
                    "display_name": platform.adapter_display_name or platform.name,
                    "default_config": copy.deepcopy(platform.default_config_tmpl),
                    "schema": copy.deepcopy(platform.config_metadata or {}),
                    "support_streaming_message": platform.support_streaming_message,
                    "support_proactive_message": platform.support_proactive_message,
                    "supported_actions": (
                        platform_cls.declared_supported_actions()
                        if platform_cls is not None
                        else []
                    ),
                }
            )
        return {"bot_types": bot_types}

    def list_bots(
        self, *, enabled: bool | None = None, type_: str | None = None
    ) -> dict:
        bots = []
        for bot in self.config.get("platform", []):
            if enabled is not None and bool(bot.get("enable", False)) != enabled:
                continue
            if type_ and bot.get("type") != type_:
                continue
            bots.append(copy.deepcopy(bot))
        return {"bots": bots}

    def get_bot(self, bot_id: str) -> dict:
        bot = self._find_bot(bot_id)
        if bot is None:
            raise DashboardValidationError(f"Bot {bot_id} not found")
        return {"bot": copy.deepcopy(bot)}

    def get_bot_stats(self) -> dict:
        return self.platform_manager.get_all_stats()

    async def create_bot(self, config: dict) -> None:
        bot_id = config.get("id")
        if not bot_id:
            raise DashboardValidationError("Bot config must have an 'id' field")
        if self._find_bot(bot_id) is not None:
            raise DashboardValidationError(f"Bot {bot_id} already exists")
        ensure_platform_webhook_config(config)
        next_config = copy.deepcopy(dict(self.config))
        next_config.setdefault("platform", []).append(copy.deepcopy(config))
        committed = await save_config_async(next_config, self.config, is_core=True)
        _require_config_save_commit(committed)
        await self.platform_manager.load_platform(config)

    async def update_bot(self, bot_id: str, config: dict) -> None:
        if config.get("id") != bot_id:
            raise DashboardValidationError("Bot id cannot be changed")
        ensure_platform_webhook_config(config)
        next_config = copy.deepcopy(dict(self.config))
        for idx, bot in enumerate(next_config.get("platform", [])):
            if bot.get("id") == bot_id:
                next_config["platform"][idx] = copy.deepcopy(config)
                committed = await save_config_async(
                    next_config,
                    self.config,
                    is_core=True,
                )
                _require_config_save_commit(committed)
                await self.platform_manager.reload(config)
                return
        raise DashboardValidationError(f"Bot {bot_id} not found")

    async def set_bot_enabled(self, bot_id: str, enabled: bool) -> None:
        bot = self._find_bot(bot_id)
        if bot is None:
            raise DashboardValidationError(f"Bot {bot_id} not found")
        new_config = copy.deepcopy(bot)
        new_config["enable"] = enabled
        await self.update_bot(bot_id, new_config)

    async def delete_bot(self, bot_id: str) -> None:
        next_config = copy.deepcopy(dict(self.config))
        for idx, bot in enumerate(next_config.get("platform", [])):
            if bot.get("id") == bot_id:
                del next_config["platform"][idx]
                committed = await save_config_async(
                    next_config,
                    self.config,
                    is_core=True,
                )
                _require_config_save_commit(committed)
                await self.platform_manager.terminate_platform(bot_id)
                return
        raise DashboardValidationError(f"Bot {bot_id} not found")

    def _find_bot(self, bot_id: str) -> dict | None:
        for bot in self.config.get("platform", []):
            if bot.get("id") == bot_id:
                return bot
        return None


class ProviderConfigService:
    def __init__(
        self,
        config: AstrBotConfig,
        provider_manager: ProviderManager,
        provider_catalog: ProviderCatalog,
        llm_metadata_catalog: LLMMetadataCatalog,
    ) -> None:
        self.config = config
        self.provider_manager = provider_manager
        self.provider_catalog = provider_catalog
        self.llm_metadata_catalog = llm_metadata_catalog

    def _resolve_provider_type_value(self, adapter_type: object) -> str | None:
        if not isinstance(adapter_type, str) or not adapter_type:
            return None

        registration = self.provider_catalog.get(adapter_type)
        if registration is None:
            try:
                self.provider_manager.dynamic_import_provider(adapter_type)
            except ImportError, ModuleNotFoundError:
                return None
            registration = self.provider_catalog.get(adapter_type)

        if registration is None:
            return None

        return registration.descriptor.provider_type.value

    def _ensure_provider_type(self, config: dict) -> dict:
        if config.get("type") == "openai_responses" and isinstance(
            config.get("web_search"), dict
        ):
            supported_web_search_fields = {
                "enable",
                "search_context_size",
                "allowed_domains",
                "include_sources",
                "include_raw_results",
                "user_location",
            }
            config["web_search"] = {
                key: value
                for key, value in config["web_search"].items()
                if key in supported_web_search_fields
            }
        provider_type = config.get("provider_type")
        if isinstance(provider_type, str) and provider_type:
            return config

        resolved_provider_type = self._resolve_provider_type_value(config.get("type"))
        if resolved_provider_type:
            config["provider_type"] = resolved_provider_type
        return config

    def _build_provider_source_response(self, source: dict) -> dict:
        return self._ensure_provider_type(copy.deepcopy(source))

    def _attach_model_metadata(self, provider: dict) -> dict:
        model_id = provider.get("model")
        if isinstance(model_id, str) and (
            metadata := self.llm_metadata_catalog.get(model_id)
        ):
            provider["model_metadata"] = metadata
        return provider

    def _build_provider_response(self, provider: dict) -> dict:
        if provider.get("provider_source_id"):
            normalized = self.provider_manager.get_merged_provider_config(provider)
        else:
            normalized = copy.deepcopy(provider)
        normalized = self._ensure_provider_type(normalized)
        return self._attach_model_metadata(normalized)

    def _build_raw_provider_response(self, provider: dict) -> dict:
        normalized = self._ensure_provider_type(copy.deepcopy(provider))
        return self._attach_model_metadata(normalized)

    def get_provider_schema(self) -> dict:
        provider_metadata = ConfigMetadataI18n.convert_to_i18n_keys(
            {
                "provider_group": {
                    "metadata": {
                        "provider": CONFIG_METADATA_2["provider_group"]["metadata"][
                            "provider"
                        ]
                    }
                }
            }
        )
        config_schema = {
            "provider": provider_metadata["provider_group"]["metadata"]["provider"]
        }
        provider_default_tmpl = config_schema["provider"]["config_template"]
        for provider in self.provider_catalog.metadata():
            if provider.default_config_tmpl:
                provider_default_tmpl[provider.type] = provider.default_config_tmpl
        providers = []
        model_metadata = {}
        for provider in self.config.get("provider", []):
            provider_response = self._build_provider_response(provider)
            model_id = provider_response.get("model")
            if isinstance(model_id, str) and "model_metadata" in provider_response:
                model_metadata[model_id] = provider_response.pop("model_metadata")
            providers.append(provider_response)

        provider_sources = [
            self._build_provider_source_response(source)
            for source in self.config.get("provider_sources", [])
        ]

        return {
            "config_schema": config_schema,
            "providers": providers,
            "provider_sources": provider_sources,
            "model_metadata": model_metadata,
        }

    def list_provider_sources(self) -> dict:
        return {
            "provider_sources": [
                self._build_provider_source_response(source)
                for source in self.config.get("provider_sources", [])
            ]
        }

    def get_provider_source(self, source_id: str) -> dict:
        source = self._find_provider_source(source_id)
        if source is None:
            raise DashboardValidationError(f"Provider source {source_id} not found")
        return {"provider_source": self._build_provider_source_response(source)}

    async def upsert_provider_source(self, source_id: str, config: dict) -> None:
        config = self._ensure_provider_type(copy.deepcopy(config))
        next_source_id = str(config.get("id") or source_id).strip()
        if not next_source_id:
            raise DashboardValidationError(
                "Provider source config must have an 'id' field"
            )
        config["id"] = next_source_id
        next_config = copy.deepcopy(dict(self.config))
        sources = next_config.setdefault("provider_sources", [])

        for source in sources:
            if source.get("id") == next_source_id and next_source_id != source_id:
                raise DashboardValidationError(
                    f"Provider source ID '{next_source_id}' exists already, please try another ID."
                )

        for idx, source in enumerate(sources):
            if source.get("id") == source_id:
                old_source_id = source.get("id") or source_id
                sources[idx] = copy.deepcopy(config)
                affected_providers = self._move_providers_to_source(
                    next_config.get("provider", []),
                    old_source_id,
                    next_source_id,
                )
                committed = await save_config_async(
                    next_config,
                    self.config,
                    is_core=True,
                )
                _require_config_save_commit(committed)
                self.provider_manager.provider_sources_config = self.config[
                    "provider_sources"
                ]
                await self._reload_providers(affected_providers)
                return

        sources.append(copy.deepcopy(config))
        committed = await save_config_async(next_config, self.config, is_core=True)
        _require_config_save_commit(committed)
        self.provider_manager.provider_sources_config = self.config["provider_sources"]

    async def delete_provider_source(self, source_id: str) -> None:
        sources = self.config.get("provider_sources", [])
        next_sources = [source for source in sources if source.get("id") != source_id]
        if len(next_sources) == len(sources):
            raise DashboardValidationError(f"Provider source {source_id} not found")
        next_config = copy.deepcopy(dict(self.config))
        next_config["provider_sources"] = copy.deepcopy(next_sources)
        committed = await save_config_async(next_config, self.config, is_core=True)
        _require_config_save_commit(committed)
        await self.provider_manager.delete_provider(provider_source_id=source_id)
        self.provider_manager.provider_sources_config = self.config["provider_sources"]

    async def list_provider_source_models(self, source_id: str) -> dict:
        source = self._find_provider_source(source_id)
        if source is None:
            raise DashboardValidationError(f"Provider source {source_id} not found")

        from astrbot.core.provider import Provider

        provider_type = source.get("type")
        if not provider_type:
            raise DashboardValidationError("Provider source missing type")
        try:
            self.provider_manager.dynamic_import_provider(provider_type)
        except ImportError as exc:
            raise DashboardValidationError(
                "动态导入提供商适配器失败，请检查提供商类型配置或查看服务端日志"
            ) from exc
        registration = self.provider_catalog.get(provider_type)
        if registration is None or not issubclass(registration.cls_type, Provider):
            raise DashboardValidationError(
                f"Provider source {source_id} does not support model list"
            )

        cls_type = registration.cls_type
        inst = cls_type(source, {})
        setattr(inst, "_provider_adapter_descriptor", registration.descriptor)
        init_fn = getattr(inst, "initialize", None)
        if callable(init_fn):
            await run_maybe_async(init_fn)
        try:
            models = await inst.get_models()
            models = models or []
            return {
                "models": models,
                "provider_source_id": source_id,
                "model_metadata": {
                    model_id: metadata
                    for model_id in models
                    if (metadata := self.llm_metadata_catalog.get(model_id))
                },
            }
        finally:
            terminate_fn = getattr(inst, "terminate", None)
            if callable(terminate_fn):
                await run_maybe_async(terminate_fn)

    async def list_provider_models(self, provider_id: str) -> dict:
        from astrbot.core.provider import Provider

        provider = self.provider_manager.inst_map.get(provider_id)
        if not provider:
            raise DashboardValidationError(f"未找到 ID 为 {provider_id} 的提供商")
        if not isinstance(provider, Provider):
            raise DashboardValidationError(
                f"提供商 {provider_id} 类型不支持获取模型列表"
            )

        models = await provider.get_models()
        models = models or []
        return {
            "models": models,
            "provider_id": provider_id,
            "model_metadata": {
                model_id: metadata
                for model_id in models
                if (metadata := self.llm_metadata_catalog.get(model_id))
            },
        }

    async def get_embedding_dimension(self, provider_config: dict | None) -> dict:
        if not provider_config:
            raise DashboardValidationError("缺少提供商配置")

        from astrbot.core.provider.provider import EmbeddingProvider

        provider_type = provider_config.get("type")
        if not provider_type:
            raise DashboardValidationError("提供商配置缺少 type 字段")

        registration = self.provider_catalog.get(provider_type)
        if registration is None:
            try:
                self.provider_manager.dynamic_import_provider(provider_type)
            except ImportError as exc:
                raise DashboardValidationError(
                    "提供商适配器加载失败，请检查提供商类型配置或查看服务端日志"
                ) from exc
            registration = self.provider_catalog.get(provider_type)

        if registration is None:
            raise DashboardValidationError(f"无法找到 {provider_type} 的类")

        cls_type = registration.cls_type
        inst = cls_type(provider_config, {})
        setattr(inst, "_provider_adapter_descriptor", registration.descriptor)
        try:
            init_fn = getattr(inst, "initialize", None)
            if callable(init_fn):
                await run_maybe_async(init_fn)

            if not isinstance(inst, EmbeddingProvider):
                raise DashboardValidationError("提供商不是 EmbeddingProvider 类型")

            vec = await inst.get_embedding("echo")
            dim = len(vec)
            logger.info(
                f"检测到 {provider_config.get('id', 'unknown')} 的嵌入向量维度为 {dim}",
            )
            return {"embedding_dimensions": dim}
        finally:
            terminate_fn = getattr(inst, "terminate", None)
            if callable(terminate_fn):
                await run_maybe_async(terminate_fn)

    def list_providers(
        self,
        *,
        provider_type: str | None = None,
        provider_source_id: str | None = None,
        enabled: bool | None = None,
    ) -> dict:
        provider_types = {
            item.strip() for item in (provider_type or "").split(",") if item.strip()
        }
        providers = []
        model_metadata = {}
        for provider in self.provider_manager.providers_config:
            if (
                provider_source_id
                and provider.get("provider_source_id") != provider_source_id
            ):
                continue
            if enabled is not None and bool(provider.get("enable", False)) != enabled:
                continue
            normalized_provider = self._build_provider_response(provider)
            effective_type = normalized_provider.get("provider_type")
            if provider_types and effective_type not in provider_types:
                continue
            model_id = normalized_provider.get("model")
            if isinstance(model_id, str) and "model_metadata" in normalized_provider:
                model_metadata[model_id] = normalized_provider.pop("model_metadata")
            providers.append(normalized_provider)
        return {"providers": providers, "model_metadata": model_metadata}

    def list_providers_for_dashboard_types(
        self, provider_type: str | None
    ) -> list[dict]:
        if not provider_type:
            raise DashboardValidationError("缺少参数 provider_type")
        return self.list_providers(provider_type=provider_type)["providers"]

    def get_provider(self, provider_id: str, *, merged: bool = False) -> dict:
        provider = self.provider_manager.get_provider_config_by_id(
            provider_id,
            merged=merged,
        )
        if provider is None:
            raise DashboardValidationError(f"Provider {provider_id} not found")
        provider_response = (
            self._build_provider_response(provider)
            if merged
            else self._build_raw_provider_response(provider)
        )
        model_id = provider_response.get("model")
        model_metadata = {}
        if isinstance(model_id, str) and "model_metadata" in provider_response:
            model_metadata[model_id] = provider_response.pop("model_metadata")
        return {"provider": provider_response, "model_metadata": model_metadata}

    async def create_provider(self, config: dict, source_id: str | None = None) -> None:
        config = copy.deepcopy(config)
        if source_id:
            config["provider_source_id"] = source_id
        else:
            self._ensure_provider_type(config)
        await self.provider_manager.create_provider(config)

    async def update_provider(self, provider_id: str, config: dict) -> None:
        config = copy.deepcopy(config)
        if not config.get("id"):
            config["id"] = provider_id
        if not config.get("provider_source_id"):
            self._ensure_provider_type(config)
        await self.provider_manager.update_provider(provider_id, config)

    async def set_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        provider = self.provider_manager.get_provider_config_by_id(provider_id)
        if provider is None:
            raise DashboardValidationError(f"Provider {provider_id} not found")
        provider["enable"] = enabled
        await self.provider_manager.update_provider(provider_id, provider)

    async def delete_provider(self, provider_id: str) -> None:
        await self.provider_manager.delete_provider(provider_id=provider_id)

    async def test_provider(self, provider_id: str) -> dict:
        target = self.provider_manager.inst_map.get(provider_id)
        if not target:
            raise DashboardValidationError(f"Provider {provider_id} not found")
        meta = target.meta()
        provider_type = getattr(meta, "provider_type", None)
        result = {
            "id": getattr(meta, "id", provider_id),
            "model": getattr(meta, "model", None),
            "type": getattr(provider_type, "value", None),
            "name": provider_id,
            "status": "unavailable",
            "error": None,
        }
        try:
            await target.test()
            result["status"] = "available"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Provider test failed: %s", safe_error("", exc))
            result["error"] = "Provider test failed"
        return result

    def _find_provider_source(self, source_id: str) -> dict | None:
        for source in self.config.get("provider_sources", []):
            if source.get("id") == source_id:
                return source
        return None

    async def _reload_providers_for_source(self, source_id: str) -> None:
        await self._reload_providers(
            [
                provider
                for provider in list(self.config.get("provider", []))
                if provider.get("provider_source_id") == source_id
            ]
        )

    def _move_providers_to_source(
        self,
        providers: list[dict],
        old_source_id: str,
        next_source_id: str,
    ) -> list[dict]:
        affected_providers = []
        for provider in providers:
            if provider.get("provider_source_id") == old_source_id:
                provider["provider_source_id"] = next_source_id
                affected_providers.append(provider)
        return affected_providers

    async def _reload_providers(self, providers: list[dict]) -> None:
        reload_fn = getattr(self.provider_manager, "reload", None)
        if not callable(reload_fn):
            return
        for provider in providers:
            await run_maybe_async(lambda provider=provider: reload_fn(provider))
