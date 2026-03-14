from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from astrbot.core import logger
from astrbot.core.star.context import Context
from astrbot.core.star.plugin_search import get_plugin_search_result_limit

from .adapters import McpTodoAdapter, PluginAdapter, SkillAdapter
from .orchestrator import ExtensionInstallOrchestrator
from .pending_operation import PendingOperationService
from .policy import ExtensionPolicyEngine

_ORCH_ATTR = "_extension_install_orchestrators"
_CLEANUP_TASK_ATTR = "_extension_pending_cleanup_task"
_DEFAULT_SCOPE_KEY = "__default__"


def _get_extension_install_config(
    config_or_provider_settings: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if not isinstance(config_or_provider_settings, Mapping):
        return {}

    provider_settings = config_or_provider_settings
    nested_provider_settings = config_or_provider_settings.get("provider_settings")
    if isinstance(nested_provider_settings, Mapping):
        provider_settings = nested_provider_settings

    extension_cfg = provider_settings.get("extension_install")
    if isinstance(extension_cfg, Mapping):
        return extension_cfg
    return {}


def is_extension_install_enabled(
    config_or_provider_settings: Mapping[str, Any] | None,
) -> bool:
    extension_cfg = _get_extension_install_config(config_or_provider_settings)
    return bool(extension_cfg.get("enable", True))


def get_extension_confirm_keywords(
    config_or_provider_settings: Mapping[str, Any] | None,
) -> tuple[str, str]:
    extension_cfg = _get_extension_install_config(config_or_provider_settings)
    confirm_keyword = str(extension_cfg.get("confirm_keyword", "")).strip()
    deny_keyword = str(extension_cfg.get("deny_keyword", "")).strip()
    if confirm_keyword or deny_keyword:
        return confirm_keyword or "确认安装", deny_keyword or "拒绝安装"

    keywords = extension_cfg.get("confirm_keywords", [])
    if isinstance(keywords, list) and len(keywords) >= 2:
        confirm_keyword = str(keywords[0]).strip() or "确认安装"
        deny_keyword = str(keywords[1]).strip() or "拒绝安装"
        return confirm_keyword, deny_keyword
    return "确认安装", "拒绝安装"


def _read_ttl_seconds(config: dict[str, Any]) -> int:
    install_cfg = _get_extension_install_config(config)
    ttl = install_cfg.get("confirmation_token_ttl_seconds", 900)
    try:
        ttl_int = int(ttl)
    except (TypeError, ValueError):
        return 900
    return max(ttl_int, 30)


def _read_cleanup_interval_seconds(config: dict[str, Any]) -> int:
    install_cfg = _get_extension_install_config(config)
    interval = install_cfg.get("pending_cleanup_interval_seconds", 300)
    try:
        interval_int = int(interval)
    except (TypeError, ValueError):
        return 300
    return max(interval_int, 30)


async def _cleanup_pending_loop(
    pending_service: PendingOperationService, interval_seconds: int
) -> None:
    while True:
        try:
            await pending_service.expire_pending_operations()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("extension pending cleanup task failed: %s", exc)
        await asyncio.sleep(interval_seconds)


def _ensure_cleanup_task(
    context: Context,
    pending_service: PendingOperationService,
    config: dict[str, Any],
) -> None:
    existing_task = getattr(context, _CLEANUP_TASK_ATTR, None)
    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    cleanup_interval = _read_cleanup_interval_seconds(config)
    task = loop.create_task(
        _cleanup_pending_loop(
            pending_service=pending_service, interval_seconds=cleanup_interval
        ),
        name="astrbot-extension-pending-cleanup",
    )
    setattr(context, _CLEANUP_TASK_ATTR, task)


def _scope_key(umo: str | None = None) -> str:
    normalized = str(umo or "").strip()
    return normalized or _DEFAULT_SCOPE_KEY


def get_extension_orchestrator(
    context: Context, *, umo: str | None = None
) -> ExtensionInstallOrchestrator:
    scope_key = _scope_key(umo)
    orchestrators = getattr(context, _ORCH_ATTR, None)
    if not isinstance(orchestrators, dict):
        orchestrators = {}
        setattr(context, _ORCH_ATTR, orchestrators)

    orchestrator = orchestrators.get(scope_key)
    if isinstance(orchestrator, ExtensionInstallOrchestrator):
        _ensure_cleanup_task(
            context,
            orchestrator.pending_service,
            context.get_config(),
        )
        return orchestrator

    config = context.get_config(umo=umo)
    pending_service = PendingOperationService(
        db=context.get_db(),
        token_ttl_seconds=_read_ttl_seconds(config),
    )
    # TODO: Unify this backend limit with the frontend extension market config.
    orchestrator = ExtensionInstallOrchestrator(
        policy_engine=ExtensionPolicyEngine(config),
        pending_service=pending_service,
        search_result_limit=get_plugin_search_result_limit(config),
        adapters=[
            PluginAdapter(context),
            SkillAdapter(context),
            McpTodoAdapter(),
        ],
    )
    orchestrators[scope_key] = orchestrator
    _ensure_cleanup_task(
        context,
        pending_service,
        context.get_config(),
    )
    return orchestrator
