"""Handshake snapshot for isolated legacy plugins.

Legacy plugins synchronously read host state that only exists in the core
process (global config, provider registry, personas, per-session provider
preferences). The bridge captures a JSON-safe snapshot at plugin start and
ships it in the initialize handshake; the compat layer serves the old sync
getters from it. The snapshot is frozen at load time: runtime edits to the
global config, providers, or personas only reach the plugin after a reload.
"""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot.core.star.context import Context

# Words marking a config value as sensitive; matched case-insensitively
# against every word of a config key (split on '_', '-', and whitespace).
_SENSITIVE_WORDS = frozenset(
    {"key", "secret", "password", "token", "credential", "credentials", "passphrase"}
)
_WORD_SPLIT = re.compile(r"[_\-\s]+")


def _redact(value: Any) -> Any:
    """Deep-copy one config tree, blanking values under sensitive keys."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _SENSITIVE_WORDS & set(_WORD_SPLIT.split(str(key).lower())):
                redacted[key] = ""
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _provider_entries(providers: Any) -> list[dict[str, Any]]:
    """Serialize provider instances to {id, model, type} dicts."""
    entries = []
    for provider in providers or []:
        try:
            meta = provider.meta()
        except Exception:  # a broken provider must not break plugin loading
            continue
        entries.append(
            {"id": str(meta.id), "model": meta.model, "type": str(meta.type)}
        )
    return entries


def _tool_entries(func_list: Any) -> list[dict[str, Any]]:
    """Serialize registered function tools to JSON-safe dicts."""
    entries = []
    for tool in func_list or []:
        try:
            entries.append(
                {
                    "name": str(tool.name),
                    "description": str(tool.description),
                    "parameters": copy.deepcopy(dict(tool.parameters or {})),
                    "active": bool(getattr(tool, "active", True)),
                }
            )
        except Exception:  # a broken tool must not break plugin loading
            continue
    return entries


def _platform_entries(instances: Any) -> list[dict[str, Any]]:
    """Serialize running platform adapters to metadata dicts."""
    entries = []
    for instance in instances or []:
        try:
            meta = instance.meta()
        except Exception:  # a broken adapter must not break plugin loading
            continue
        entries.append(
            {
                "id": str(meta.id),
                "name": str(meta.name),
                "description": meta.description,
                "adapter_display_name": meta.adapter_display_name,
                # Legacy plugins read platform.config (e.g. the qq_official
                # appid); ship it redacted like get_config does.
                "config": _redact(getattr(instance, "config", None) or {}),
            }
        )
    return entries


def handoff_entries(orchestrator: Any) -> list[dict[str, Any]]:
    """Serialize SubAgentOrchestrator handoffs into JSON-safe entries.

    Args:
        orchestrator: Core SubAgentOrchestrator, or None when unconfigured.

    Returns:
        List of handoff records with the fields legacy plugins read.
    """
    return [
        {
            "name": handoff.name,
            "description": handoff.description,
            "provider_id": handoff.provider_id,
            "agent_name": getattr(getattr(handoff, "agent", None), "name", ""),
        }
        for handoff in (getattr(orchestrator, "handoffs", None) or [])
    ]


def _handler_entries() -> list[dict[str, Any]]:
    """Serialize the global handler registry into JSON-safe entries.

    Help-panel style legacy plugins enumerate ``star_handlers_registry``
    directly; the compat facade rebuilds it from this list. Filter payloads
    keep only the fields those plugins read (isinstance checks plus command
    names/aliases/regex text); enum values are shipped as ints aligned with
    the facade's own Flag enums.

    Returns:
        List of handler records for the legacy handshake snapshot.
    """
    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.filter.command_group import CommandGroupFilter
    from astrbot.core.star.filter.event_message_type import EventMessageTypeFilter
    from astrbot.core.star.filter.permission import PermissionTypeFilter
    from astrbot.core.star.filter.platform_adapter_type import (
        PlatformAdapterTypeFilter,
    )
    from astrbot.core.star.filter.regex import RegexFilter
    from astrbot.core.star.star import star_map
    from astrbot.core.star.star_handler import star_handlers_registry

    entries: list[dict[str, Any]] = []
    for handler in star_handlers_registry:
        plugin = star_map.get(handler.handler_module_path)
        filters: list[dict[str, Any]] = []
        for event_filter in handler.event_filters:
            payload: dict[str, Any] | None = None
            if isinstance(event_filter, CommandGroupFilter):
                payload = {
                    "type": "command_group",
                    "name": event_filter.group_name,
                    "alias": sorted(event_filter.alias),
                }
            elif isinstance(event_filter, CommandFilter):
                payload = {
                    "type": "command",
                    "name": event_filter.command_name,
                    "alias": sorted(event_filter.alias),
                }
            elif isinstance(event_filter, RegexFilter):
                payload = {"type": "regex", "regex": event_filter.regex_str}
            elif isinstance(event_filter, PermissionTypeFilter):
                payload = {
                    "type": "permission",
                    "permission_type": event_filter.permission_type.value,
                }
            elif isinstance(event_filter, PlatformAdapterTypeFilter):
                payload = {
                    "type": "platform_adapter",
                    "platform_type": (
                        event_filter.platform_type.value
                        if event_filter.platform_type is not None
                        else None
                    ),
                }
            elif isinstance(event_filter, EventMessageTypeFilter):
                payload = {
                    "type": "event_message_type",
                    "message_type": event_filter.event_message_type.value,
                }
            if payload is not None:
                filters.append(payload)
        entries.append(
            {
                "event_type": (handler.event_type.name if handler.event_type else None),
                "handler_full_name": handler.handler_full_name,
                "handler_name": handler.handler_name,
                "handler_module_path": handler.handler_module_path,
                "desc": handler.desc,
                "enabled": handler.enabled,
                "priority": handler.extras_configs.get("priority", 0),
                # Core resolves plugin ownership lazily via star_map at query
                # time; precompute it so the facade can answer synchronously.
                "plugin_name": plugin.name if plugin else None,
                "plugin_activated": plugin.activated if plugin else True,
                "plugin_reserved": plugin.reserved if plugin else False,
                "filters": filters,
            }
        )
    return entries


async def build_legacy_snapshot(context: Context) -> dict[str, Any]:
    """Capture the host state legacy plugins read synchronously.

    Args:
        context: Core star context owning the provider/persona/config managers.

    Returns:
        JSON-safe snapshot dict shipped in the legacy plugin handshake.
    """
    from astrbot.core import sp
    from astrbot.core.persona_mgr import DEFAULT_PERSONALITY
    from astrbot.core.provider.entities import ProviderType
    from astrbot.core.provider.register import llm_tools

    from .services.kb import serialize_kb

    pm = context.provider_manager
    persona_mgr = context.persona_manager
    acm = context.astrbot_config_mgr

    providers = {
        "chat": _provider_entries(pm.provider_insts),
        "speech_to_text": _provider_entries(pm.stt_provider_insts),
        "text_to_speech": _provider_entries(pm.tts_provider_insts),
        "embedding": _provider_entries(pm.embedding_provider_insts),
        "rerank": _provider_entries(pm.rerank_provider_insts),
    }

    # Defaults resolved against the default config profile, mirroring
    # ProviderManager._resolve_using_provider with no session preference.
    defaults: dict[str, str | None] = {}
    for key, provider_type in (
        ("chat", ProviderType.CHAT_COMPLETION),
        ("speech_to_text", ProviderType.SPEECH_TO_TEXT),
        ("text_to_speech", ProviderType.TEXT_TO_SPEECH),
    ):
        provider = pm._resolve_using_provider(provider_type, None, None)
        defaults[key] = str(provider.meta().id) if provider is not None else None
    defaults["embedding"] = (
        str(pm.embedding_provider_insts[0].meta().id)
        if pm.embedding_provider_insts
        else None
    )

    umo_prefs: dict[str, dict[str, Any]] = {}
    session_personas: dict[str, str] = {}
    for pref in await sp.range_get_async(scope="umo"):
        value = pref.value.get("val") if isinstance(pref.value, dict) else None
        if pref.key.startswith("provider_perf_"):
            if value is not None:
                umo_prefs.setdefault(pref.scope_id, {})[
                    pref.key.removeprefix("provider_perf_")
                ] = value
        elif pref.key == "session_service_config":
            persona_id = (value or {}).get("persona_id") if value else None
            if persona_id:
                session_personas[pref.scope_id] = str(persona_id)

    profiles = {
        str(conf_id): _redact(copy.deepcopy(dict(conf)))
        for conf_id, conf in acm.confs.items()
        if conf_id != "default"
    }

    config_list = [
        {"id": str(info.get("id")), "name": info.get("name"), "path": info.get("path")}
        for info in acm.get_conf_list()
    ]

    return {
        "providers": providers,
        "providers_config": _redact(copy.deepcopy(pm.providers_config)),
        "provider_sources_config": _redact(copy.deepcopy(pm.provider_sources_config)),
        "tools": _tool_entries(llm_tools.func_list),
        "provider_defaults": defaults,
        "provider_umo_prefs": umo_prefs,
        "personas_v3": copy.deepcopy(persona_mgr.personas_v3),
        "personas": [
            {"persona_id": p.persona_id, "system_prompt": p.system_prompt}
            for p in persona_mgr.personas
        ],
        "default_personality": copy.deepcopy(dict(DEFAULT_PERSONALITY)),
        "default_persona_id": persona_mgr.default_persona,
        "umo_session_personas": session_personas,
        "config": _redact(copy.deepcopy(dict(acm.confs["default"]))),
        "config_profiles": profiles,
        "config_routes": dict(acm.ucr.umop_to_conf_id),
        "config_list": config_list,
        "session_conversations": dict(
            context.conversation_manager.session_conversations
        ),
        "persona_folder_tree": await persona_mgr.get_folder_tree(),
        "kbs": [serialize_kb(kb) for kb in await context.kb_manager.list_kbs()],
        "platforms": _platform_entries(context.platform_manager.platform_insts),
        "subagent_handoffs": handoff_entries(context.subagent_orchestrator),
        "handlers": _handler_entries(),
        "sp": [
            {
                "scope": pref.scope,
                "scope_id": pref.scope_id,
                "key": pref.key,
                "value": pref.value.get("val")
                if isinstance(pref.value, dict)
                else pref.value,
            }
            for pref in await sp.range_get_async(scope=None)
        ],
    }
