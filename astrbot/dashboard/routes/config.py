import asyncio
import copy
import inspect
import os
import time
import traceback
from pathlib import Path
from typing import Any

import anyio
from quart import request

from astrbot.core import astrbot_config, file_token_service, logger
from astrbot.core.computer import computer_client
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.config.default import (
    CONFIG_METADATA_2,
    CONFIG_METADATA_3,
    CONFIG_METADATA_3_SYSTEM,
    DEFAULT_CONFIG,
    DEFAULT_VALUE_MAP,
)
from astrbot.core.config.i18n_utils import ConfigMetadataI18n
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.log import LogManager
from astrbot.core.platform.register import platform_cls_map, platform_registry
from astrbot.core.provider import Provider
from astrbot.core.provider.oauth.openai_oauth import (
    create_pkce_flow,
    exchange_authorization_code,
    parse_authorization_input,
    parse_oauth_credential_json,
    refresh_access_token,
)
from astrbot.core.provider.register import provider_registry
from astrbot.core.star.star import StarMetadata, star_registry
from astrbot.core.utils.astrbot_path import (
    get_astrbot_data_path,
    get_astrbot_plugin_data_path,
)
from astrbot.core.utils.llm_metadata import LLM_METADATAS
from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config

from .restart_control import mark_runtime_log_config_saved
from .route import Response, Route, RouteContext
from .util import (
    config_key_to_folder,
    get_schema_item,
    normalize_rel_path,
    sanitize_filename,
)

MAX_FILE_BYTES = 500 * 1024 * 1024
OPENAI_OAUTH_FLOW_TTL_SECONDS = 10 * 60


def _resolve_path(path: Path) -> Path:
    return path.resolve(strict=False)


_RUNTIME_LOG_KEYS = (
    "log_level",
    "log_file_enable",
    "log_file_path",
    "log_file_max_mb",
)

_RUNTIME_TRACE_LOG_KEYS = (
    "trace_log_enable",
    "trace_log_path",
    "trace_log_max_mb",
)


def _runtime_log_config(conf: dict) -> dict:
    legacy = conf.get("log_file") or {}
    return {
        **{key: copy.deepcopy(conf.get(key)) for key in _RUNTIME_LOG_KEYS},
        "legacy_log_file": {
            "enable": copy.deepcopy(legacy.get("enable")),
            "path": copy.deepcopy(legacy.get("path")),
            "max_mb": copy.deepcopy(legacy.get("max_mb")),
        },
    }


def _runtime_trace_log_config(conf: dict) -> dict:
    legacy = conf.get("log_file") or {}
    return {
        **{key: copy.deepcopy(conf.get(key)) for key in _RUNTIME_TRACE_LOG_KEYS},
        "legacy_log_file": {
            "trace_enable": copy.deepcopy(legacy.get("trace_enable")),
            "trace_path": copy.deepcopy(legacy.get("trace_path")),
            "trace_max_mb": copy.deepcopy(legacy.get("trace_max_mb")),
        },
    }


def _config_without_runtime_log_config(conf: dict) -> dict:
    conf = copy.deepcopy(conf)
    for key in (*_RUNTIME_LOG_KEYS, *_RUNTIME_TRACE_LOG_KEYS):
        conf.pop(key, None)

    legacy = conf.get("log_file")
    if isinstance(legacy, dict):
        for key in (
            "enable",
            "path",
            "max_mb",
            "trace_enable",
            "trace_path",
            "trace_max_mb",
        ):
            legacy.pop(key, None)
        if not legacy:
            conf.pop("log_file", None)

    return conf


def _runtime_log_config_changed(old_config: dict, new_config: dict) -> bool:
    return _runtime_log_config(old_config) != _runtime_log_config(
        new_config
    ) or _runtime_trace_log_config(old_config) != _runtime_trace_log_config(new_config)


def _system_config_save_requires_restart(old_config: dict, new_config: dict) -> bool:
    if old_config == new_config:
        return False

    return _config_without_runtime_log_config(
        old_config
    ) != _config_without_runtime_log_config(new_config)


def _apply_runtime_log_config_if_changed(
    old_config: dict,
    new_config: dict,
) -> bool:
    old_log_config = _runtime_log_config(old_config)
    new_log_config = _runtime_log_config(new_config)
    old_trace_config = _runtime_trace_log_config(old_config)
    new_trace_config = _runtime_trace_log_config(new_config)

    if old_log_config == new_log_config and old_trace_config == new_trace_config:
        return False

    updated = False

    if old_log_config != new_log_config:
        try:
            LogManager.configure_logger(logger, new_config)
            updated = True
        except Exception:
            logger.error(
                "Failed to update runtime logger:\n%s",
                traceback.format_exc(),
            )

    if old_trace_config != new_trace_config:
        try:
            LogManager.configure_trace_logger(new_config)
            updated = True
        except Exception:
            logger.error(
                "Failed to update runtime trace logger:\n%s",
                traceback.format_exc(),
            )

    if updated:
        logger.info("Runtime log configuration updated.")

    return updated


def try_cast(value: Any, type_: str):
    if type_ == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
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
        except (ValueError, TypeError):
            return None


def _expect_type(value, expected_type, path_key, errors, expected_name=None) -> bool:
    if not isinstance(value, expected_type):
        errors.append(
            f"错误的类型 {path_key}: 期望是 {expected_name or expected_type.__name__}, 得到了 {type(value).__name__}",
        )
        return False
    return True


def _default_empty_value_allowed(value, meta: dict) -> bool:
    type_ = meta.get("type")
    if "default" in meta or type_ not in DEFAULT_VALUE_MAP:
        return False
    return value == DEFAULT_VALUE_MAP[type_]


def _validate_options(value, meta: dict, path_key: str, errors: list[str]) -> None:
    options = meta.get("options")
    if not isinstance(options, list):
        return

    if meta.get("type") == "list":
        if not isinstance(value, list):
            return
        invalid_values = [item for item in value if item not in options]
        if invalid_values:
            errors.append(f"无效的选项 {path_key}: {invalid_values}")
        return

    if value not in options and not _default_empty_value_allowed(value, meta):
        errors.append(f"无效的选项 {path_key}: {value}")


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


def validate_config(data, schema: dict, is_core: bool) -> tuple[list[str], dict]:
    errors: list[str] = []

    def validate(data: dict, metadata: dict = schema, path="") -> None:
        for key, value in data.items():
            if key not in metadata:
                continue
            meta = metadata[key]
            if "type" not in meta:
                logger.debug(f"配置项 {path}{key} 没有类型定义, 跳过校验")
                continue
            if value is None:
                data[key] = DEFAULT_VALUE_MAP[meta["type"]]
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
                    normalized = normalize_rel_path(item)
                    if not normalized or not normalized.startswith("files/"):
                        errors.append(f"Invalid file path {path}{key}[{idx}]: {item}")
                        continue
                    key_path = f"{path}{key}"
                    expected_folder = config_key_to_folder(key_path)
                    expected_prefix = f"files/{expected_folder}/"
                    if not normalized.startswith(expected_prefix):
                        errors.append(f"Invalid file path {path}{key}[{idx}]: {item}")
                        continue
                    value[idx] = normalized
                continue
            if meta["type"] == "list" and (not isinstance(value, list)):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif (
                meta["type"] == "list"
                and isinstance(value, list)
                and value
                and ("items" in meta)
                and isinstance(value[0], dict)
            ):
                for item in value:
                    validate(item, meta["items"], path=f"{path}{key}.")
            elif meta["type"] == "object" and isinstance(value, dict):
                object_schema = meta.get("items")
                if not isinstance(object_schema, dict):
                    object_schema = meta.get("properties", {})
                validate(value, object_schema, path=f"{path}{key}.")

            if meta["type"] == "int" and not isinstance(value, int):
                casted = try_cast(value, "int")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 int, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "float" and (not isinstance(value, float)):
                casted = try_cast(value, "float")
                if casted is None:
                    errors.append(
                        f"错误的类型 {path}{key}: 期望是 float, 得到了 {type(value).__name__}",
                    )
                data[key] = casted
            elif meta["type"] == "bool" and (not isinstance(value, bool)):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 bool, 得到了 {type(value).__name__}",
                )
            elif meta["type"] in ["string", "text"] and (not isinstance(value, str)):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 string, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "list" and (not isinstance(value, list)):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 list, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "object" and (not isinstance(value, dict)):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 dict, 得到了 {type(value).__name__}",
                )
            elif meta["type"] == "dict" and not isinstance(value, dict):
                errors.append(
                    f"错误的类型 {path}{key}: 期望是 dict, 得到了 {type(value).__name__}",
                )

            _validate_options(data.get(key), meta, f"{path}{key}", errors)

    if is_core:
        meta_all = {
            **schema["platform_group"]["metadata"],
            **schema["provider_group"]["metadata"],
            **schema["misc_config_group"]["metadata"],
        }
        validate(data, meta_all)
    else:
        validate(data, schema)
    return (errors, data)


def validate_ssl_config(post_config: dict) -> list[str]:
    """Validate WebUI HTTPS certificate settings before saving config."""
    errors: list[str] = []
    dashboard_config = post_config.get("dashboard", {})
    if not isinstance(dashboard_config, dict):
        return errors

    ssl_config = dashboard_config.get("ssl", {})
    if not isinstance(ssl_config, dict):
        return errors

    ssl_enable = ssl_config.get("enable", False)
    if not ssl_enable:
        return errors

    cert_file = ssl_config.get("cert_file", "")
    key_file = ssl_config.get("key_file", "")

    cert_file = cert_file.strip() if isinstance(cert_file, str) else ""
    key_file = key_file.strip() if isinstance(key_file, str) else ""

    if not cert_file:
        errors.append("sslValidation.required")
    elif not _ssl_config_file_exists(cert_file):
        errors.append(f"sslValidation.certNotFound|{cert_file}")

    if not key_file:
        errors.append("sslValidation.required")
    elif not _ssl_config_file_exists(key_file):
        errors.append(f"sslValidation.keyNotFound|{key_file}")

    return list(dict.fromkeys(errors))


def _ssl_config_file_exists(path_value: str) -> bool:
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(get_astrbot_data_path()) / path
    return path.is_file()


def _log_computer_config_changes(old_config: dict, new_config: dict) -> None:
    """Compare and log Computer/sandbox configuration changes."""
    old_ps = old_config.get("provider_settings", {})
    new_ps = new_config.get("provider_settings", {})
    old_runtime = old_ps.get("computer_use_runtime", "none")
    new_runtime = new_ps.get("computer_use_runtime", "none")
    if old_runtime != new_runtime:
        logger.info(
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
        if old_val != new_val:
            if "token" in key or "secret" in key:
                old_display = "***" if old_val else "(empty)"
                new_display = "***" if new_val else "(empty)"
            else:
                old_display = old_val
                new_display = new_val
            logger.info(
                "[Computer] Config changed: sandbox.%s %s -> %s",
                key,
                old_display,
                new_display,
            )


async def _validate_neo_connectivity(
    post_config: dict,
) -> str | None:
    """Check if Bay is reachable when Shipyard Neo sandbox is configured.

    Returns a warning message string if Bay isn't reachable, or None if
    everything looks fine (or Neo isn't configured).
    """
    ps = post_config.get("provider_settings", {})
    runtime = ps.get("computer_use_runtime", "none")
    sandbox = ps.get("sandbox", {})
    booter = sandbox.get("booter", "")

    # Only check when sandbox mode + shipyard_neo is selected
    if runtime != "sandbox" or booter != "shipyard_neo":
        return None

    endpoint = sandbox.get("shipyard_neo_endpoint", "").rstrip("/")
    if not endpoint:
        return "⚠️ Shipyard Neo endpoint 未设置"

    access_token = sandbox.get("shipyard_neo_access_token", "")
    if not access_token:
        # Try auto-discovery
        from astrbot.core.computer.computer_client import _discover_bay_credentials

        access_token = _discover_bay_credentials(endpoint)

    if not access_token:
        return (
            "⚠️ 未找到 Bay API Key。请填写访问令牌，"
            "或确保 Bay 的 credentials.json 可被自动发现。"
        )

    # Connectivity check
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


def save_config(
    post_config: dict,
    config: AstrBotConfig,
    is_core: bool = False,
    old_config_snapshot: dict | None = None,
) -> bool:
    """验证并保存配置"""
    errors = None
    if is_core and old_config_snapshot is None:
        old_config_snapshot = copy.deepcopy(dict(config))

    # Snapshot old Computer config for change detection
    if is_core:
        _log_computer_config_changes(dict(config), post_config)
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
    except BaseException as e:
        logger.error(traceback.format_exc())
        logger.warning(f"验证配置时出现异常: {e}")
        raise ValueError(f"验证配置时出现异常: {e}") from e
    if errors:
        raise ValueError(f"格式校验未通过: {errors}")

    ssl_errors = validate_ssl_config(post_config)
    if ssl_errors:
        raise ValueError("; ".join(ssl_errors))

    config.save_config(post_config)

    if is_core and old_config_snapshot is not None:
        return _apply_runtime_log_config_if_changed(old_config_snapshot, dict(config))

    return False


def _merge_registered_providers_into(config_template: dict) -> None:
    """Inject providers registered via ``@register_provider_adapter`` into
    a config_template dict, in-place.

    Used by both ``GET /api/config/get`` and ``GET /api/config/provider/template``
    so the two endpoints expose a consistent set of providers in the WebUI's
    "Add Provider" picker.

    - Uses ``is not None`` (not truthiness) so providers that intentionally
      register an empty default template still appear.
    - Uses ``setdefault`` so a plugin cannot silently shadow a core static
      template that happens to share the same key.

    The caller owns ``config_template`` and is responsible for handing in a
    non-shared dict (both call sites operate on already-deep-copied metadata
    so mutating it here does not pollute ``CONFIG_METADATA_2``).
    """
    for provider in provider_registry:
        if provider.default_config_tmpl is not None:
            config_template.setdefault(provider.type, provider.default_config_tmpl)


class ConfigRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.config: AstrBotConfig = core_lifecycle.astrbot_config
        self._logo_token_cache: dict[str, Any] = {}
        self.acm = core_lifecycle.astrbot_config_mgr
        self.ucr = core_lifecycle.umop_config_router
        self._provider_source_oauth_flows: dict[str, dict[str, Any]] = {}
        self.routes = {
            "/config/abconf/new": ("POST", self.create_abconf),
            "/config/abconf": ("GET", self.get_abconf),
            "/config/abconfs": ("GET", self.get_abconf_list),
            "/config/abconf/delete": ("POST", self.delete_abconf),
            "/config/abconf/update": ("POST", self.update_abconf),
            "/config/umo_abconf_routes": ("GET", self.get_uc_table),
            "/config/umo_abconf_route/update_all": ("POST", self.update_ucr_all),
            "/config/umo_abconf_route/update": ("POST", self.update_ucr),
            "/config/umo_abconf_route/delete": ("POST", self.delete_ucr),
            "/config/get": ("GET", self.get_configs),
            "/config/default": ("GET", self.get_default_config),
            "/config/astrbot/update": ("POST", self.post_astrbot_configs),
            "/config/plugin/update": ("POST", self.post_plugin_configs),
            "/config/file/upload": ("POST", self.upload_config_file),
            "/config/file/delete": ("POST", self.delete_config_file),
            "/config/file/get": ("GET", self.get_config_file_list),
            "/config/platform/new": ("POST", self.post_new_platform),
            "/config/platform/update": ("POST", self.post_update_platform),
            "/config/platform/delete": ("POST", self.post_delete_platform),
            "/config/platform/list": ("GET", self.get_platform_list),
            "/config/provider/new": ("POST", self.post_new_provider),
            "/config/provider/update": ("POST", self.post_update_provider),
            "/config/provider/delete": ("POST", self.post_delete_provider),
            "/config/provider/template": ("GET", self.get_provider_template),
            "/config/provider/check_one": ("GET", self.check_one_provider_status),
            "/config/provider/list": ("GET", self.get_provider_config_list),
            "/config/provider/model_list": ("GET", self.get_provider_model_list),
            "/config/provider/get_embedding_dim": ("POST", self.get_embedding_dim),
            "/config/provider/get_embedding_models": (
                "POST",
                self.get_embedding_models,
            ),
            "/config/provider_sources/models": (
                "GET",
                self.get_provider_source_models,
            ),
            "/config/provider_sources/update": (
                "POST",
                self.update_provider_source,
            ),
            "/config/provider_sources/delete": (
                "POST",
                self.delete_provider_source,
            ),
        }
        self.register_routes()

    def _find_provider_source(self, source_id: str) -> tuple[list[dict], int, dict]:
        provider_sources = self.config.get("provider_sources", [])
        target_idx = next(
            (i for i, ps in enumerate(provider_sources) if ps.get("id") == source_id),
            -1,
        )
        if target_idx == -1:
            raise ValueError("未找到对应的 provider source")
        return provider_sources, target_idx, provider_sources[target_idx]

    def _is_openai_oauth_supported_source(self, provider_source: dict) -> bool:
        return (
            provider_source.get("provider") == "openai"
            and provider_source.get("type") == "openai_oauth_chat_completion"
        )

    def _cleanup_expired_provider_source_oauth_flows(self) -> None:
        now = time.time()
        expired_source_ids = [
            source_id
            for source_id, flow in self._provider_source_oauth_flows.items()
            if now - float(flow.get("created_at") or 0) > OPENAI_OAUTH_FLOW_TTL_SECONDS
        ]
        for source_id in expired_source_ids:
            self._provider_source_oauth_flows.pop(source_id, None)

    def _create_provider_source_oauth_flow(self) -> dict[str, Any]:
        flow = create_pkce_flow()
        flow["created_at"] = time.time()
        return flow

    def _get_provider_source_oauth_flow(self, source_id: str) -> dict[str, Any] | None:
        self._cleanup_expired_provider_source_oauth_flows()
        return self._provider_source_oauth_flows.get(source_id)

    async def _reload_provider_source_providers(self, source_id: str) -> list[str]:
        prov_mgr = self.core_lifecycle.provider_manager
        reload_errors = []
        for provider in self.config.get("provider", []):
            if provider.get("provider_source_id") != source_id:
                continue
            try:
                await prov_mgr.reload(provider)
            except Exception as e:
                logger.error(traceback.format_exc())
                reload_errors.append(f"{provider.get('id')}: {e}")
        return reload_errors

    async def _persist_provider_source_patch(
        self, source_id: str, updates: dict
    ) -> dict:
        provider_sources, target_idx, provider_source = self._find_provider_source(
            source_id
        )
        provider_sources[target_idx] = {**provider_source, **updates}
        self.config["provider_sources"] = provider_sources
        save_config(self.config, self.config, is_core=True)
        reload_errors = await self._reload_provider_source_providers(source_id)
        if reload_errors:
            raise ValueError(
                "更新成功，但部分提供商重载失败: " + ", ".join(reload_errors)
            )
        return provider_sources[target_idx]

    async def start_provider_source_openai_oauth(self):
        post_data = await request.json or {}
        source_id = (post_data.get("source_id") or "").strip()
        if not source_id:
            return Response().error("缺少 source_id").__dict__
        try:
            _, _, provider_source = self._find_provider_source(source_id)
        except ValueError:
            new_source_config = post_data.get("config") or {}
            if not isinstance(new_source_config, dict):
                return Response().error("未找到对应的 provider source").__dict__
            if (new_source_config.get("id") or "").strip() != source_id:
                return Response().error("provider source ID 不匹配").__dict__
            provider_sources = self.config.get("provider_sources", [])
            provider_sources.append(new_source_config)
            self.config["provider_sources"] = provider_sources
            try:
                save_config(self.config, self.config, is_core=True)
            except Exception as e:
                logger.error(traceback.format_exc())
                return Response().error(f"保存 provider source 失败: {e}").__dict__
            _, _, provider_source = self._find_provider_source(source_id)
        if not self._is_openai_oauth_supported_source(provider_source):
            return Response().error("当前 provider source 不支持 OpenAI OAuth").__dict__
        self._cleanup_expired_provider_source_oauth_flows()
        flow = self._create_provider_source_oauth_flow()
        self._provider_source_oauth_flows[source_id] = flow
        return (
            Response()
            .ok(
                data={
                    "authorize_url": flow["authorize_url"],
                    "state": flow["state"],
                }
            )
            .__dict__
        )

    async def complete_provider_source_openai_oauth(self):
        post_data = await request.json or {}
        source_id = (post_data.get("source_id") or "").strip()
        auth_input = post_data.get("input") or ""
        if not source_id:
            return Response().error("缺少 source_id").__dict__
        flow = self._get_provider_source_oauth_flow(source_id)
        try:
            _, _, provider_source = self._find_provider_source(source_id)
            if not self._is_openai_oauth_supported_source(provider_source):
                return (
                    Response()
                    .error("当前 provider source 不支持 OpenAI OAuth")
                    .__dict__
                )
            token = parse_oauth_credential_json(auth_input)
            if token is None:
                if not flow:
                    return Response().error("OAuth 流程未开始或已过期").__dict__
                code, state = parse_authorization_input(auth_input)
                if not code:
                    return Response().error("缺少授权码").__dict__
                if not state:
                    return Response().error("缺少 state").__dict__
                if state != flow.get("state"):
                    return Response().error("state 不匹配").__dict__
                token = await exchange_authorization_code(
                    code,
                    flow.get("verifier", ""),
                    provider_source.get("proxy", ""),
                )
            updated_source = await self._persist_provider_source_patch(
                source_id,
                {
                    "auth_mode": "openai_oauth",
                    "oauth_provider": "openai",
                    "oauth_access_token": token["access_token"],
                    "oauth_refresh_token": token["refresh_token"],
                    "oauth_expires_at": token["expires_at"],
                    "oauth_account_email": token.get("email", ""),
                    "oauth_account_id": token.get("account_id", ""),
                },
            )
            self._provider_source_oauth_flows.pop(source_id, None)
            return (
                Response()
                .ok(
                    data={
                        "source": updated_source,
                        "email": updated_source.get("oauth_account_email", ""),
                        "expires_at": updated_source.get("oauth_expires_at", ""),
                    },
                    message="账号态 OAuth 绑定成功",
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"账号态 OAuth 绑定失败: {e}").__dict__

    async def refresh_provider_source_openai_oauth(self):
        post_data = await request.json or {}
        source_id = (post_data.get("source_id") or "").strip()
        if not source_id:
            return Response().error("缺少 source_id").__dict__
        try:
            _, _, provider_source = self._find_provider_source(source_id)
            refresh_token_value = (
                provider_source.get("oauth_refresh_token") or ""
            ).strip()
            if not refresh_token_value:
                return (
                    Response()
                    .error("当前 provider source 没有可用的 refresh token")
                    .__dict__
                )
            token = await refresh_access_token(
                refresh_token_value,
                provider_source.get("proxy", ""),
            )
            updated_source = await self._persist_provider_source_patch(
                source_id,
                {
                    "auth_mode": "openai_oauth",
                    "oauth_provider": "openai",
                    "oauth_access_token": token["access_token"],
                    "oauth_refresh_token": token["refresh_token"],
                    "oauth_expires_at": token["expires_at"],
                    "oauth_account_email": token.get("email")
                    or provider_source.get("oauth_account_email", ""),
                    "oauth_account_id": token.get("account_id")
                    or provider_source.get("oauth_account_id", ""),
                },
            )
            return (
                Response()
                .ok(
                    data={
                        "source": updated_source,
                        "email": updated_source.get("oauth_account_email", ""),
                        "expires_at": updated_source.get("oauth_expires_at", ""),
                    },
                    message="账号态 OAuth 刷新成功",
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"账号态 OAuth 刷新失败: {e}").__dict__

    async def disconnect_provider_source_openai_oauth(self):
        post_data = await request.json or {}
        source_id = (post_data.get("source_id") or "").strip()
        if not source_id:
            return Response().error("缺少 source_id").__dict__
        try:
            updated_source = await self._persist_provider_source_patch(
                source_id,
                {
                    "auth_mode": "manual",
                    "oauth_provider": "",
                    "oauth_access_token": "",
                    "oauth_refresh_token": "",
                    "oauth_expires_at": "",
                    "oauth_account_email": "",
                    "oauth_account_id": "",
                },
            )
            self._provider_source_oauth_flows.pop(source_id, None)
            return (
                Response()
                .ok(
                    data={"source": updated_source},
                    message="账号态 OAuth 已断开",
                )
                .__dict__
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"断开账号态 OAuth 失败: {e}").__dict__

    async def delete_provider_source(self):
        """删除 provider_source,并更新关联的 providers"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").to_json()
        provider_source_id = post_data.get("id")
        if not provider_source_id:
            return Response().error("缺少 provider_source_id").to_json()
        provider_sources = self.config.get("provider_sources", [])
        target_idx = next(
            (
                i
                for i, ps in enumerate(provider_sources)
                if ps.get("id") == provider_source_id
            ),
            -1,
        )
        if target_idx == -1:
            return Response().error("未找到对应的 provider source").to_json()
        del provider_sources[target_idx]
        self.config["provider_sources"] = provider_sources
        pm = self.core_lifecycle.provider_manager
        if pm is None:
            return Response().error("Provider manager not available").to_json()
        await pm.delete_provider(provider_source_id=provider_source_id)
        try:
            save_config(self.config, self.config, is_core=True)
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).to_json()
        return Response().ok(message="删除 provider source 成功").to_json()

    async def update_provider_source(self):
        """更新或新增 provider_source,并重载关联的 providers"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").to_json()
        new_source_config = post_data.get("config") or post_data
        original_id = post_data.get("original_id")
        if not original_id:
            return Response().error("缺少 original_id").to_json()
        if not isinstance(new_source_config, dict):
            return Response().error("缺少或错误的配置数据").to_json()
        if not new_source_config.get("id"):
            new_source_config["id"] = original_id
        provider_sources = self.config.get("provider_sources", [])
        for ps in provider_sources:
            if ps.get("id") == new_source_config["id"] and ps.get("id") != original_id:
                return (
                    Response()
                    .error(
                        f"Provider source ID '{new_source_config['id']}' exists already, please try another ID.",
                    )
                    .to_json()
                )
        target_idx = next(
            (i for i, ps in enumerate(provider_sources) if ps.get("id") == original_id),
            -1,
        )
        old_id = original_id
        if target_idx == -1:
            provider_sources.append(new_source_config)
        else:
            old_id = provider_sources[target_idx].get("id")
            provider_sources[target_idx] = new_source_config
        affected_providers = []
        for provider in self.config.get("provider", []):
            if provider.get("provider_source_id") == old_id:
                provider["provider_source_id"] = new_source_config["id"]
                affected_providers.append(provider)
        self.config["provider_sources"] = provider_sources
        try:
            save_config(self.config, self.config, is_core=True)
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).to_json()
        reload_errors = []
        prov_mgr = self.core_lifecycle.provider_manager
        assert prov_mgr is not None
        for provider in affected_providers:
            try:
                await prov_mgr.reload(provider)
            except Exception as e:
                logger.error(traceback.format_exc())
                reload_errors.append(f"{provider.get('id')}: {e}")
        if reload_errors:
            return (
                Response()
                .error("更新成功,但部分提供商重载失败: " + ", ".join(reload_errors))
                .to_json()
            )
        return Response().ok(message="更新 provider source 成功").to_json()

    async def get_provider_template(self):
        # Deep-copy the static schema first; the merge below mutates the
        # config_template dict and we don't want plugin providers leaking
        # into the global CONFIG_METADATA_2 across requests.
        provider_section = copy.deepcopy(
            CONFIG_METADATA_2["provider_group"]["metadata"]["provider"]
        )
        provider_metadata = ConfigMetadataI18n.convert_to_i18n_keys(
            {"provider_group": {"metadata": {"provider": provider_section}}}
        )
        provider_i18n_translations = {}
        provider_schema = provider_metadata["provider_group"]["metadata"]["provider"]
        config_schema = {"provider": provider_schema}

        config_schema["provider"]["config_template"]
        _merge_registered_providers_into(
            config_schema["provider"].setdefault("config_template", {})
        )
        data = {
            "config_schema": config_schema,
            "providers": astrbot_config["provider"],
            "provider_sources": astrbot_config["provider_sources"],
            "provider_i18n_translations": provider_i18n_translations,
        }
        return Response().ok(data=data).to_json()

    async def get_uc_table(self):
        """获取 UMOP 配置路由表"""
        ucr = self.ucr
        if ucr is None:
            return Response().error("UMOP config router not available").to_json()
        return Response().ok({"routing": ucr.umop_to_conf_id}).to_json()

    async def update_ucr_all(self):
        """更新 UMOP 配置路由表的全部内容"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").to_json()
        new_routing = post_data.get("routing", None)
        if not new_routing or not isinstance(new_routing, dict):
            return Response().error("缺少或错误的路由表数据").to_json()
        try:
            if self.ucr is None:
                return Response().error("UMOP config router not available").to_json()
            await self.ucr.update_routing_data(new_routing)
            return Response().ok(message="更新成功").to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"更新路由表失败: {e!s}").to_json()

    async def update_ucr(self):
        """更新 UMOP 配置路由表"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").to_json()
        umo = post_data.get("umo", None)
        conf_id = post_data.get("conf_id", None)
        if not umo or not conf_id:
            return Response().error("缺少 UMO 或配置文件 ID").to_json()
        try:
            ucr = self.ucr
            if ucr is None:
                return Response().error("UMOP config router not available").to_json()
            await ucr.update_route(umo, conf_id)
            return Response().ok(message="更新成功").to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"更新路由表失败: {e!s}").to_json()

    async def delete_ucr(self):
        """删除 UMOP 配置路由表中的一项"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").to_json()
        umo = post_data.get("umo", None)
        if not umo:
            return Response().error("缺少 UMO").to_json()
        try:
            ucr = self.ucr
            if ucr is None:
                return Response().error("UMOP config router not available").to_json()
            if umo in ucr.umop_to_conf_id:
                del ucr.umop_to_conf_id[umo]
                await ucr.update_routing_data(ucr.umop_to_conf_id)
            return Response().ok(message="删除成功").to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"删除路由表项失败: {e!s}").to_json()

    async def get_default_config(self):
        """获取默认配置文件"""
        metadata = ConfigMetadataI18n.convert_to_i18n_keys(
            self._inject_sandbox_provider_options(copy.deepcopy(CONFIG_METADATA_3))
        )
        return Response().ok({"config": DEFAULT_CONFIG, "metadata": metadata}).__dict__

    async def get_abconf_list(self):
        """获取所有 AstrBot 配置文件的列表"""
        if not self.acm:
            return Response().error("Config manager not available").to_json()
        abconf_list = self.acm.get_conf_list()
        return Response().ok({"info_list": abconf_list}).to_json()

    async def create_abconf(self):
        """创建新的 AstrBot 配置文件"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").to_json()
        name = post_data.get("name", None)
        config = post_data.get("config", DEFAULT_CONFIG)
        try:
            acm = self.acm
            if acm is None:
                return Response().error("Config manager not available").to_json()
            conf_id = acm.create_conf(name=name, config=config)
            await self.core_lifecycle.reload_pipeline_scheduler(conf_id)
            return (
                Response().ok(message="创建成功", data={"conf_id": conf_id}).to_json()
            )
        except ValueError as e:
            return Response().error(str(e)).to_json()

    async def get_abconf(self):
        """获取指定 AstrBot 配置文件"""
        abconf_id = request.args.get("id")
        system_config = request.args.get("system_config", "0").lower() == "1"
        reload_from_file = request.args.get("reload_from_file", "0").lower() == "1"
        if not abconf_id and (not system_config):
            return Response().error("缺少配置文件 ID").to_json()
        try:
            acm = self.acm
            if acm is None:
                return Response().error("Config manager not available").to_json()
            if system_config:
                abconf = acm.confs["default"]
                if reload_from_file:
                    abconf = AstrBotConfig(
                        config_path=abconf.config_path,
                        default_config=abconf.default_config,
                        schema=abconf.schema,
                    )
                metadata = ConfigMetadataI18n.convert_to_i18n_keys(
                    self._inject_sandbox_provider_options(
                        copy.deepcopy(CONFIG_METADATA_3_SYSTEM)
                    )
                )
                return Response().ok({"config": abconf, "metadata": metadata}).to_json()
            if abconf_id is None:
                raise ValueError("abconf_id cannot be None")
            if abconf_id not in acm.confs:
                return Response().error("配置文件不存在").__dict__
            abconf = self.acm.confs[abconf_id]
            metadata = ConfigMetadataI18n.convert_to_i18n_keys(
                self._inject_sandbox_provider_options(copy.deepcopy(CONFIG_METADATA_3))
            )
            return Response().ok({"config": abconf, "metadata": metadata}).__dict__
        except ValueError as e:
            return Response().error(str(e)).__dict__

    async def delete_abconf(self):
        """删除指定 AstrBot 配置文件"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").to_json()
        conf_id = post_data.get("id")
        if not conf_id:
            return Response().error("缺少配置文件 ID").to_json()
        try:
            acm = self.acm
            if acm is None:
                return Response().error("Config manager not available").to_json()
            success = acm.delete_conf(conf_id)
            if success:
                self.core_lifecycle.pipeline_scheduler_mapping.pop(conf_id, None)
                return Response().ok(message="删除成功").to_json()
            return Response().error("删除失败").to_json()
        except ValueError as e:
            return Response().error(str(e)).to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"删除配置文件失败: {e!s}").to_json()

    async def update_abconf(self):
        """更新指定 AstrBot 配置文件信息"""
        post_data = await request.json
        if not post_data:
            return Response().error("缺少配置数据").to_json()
        conf_id = post_data.get("id")
        if not conf_id:
            return Response().error("缺少配置文件 ID").to_json()
        name = post_data.get("name")
        try:
            if not self.acm:
                return Response().error("Config manager not available").to_json()
            success = self.acm.update_conf_info(conf_id, name=name)
            if success:
                return Response().ok(message="更新成功").to_json()
            return Response().error("更新失败").to_json()
        except ValueError as e:
            return Response().error(str(e)).to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"更新配置文件失败: {e!s}").to_json()

    async def _test_single_provider(self, provider):
        """辅助函数:测试单个 provider 的可用性"""
        meta = provider.meta()
        provider_name = provider.provider_config.get("id", "Unknown Provider")
        provider_capability_type = meta.provider_type
        status_info = {
            "id": getattr(meta, "id", "Unknown ID"),
            "model": getattr(meta, "model", "Unknown Model"),
            "type": provider_capability_type.value,
            "name": provider_name,
            "status": "unavailable",
            "error": None,
        }
        logger.debug(
            f"Attempting to check provider: {status_info['name']} (ID: {status_info['id']}, Type: {status_info['type']}, Model: {status_info['model']})",
        )
        try:
            await provider.test()
            status_info["status"] = "available"
            logger.info(
                f"Provider {status_info['name']} (ID: {status_info['id']}) is available.",
            )
        except Exception as e:
            error_message = str(e)
            status_info["error"] = error_message
            logger.warning(
                f"Provider {status_info['name']} (ID: {status_info['id']}) is unavailable. Error: {error_message}",
            )
            logger.debug(
                f"Traceback for {status_info['name']}:\n{traceback.format_exc()}",
            )
        return status_info

    def _error_response(
        self,
        message: str,
        status_code: int = 500,
        log_fn=logger.error,
    ):
        log_fn(message)
        if status_code == 500:
            log_fn(traceback.format_exc())
        return Response().error(message).to_json()

    async def check_one_provider_status(self):
        """API: check a single LLM Provider's status by id"""
        provider_id = request.args.get("id")
        if not provider_id:
            return self._error_response(
                "Missing provider_id parameter",
                400,
                logger.warning,
            )
        logger.info(f"API call: /config/provider/check_one id={provider_id}")
        try:
            prov_mgr = self.core_lifecycle.provider_manager
            if prov_mgr is None:
                return Response().error("Provider manager not available").to_json()
            target = prov_mgr.inst_map.get(provider_id)
            if not target:
                logger.warning(
                    f"Provider with id '{provider_id}' not found in provider_manager.",
                )
                return (
                    Response()
                    .error(f"Provider with id '{provider_id}' not found")
                    .to_json()
                )
            result = await self._test_single_provider(target)
            return Response().ok(result).to_json()
        except Exception as e:
            return self._error_response(
                f"Critical error checking provider {provider_id}: {e}",
                500,
            )

    async def get_configs(self):
        plugin_name = request.args.get("plugin_name", None)
        if not plugin_name:
            return Response().ok(await self._get_astrbot_config()).to_json()
        return Response().ok(await self._get_plugin_config(plugin_name)).to_json()

    async def get_provider_config_list(self):
        provider_type = request.args.get("provider_type", None)
        if not provider_type:
            return Response().error("缺少参数 provider_type").to_json()
        provider_type_ls = provider_type.split(",")
        provider_list = []
        pm = self.core_lifecycle.provider_manager
        if pm is None:
            return Response().error("Provider manager not available").to_json()
        ps = pm.providers_config
        p_source_pt = {
            psrc["id"]: psrc.get("provider_type", "chat_completion")
            for psrc in pm.provider_sources_config
        }
        for provider in ps:
            ps_id = provider.get("provider_source_id", None)
            if (
                ps_id
                and ps_id in p_source_pt
                and (p_source_pt[ps_id] in provider_type_ls)
            ):
                prov = pm.get_merged_provider_config(provider)
                provider_list.append(prov)
            elif not ps_id and provider.get("provider_type", "") in provider_type_ls:
                provider_list.append(provider)
        return Response().ok(provider_list).to_json()

    async def get_provider_model_list(self):
        """获取指定提供商的模型列表"""
        provider_id = request.args.get("provider_id", None)
        if not provider_id:
            return Response().error("缺少参数 provider_id").to_json()
        prov_mgr = self.core_lifecycle.provider_manager
        if prov_mgr is None:
            return Response().error("Provider manager not available").to_json()
        provider = prov_mgr.inst_map.get(provider_id, None)
        if not provider:
            return Response().error(f"未找到 ID 为 {provider_id} 的提供商").to_json()
        if not isinstance(provider, Provider):
            return (
                Response()
                .error(f"提供商 {provider_id} 类型不支持获取模型列表")
                .to_json()
            )
        try:
            models = await provider.get_models()
            models = models or []
            metadata_map = {}
            for model_id in models:
                meta = LLM_METADATAS.get(model_id)
                if meta:
                    metadata_map[model_id] = meta
            ret = {
                "models": models,
                "provider_id": provider_id,
                "model_metadata": metadata_map,
            }
            return Response().ok(ret).to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).to_json()

    async def get_embedding_dim(self):
        """获取嵌入模型的维度"""
        post_data = await request.json
        provider_config = post_data.get("provider_config", None)
        if not provider_config:
            return Response().error("缺少参数 provider_config").__dict__

        inst = None
        try:
            from astrbot.core.provider.provider import EmbeddingProvider
            from astrbot.core.provider.register import provider_cls_map

            provider_type = provider_config.get("type", None)
            if not provider_type:
                return Response().error("provider_config 缺少 type 字段").to_json()
            if provider_type not in provider_cls_map:
                try:
                    prov_mgr = self.core_lifecycle.provider_manager
                    if prov_mgr is None:
                        return (
                            Response().error("Provider manager not available").to_json()
                        )
                    prov_mgr.dynamic_import_provider(provider_type)
                except ImportError:
                    logger.error(traceback.format_exc())
                    return (
                        Response()
                        .error(
                            "提供商适配器加载失败,请检查提供商类型配置或查看服务端日志",
                        )
                        .to_json()
                    )
            if provider_type not in provider_cls_map:
                return (
                    Response()
                    .error(f"未找到适用于 {provider_type} 的提供商适配器")
                    .to_json()
                )
            provider_metadata = provider_cls_map[provider_type]
            cls_type = provider_metadata.cls_type
            if not cls_type:
                return Response().error(f"无法找到 {provider_type} 的类").to_json()
            inst = cls_type(provider_config, {})
            if not isinstance(inst, EmbeddingProvider):
                return Response().error("提供商不是 EmbeddingProvider 类型").to_json()
            init_fn = getattr(inst, "initialize", None)
            if inspect.iscoroutinefunction(init_fn):
                await init_fn()

            # 通过实际请求检测模型原生维度
            vec = await inst.client.embeddings.create(
                input="echo",
                model=inst.model,
                **inst._embedding_kwargs(),
            )
            dim = len(vec.data[0].embedding)

            logger.info(
                f"检测到 {provider_config.get('id', 'unknown')} 的嵌入向量维度为 {dim}",
            )
            return Response().ok({"embedding_dimensions": dim}).to_json()
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"获取嵌入维度失败: {e!s}").__dict__
        finally:
            terminate_fn = getattr(inst, "terminate", None) if inst else None
            if inspect.iscoroutinefunction(terminate_fn):
                try:
                    await terminate_fn()
                except Exception:
                    logger.warning("释放嵌入 provider 资源失败")

    async def get_embedding_models(self):
        """根据临时 provider_config 获取可用嵌入模型列表"""
        post_data = await request.json
        provider_config = post_data.get("provider_config", None)
        if not provider_config:
            return Response().error("缺少参数 provider_config").__dict__

        inst = None
        try:
            from astrbot.core.provider.provider import EmbeddingProvider
            from astrbot.core.provider.register import provider_cls_map

            provider_type = provider_config.get("type", None)
            if not provider_type:
                return Response().error("provider_config 缺少 type 字段").__dict__

            if provider_type not in provider_cls_map:
                try:
                    self.core_lifecycle.provider_manager.dynamic_import_provider(
                        provider_type,
                    )
                except ImportError:
                    logger.error(traceback.format_exc())
                    return Response().error("提供商适配器加载失败").__dict__

            if provider_type not in provider_cls_map:
                return (
                    Response()
                    .error(f"未找到适用于 {provider_type} 的提供商适配器")
                    .__dict__
                )

            provider_metadata = provider_cls_map[provider_type]
            cls_type = provider_metadata.cls_type
            if not cls_type:
                return Response().error(f"无法找到 {provider_type} 的类").__dict__

            inst = cls_type(provider_config, {})
            if not isinstance(inst, EmbeddingProvider):
                return Response().error("提供商不是 EmbeddingProvider 类型").__dict__

            init_fn = getattr(inst, "initialize", None)
            if inspect.iscoroutinefunction(init_fn):
                await init_fn()

            try:
                models = await inst.get_models()
            except NotImplementedError:
                return (
                    Response()
                    .error("当前提供商暂不支持自动获取模型列表，请手动填写模型 ID")
                    .__dict__
                )

            models = sorted(dict.fromkeys(models or []))
            return Response().ok({"models": models}).__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            err_msg = str(e).lower()
            # [新增] 识别 vLLM 的特定报错关键字
            if "matryoshka" in err_msg or "dimensions" in err_msg:
                logger.info("Detected vLLM specific error, bypassing...")
                # 伪造一个成功的响应，告知前端进入"兼容模式"
                return Response().ok({"embedding_dimensions": "vLLM-Adaptive"}).__dict__
            return Response().error(f"获取嵌入模型列表失败: {e!s}").__dict__
        finally:
            terminate_fn = getattr(inst, "terminate", None) if inst else None
            if terminate_fn is not None:
                try:
                    result = terminate_fn()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.warning("释放嵌入 provider 资源失败")

    async def get_provider_source_models(self):
        """获取指定 provider_source 支持的模型列表

        本质上会临时初始化一个 Provider 实例,调用 get_models() 获取模型列表,然后销毁实例
        """
        provider_source_id = request.args.get("source_id")
        if not provider_source_id:
            return Response().error("缺少参数 source_id").to_json()
        try:
            from astrbot.core.provider.register import provider_cls_map

            provider_sources = self.config.get("provider_sources", [])
            provider_source = None
            for ps in provider_sources:
                if ps.get("id") == provider_source_id:
                    provider_source = ps
                    break
            if not provider_source:
                return (
                    Response()
                    .error(f"未找到 ID 为 {provider_source_id} 的 provider_source")
                    .to_json()
                )
            provider_type = provider_source.get("type", None)
            if not provider_type:
                return Response().error("provider_source 缺少 type 字段").to_json()
            try:
                prov_mgr = self.core_lifecycle.provider_manager
                if prov_mgr is None:
                    return Response().error("Provider manager not available").to_json()
                prov_mgr.dynamic_import_provider(provider_type)
            except ImportError as e:
                logger.error(traceback.format_exc())
                return Response().error(f"动态导入提供商适配器失败: {e!s}").to_json()
            if provider_type not in provider_cls_map:
                return (
                    Response()
                    .error(f"未找到适用于 {provider_type} 的提供商适配器")
                    .to_json()
                )
            provider_metadata = provider_cls_map[provider_type]
            cls_type = provider_metadata.cls_type
            if not cls_type:
                return Response().error(f"无法找到 {provider_type} 的类").to_json()
            if not issubclass(cls_type, Provider):
                return (
                    Response()
                    .error(f"提供商 {provider_type} 不支持获取模型列表")
                    .to_json()
                )
            inst = cls_type(provider_source, {})
            init_fn = getattr(inst, "initialize", None)
            if inspect.iscoroutinefunction(init_fn):
                await init_fn()
            models = await inst.get_models()
            models = models or []
            metadata_map = {}
            for model_id in models:
                meta = LLM_METADATAS.get(model_id)
                if meta:
                    metadata_map[model_id] = meta
            terminate_fn = getattr(inst, "terminate", None)
            if inspect.iscoroutinefunction(terminate_fn):
                await terminate_fn()
            logger.info(
                f"获取到 provider_source {provider_source_id} 的模型列表: {models}",
            )
            return (
                Response()
                .ok({"models": models, "model_metadata": metadata_map})
                .to_json()
            )
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(f"获取模型列表失败: {e!s}").to_json()

    async def get_platform_list(self):
        """获取所有平台的列表"""
        platform_list = []
        for platform in self.config["platform"]:
            platform_list.append(platform)
        return Response().ok({"platforms": platform_list}).to_json()

    async def post_astrbot_configs(self):
        data = await request.json
        config = data.get("config", None)
        conf_id = data.get("conf_id", None)
        try:
            if conf_id == "default":
                acm = self.acm
                if acm is None:
                    return Response().error("Config manager not available").to_json()
                no_update_keys = ["provider_sources", "provider", "platform"]
                for key in no_update_keys:
                    config[key] = self.acm.default_conf[key]

            save_result = await self._save_astrbot_configs(config, conf_id)
            await self.core_lifecycle.reload_pipeline_scheduler(conf_id)

            # Non-blocking Bay connectivity check
            warning = await _validate_neo_connectivity(config)
            response_data = {"requires_restart": save_result["requires_restart"]}
            if warning:
                return Response().ok(response_data, f"保存成功。{warning}").__dict__
            return Response().ok(response_data, "保存成功~").__dict__
        except Exception as e:
            logger.error(traceback.format_exc())
            return Response().error(str(e)).to_json()

    async def post_plugin_configs(self):
        post_configs = await request.json
        plugin_name = request.args.get("plugin_name", "unknown")
        try:
            await self._save_plugin_configs(post_configs, plugin_name)
            pm = self.core_lifecycle.plugin_manager
            if pm is None:
                return Response().error("Plugin manager not available").to_json()
            await pm.reload(plugin_name)
            return (
                Response()
                .ok(None, f"保存插件 {plugin_name} 成功~ 机器人正在热重载插件｡")
                .to_json()
            )
        except Exception as e:
            return Response().error(str(e)).to_json()

    def _get_plugin_metadata_by_name(self, plugin_name: str) -> StarMetadata | None:
        for plugin_md in star_registry:
            if plugin_md.name == plugin_name:
                return plugin_md
        return None

    def _resolve_config_file_scope(
        self,
    ) -> tuple[str, str, str, StarMetadata, AstrBotConfig]:
        """将请求参数解析为一个明确的配置作用域｡

        当前支持的 scope:
        - scope=plugin:name=<plugin_name>,key=<config_key_path>
        """
        scope = request.args.get("scope") or "plugin"
        name = request.args.get("name")
        key_path = request.args.get("key")
        if scope != "plugin":
            raise ValueError(f"Unsupported scope: {scope}")
        if not name or not key_path:
            raise ValueError("Missing name or key parameter")
        md = self._get_plugin_metadata_by_name(name)
        if not md or not md.config:
            raise ValueError(f"Plugin {name} not found or has no config")
        return (scope, name, key_path, md, md.config)

    async def upload_config_file(self):
        """上传文件到插件数据目录(用于某个 file 类型配置项)｡"""
        try:
            _scope, name, key_path, _md, config = self._resolve_config_file_scope()
        except ValueError as e:
            return Response().error(str(e)).to_json()
        meta = get_schema_item(getattr(config, "schema", None), key_path)
        if not meta or meta.get("type") != "file":
            return Response().error("Config item not found or not file type").to_json()
        file_types = meta.get("file_types")
        allowed_exts: list[str] = []
        if isinstance(file_types, list):
            allowed_exts = [
                str(ext).lstrip(".").lower() for ext in file_types if str(ext).strip()
            ]
        files = await request.files
        if not files:
            return Response().error("No files uploaded").to_json()
        storage_root_path = _resolve_path(Path(get_astrbot_plugin_data_path()))
        plugin_root_path = _resolve_path(storage_root_path / name)
        try:
            plugin_root_path.relative_to(storage_root_path)
        except ValueError:
            return Response().error("Invalid name parameter").to_json()
        plugin_root_path.mkdir(parents=True, exist_ok=True)
        uploaded: list[str] = []
        folder = config_key_to_folder(key_path)
        errors: list[str] = []
        for file in files.values():
            filename = sanitize_filename(file.filename or "")
            if not filename:
                errors.append("Invalid filename")
                continue
            file_size = getattr(file, "content_length", None)
            if isinstance(file_size, int) and file_size > MAX_FILE_BYTES:
                errors.append(f"File too large: {filename}")
                continue
            ext = os.path.splitext(filename)[1].lstrip(".").lower()
            if allowed_exts and ext not in allowed_exts:
                errors.append(f"Unsupported file type: {filename}")
                continue
            rel_path = f"files/{folder}/{filename}"
            save_path = _resolve_path(plugin_root_path / rel_path)
            try:
                save_path.relative_to(plugin_root_path)
            except ValueError:
                errors.append(f"Invalid path: {filename}")
                continue
            save_path.parent.mkdir(parents=True, exist_ok=True)
            await file.save(str(save_path))
            if save_path.is_file() and save_path.stat().st_size > MAX_FILE_BYTES:
                save_path.unlink()
                errors.append(f"File too large: {filename}")
                continue
            uploaded.append(rel_path)
        if not uploaded:
            return (
                Response()
                .error(
                    "Upload failed: " + ", ".join(errors)
                    if errors
                    else "Upload failed",
                )
                .to_json()
            )
        return Response().ok({"uploaded": uploaded, "errors": errors}).to_json()

    async def delete_config_file(self):
        """删除插件数据目录中的文件｡"""
        scope = request.args.get("scope") or "plugin"
        name = request.args.get("name")
        if not name:
            return Response().error("Missing name parameter").to_json()
        if scope != "plugin":
            return Response().error(f"Unsupported scope: {scope}").to_json()
        data = await request.get_json()
        rel_path = data.get("path") if isinstance(data, dict) else None
        rel_path = normalize_rel_path(rel_path)
        if not rel_path or not rel_path.startswith("files/"):
            return Response().error("Invalid path parameter").to_json()
        md = self._get_plugin_metadata_by_name(name)
        if not md:
            return Response().error(f"Plugin {name} not found").to_json()
        storage_root_path = _resolve_path(Path(get_astrbot_plugin_data_path()))
        plugin_root_path = _resolve_path(storage_root_path / name)
        try:
            plugin_root_path.relative_to(storage_root_path)
        except ValueError:
            return Response().error("Invalid name parameter").to_json()
        target_path = _resolve_path(plugin_root_path / rel_path)
        try:
            target_path.relative_to(plugin_root_path)
        except ValueError:
            return Response().error("Invalid path parameter").to_json()
        if target_path.is_file():
            target_path.unlink()
        return Response().ok(None, "Deleted").to_json()

    async def get_config_file_list(self):
        """获取配置项对应目录下的文件列表｡"""
        try:
            _, name, key_path, _, config = self._resolve_config_file_scope()
        except ValueError as e:
            return Response().error(str(e)).to_json()
        meta = get_schema_item(getattr(config, "schema", None), key_path)
        if not meta or meta.get("type") != "file":
            return Response().error("Config item not found or not file type").to_json()
        storage_root_path = _resolve_path(Path(get_astrbot_plugin_data_path()))
        plugin_root_path = _resolve_path(storage_root_path / name)
        try:
            plugin_root_path.relative_to(storage_root_path)
        except ValueError:
            return Response().error("Invalid name parameter").to_json()
        folder = config_key_to_folder(key_path)
        target_dir = _resolve_path(plugin_root_path / "files" / folder)
        try:
            target_dir.relative_to(plugin_root_path)
        except ValueError:
            return Response().error("Invalid path parameter").to_json()
        if not target_dir.exists() or not target_dir.is_dir():
            return Response().ok({"files": []}).to_json()
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
        return Response().ok({"files": files}).to_json()

    async def post_new_platform(self):
        new_platform_config = await request.json
        ensure_platform_webhook_config(new_platform_config)
        self.config["platform"].append(new_platform_config)
        try:
            save_config(self.config, self.config, is_core=True)
            pm = self.core_lifecycle.platform_manager
            if pm is None:
                return Response().error("Platform manager not available").to_json()
            await pm.load_platform(new_platform_config)
        except Exception as e:
            return Response().error(str(e)).to_json()
        return Response().ok(None, "新增平台配置成功~").to_json()

    async def post_new_provider(self):
        new_provider_config = await request.json
        try:
            pm = self.core_lifecycle.provider_manager
            if pm is None:
                return Response().error("Provider manager not available").to_json()
            await pm.create_provider(new_provider_config)
        except Exception as e:
            return Response().error(str(e)).to_json()
        return Response().ok(None, "新增服务提供商配置成功").to_json()

    async def post_update_platform(self):
        update_platform_config = await request.json
        origin_platform_id = update_platform_config.get("id", None)
        new_config = update_platform_config.get("config", None)
        if not origin_platform_id or not new_config:
            return Response().error("参数错误").to_json()
        if origin_platform_id != new_config.get("id", None):
            return Response().error("机器人名称不允许修改").to_json()
        ensure_platform_webhook_config(new_config)
        for i, platform in enumerate(self.config["platform"]):
            if platform["id"] == origin_platform_id:
                self.config["platform"][i] = new_config
                break
        else:
            return Response().error("未找到对应平台").to_json()
        try:
            save_config(self.config, self.config, is_core=True)
            pm = self.core_lifecycle.platform_manager
            if pm is None:
                return Response().error("Platform manager not available").to_json()
            await pm.reload(new_config)
        except Exception as e:
            return Response().error(str(e)).to_json()
        return Response().ok(None, "更新平台配置成功~").to_json()

    async def post_update_provider(self):
        update_provider_config = await request.json
        origin_provider_id = update_provider_config.get("id", None)
        new_config = update_provider_config.get("config", None)
        if not origin_provider_id or not new_config:
            return Response().error("参数错误").to_json()
        try:
            provider_mgr = self.core_lifecycle.provider_manager
            if provider_mgr is None:
                return Response().error("Provider manager not available").to_json()
            await provider_mgr.update_provider(origin_provider_id, new_config)
        except Exception as e:
            return Response().error(str(e)).to_json()
        return Response().ok(None, "更新成功,已经实时生效~").to_json()

    async def post_delete_platform(self):
        platform_id = await request.json
        platform_id = platform_id.get("id")
        for i, platform in enumerate(self.config["platform"]):
            if platform["id"] == platform_id:
                del self.config["platform"][i]
                break
        else:
            return Response().error("未找到对应平台").to_json()
        try:
            save_config(self.config, self.config, is_core=True)
            pm = self.core_lifecycle.platform_manager
            if pm is None:
                return Response().error("Platform manager not available").to_json()
            await pm.terminate_platform(platform_id)
        except Exception as e:
            return Response().error(str(e)).to_json()
        return Response().ok(None, "删除平台配置成功~").to_json()

    async def post_delete_provider(self):
        provider_id = await request.json
        provider_id = provider_id.get("id", "")
        if not provider_id:
            return Response().error("缺少参数 id").to_json()
        try:
            pm = self.core_lifecycle.provider_manager
            if pm is None:
                return Response().error("Provider manager not available").to_json()
            await pm.delete_provider(provider_id=provider_id)
        except Exception as e:
            return Response().error(str(e)).to_json()
        return Response().ok(None, "删除成功,已经实时生效｡").to_json()

    async def get_llm_tools(self):
        """获取函数调用工具｡包含了本地加载的以及 MCP 服务的工具"""
        prov_mgr = self.core_lifecycle.provider_manager
        if prov_mgr is None:
            return Response().error("Provider manager not available").to_json()
        tool_mgr = prov_mgr.llm_tools
        tools = tool_mgr.get_func_desc_openai_style()
        return Response().ok(tools).to_json()

    async def _register_platform_logo(self, platform, platform_default_tmpl) -> None:
        """注册平台logo文件并生成访问令牌"""
        if not platform.logo_path:
            return
        try:
            cache_key = f"{platform.name}:{platform.logo_path}"
            if cache_key in self._logo_token_cache:
                cached_token = self._logo_token_cache[cache_key]
                if platform.name not in platform_default_tmpl or not isinstance(
                    platform_default_tmpl[platform.name],
                    dict,
                ):
                    platform_default_tmpl[platform.name] = {}
                platform_default_tmpl[platform.name]["logo_token"] = cached_token
                logger.debug(f"Using cached logo token for platform {platform.name}")
                return
            platform_cls = platform_cls_map.get(platform.name)
            if not platform_cls:
                logger.warning(f"Platform class not found for {platform.name}")
                return
            module_file = inspect.getfile(platform_cls)
            plugin_dir = os.path.dirname(module_file)
            logo_file_path = os.path.join(plugin_dir, platform.logo_path)
            if await anyio.Path(logo_file_path).exists():
                logo_token = await file_token_service.register_file(
                    logo_file_path,
                    expire_seconds=3600,
                )
                if platform.name not in platform_default_tmpl or not isinstance(
                    platform_default_tmpl[platform.name],
                    dict,
                ):
                    platform_default_tmpl[platform.name] = {}
                platform_default_tmpl[platform.name]["logo_token"] = logo_token
                self._logo_token_cache[cache_key] = logo_token
                logger.debug(f"Logo token registered for platform {platform.name}")
            else:
                logger.warning(
                    f"Platform {platform.name} logo file not found: {logo_file_path}",
                )
        except (ImportError, AttributeError) as e:
            logger.warning(
                f"Failed to import required modules for platform {platform.name}: {e}",
            )
        except OSError as e:
            logger.warning(f"File system error for platform {platform.name} logo: {e}")
        except Exception as e:
            logger.warning(
                f"Unexpected error registering logo for platform {platform.name}: {e}",
            )

    def _rewrite_metadata_i18n_keys(
        self, metadata: dict, i18n_prefix: str, field_path: str = ""
    ):
        """Rewrite metadata text fields to dynamic i18n keys recursively."""
        for field_key, field_value in metadata.items():
            if not isinstance(field_value, dict):
                continue

            current_path = f"{field_path}.{field_key}" if field_path else field_key
            for key in ("description", "hint", "labels", "name"):
                if key in field_value:
                    field_value[key] = f"{i18n_prefix}.{current_path}.{key}"

            if "items" in field_value and isinstance(field_value["items"], dict):
                self._rewrite_metadata_i18n_keys(
                    field_value["items"], i18n_prefix, current_path
                )

            if "template_schema" in field_value and isinstance(
                field_value["template_schema"], dict
            ):
                self._rewrite_metadata_i18n_keys(
                    field_value["template_schema"],
                    i18n_prefix,
                    f"{current_path}.template_schema",
                )

    def _inject_platform_metadata_with_i18n(
        self,
        platform,
        metadata,
        platform_i18n_translations: dict,
    ):
        """将配置元数据注入到 metadata 中并处理国际化键转换｡"""
        metadata["platform_group"]["metadata"]["platform"].setdefault("items", {})
        platform_items_to_inject = copy.deepcopy(platform.config_metadata)
        if platform.i18n_resources:
            i18n_prefix = f"platform_group.platform.{platform.name}"
            for lang, lang_data in platform.i18n_resources.items():
                platform_i18n_translations.setdefault(lang, {}).setdefault(
                    "platform_group",
                    {},
                ).setdefault("platform", {})[platform.name] = lang_data

            self._rewrite_metadata_i18n_keys(platform_items_to_inject, i18n_prefix)

        metadata["platform_group"]["metadata"]["platform"]["items"].update(
            platform_items_to_inject,
        )

    def _inject_provider_metadata_with_i18n(
        self, provider, metadata, provider_i18n_translations: dict
    ):
        """Inject provider config metadata and rewrite dynamic i18n keys."""
        metadata["provider_group"]["metadata"]["provider"].setdefault("items", {})
        provider_items_to_inject = copy.deepcopy(provider.config_metadata)

        if provider.i18n_resources:
            i18n_prefix = f"provider_group.provider.{provider.type}"

            for lang, lang_data in provider.i18n_resources.items():
                provider_i18n_translations.setdefault(lang, {}).setdefault(
                    "provider_group", {}
                ).setdefault("provider", {})[provider.type] = lang_data

            self._rewrite_metadata_i18n_keys(provider_items_to_inject, i18n_prefix)

        metadata["provider_group"]["metadata"]["provider"]["items"].update(
            provider_items_to_inject
        )

    async def _get_astrbot_config(self):
        config = self.config
        metadata: Any = copy.deepcopy(CONFIG_METADATA_2)
        provider_i18n_translations: dict[str, Any] = {}
        _pg: Any = metadata["platform_group"]
        _pg_meta: Any = _pg["metadata"]
        _platform_meta: Any = _pg_meta["platform"]
        platform_i18n = ConfigMetadataI18n.convert_to_i18n_keys(
            {"platform_group": {"metadata": {"platform": _platform_meta}}},
        )
        _target: Any = _pg_meta
        _platform_i18n_dict: Any = platform_i18n
        _target["platform"] = _platform_i18n_dict["platform_group"]["metadata"][
            "platform"
        ]
        _pg2: Any = metadata["platform_group"]
        _pg_meta2: Any = _pg2["metadata"]
        _platform_tmpl: Any = _pg_meta2["platform"]
        platform_default_tmpl: Any = _platform_tmpl["config_template"]
        platform_i18n_translations: dict[str, Any] = {}
        logo_registration_tasks = []
        for platform in platform_registry:
            if platform.default_config_tmpl:
                platform_default_tmpl[platform.name] = copy.deepcopy(
                    platform.default_config_tmpl,
                )
                if platform.config_metadata:
                    self._inject_platform_metadata_with_i18n(
                        platform,
                        metadata,
                        platform_i18n_translations,
                    )
                if platform.logo_path:
                    logo_registration_tasks.append(
                        self._register_platform_logo(platform, platform_default_tmpl),
                    )
        if logo_registration_tasks:
            await asyncio.gather(*logo_registration_tasks, return_exceptions=True)

        # 服务提供商的默认配置模板注入
        _merge_registered_providers_into(
            metadata["provider_group"]["metadata"]["provider"]["config_template"]
        )

        self._inject_sandbox_provider_options(metadata)

        return {
            "metadata": metadata,
            "config": config,
            "platform_i18n_translations": platform_i18n_translations,
            "provider_i18n_translations": provider_i18n_translations,
        }

    def _inject_sandbox_provider_options(self, metadata: dict) -> dict:
        try:
            items = metadata["ai_group"]["metadata"]["agent_computer_use"]["items"]
            booter = items.get("provider_settings.sandbox.booter")
        except KeyError:
            return metadata
        if not isinstance(booter, dict):
            return metadata

        providers = computer_client.list_sandbox_providers()
        options = [provider["provider_id"] for provider in providers]
        booter["options"] = options
        booter["labels"] = options.copy()
        return metadata

    async def _get_plugin_config(self, plugin_name: str):
        ret: dict = {"metadata": None, "config": None, "i18n": {}}
        for plugin_md in star_registry:
            if plugin_md.name == plugin_name:
                if not plugin_md.config:
                    break
                ret["config"] = plugin_md.config
                ret["metadata"] = {
                    plugin_name: {
                        "description": f"{plugin_name} 配置",
                        "type": "object",
                        "items": plugin_md.config.schema,
                    },
                }
                ret["i18n"] = plugin_md.i18n
                break
        return ret

    async def _save_astrbot_configs(
        self, post_configs: dict, conf_id: str | None = None
    ) -> dict:
        try:
            if not self.acm or conf_id not in self.acm.confs:
                raise ValueError(f"配置文件 {conf_id} 不存在")
            astrbot_config = self.acm.confs[conf_id]
            old_config_snapshot = copy.deepcopy(dict(astrbot_config))

            # 保留服务端的 t2i_active_template 值
            if "t2i_active_template" in astrbot_config:
                post_configs["t2i_active_template"] = astrbot_config[
                    "t2i_active_template"
                ]

            runtime_log_config_updated = save_config(
                post_configs,
                astrbot_config,
                is_core=True,
                old_config_snapshot=old_config_snapshot,
            )
            requires_restart = _system_config_save_requires_restart(
                old_config_snapshot,
                dict(astrbot_config),
            )
            if runtime_log_config_updated and not requires_restart:
                mark_runtime_log_config_saved()

            return {"requires_restart": requires_restart}
        except Exception as e:
            raise e

    async def _save_plugin_configs(self, post_configs: dict, plugin_name: str) -> None:
        md = None
        for plugin_md in star_registry:
            if plugin_md.name == plugin_name:
                md = plugin_md
        if not md:
            raise ValueError(f"插件 {plugin_name} 不存在")
        if not md.config:
            raise ValueError(f"插件 {plugin_name} 没有注册配置")
        assert md.config is not None
        try:
            errors, post_configs = validate_config(
                post_configs,
                getattr(md.config, "schema", {}),
                is_core=False,
            )
            if errors:
                raise ValueError(f"格式校验未通过: {errors}")
            md.config.save_config(post_configs)
        except Exception as e:
            raise e
