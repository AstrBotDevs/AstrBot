from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

from astrbot.core import logger
from astrbot.core.pipeline.snapshot.conflicts import (
    build_llm_prompt_preview,
    detect_command_conflicts,
    detect_duplicate_send,
    detect_priority_ties,
    detect_prompt_overwrite_conflicts,
    detect_stop_interception,
    detect_tool_name_conflicts,
)
from astrbot.core.pipeline.snapshot.filters import summarize_filters
from astrbot.core.pipeline.snapshot.risks import (
    scan_static_mutations_from_callable,
    scan_static_name_calls_from_callable,
    scan_static_risks,
    scan_static_self_calls_from_callable,
)
from astrbot.core.pipeline.snapshot.stages import STAGES_ORDER, build_stage_snapshot, stage_for_event_type
from astrbot.core.pipeline.snapshot.utils import sha256_hex, stable_id, utc_now_iso
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star import StarMetadata, star_registry
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata, star_handlers_registry


@dataclass(frozen=True)
class SnapshotScope:
    mode: Literal["global", "session"]
    umo: str | None = None


def _plugin_ref(meta: StarMetadata | None, fallback_name: str) -> dict[str, Any]:
    if meta and meta.name:
        return {
            "name": meta.name,
            "display_name": meta.display_name,
            "reserved": bool(meta.reserved),
            "activated": bool(meta.activated),
            "version": meta.version,
            "repo": meta.repo,
        }
    return {
        "name": fallback_name,
        "display_name": None,
        "reserved": True,
        "activated": True,
        "version": None,
        "repo": None,
    }


def _handler_ref(handler: StarHandlerMetadata) -> dict[str, Any]:
    return {
        "handler_full_name": handler.handler_full_name,
        "handler_name": handler.handler_name,
        "handler_module_path": handler.handler_module_path,
    }


def _priority(handler: StarHandlerMetadata) -> int:
    p = handler.extras_configs.get("priority", 0)
    try:
        return int(p)
    except Exception:
        return 0


def _collect_active_plugins(scope: SnapshotScope) -> list[StarMetadata]:
    active: list[StarMetadata] = []
    for meta in star_registry:
        if not meta.activated:
            continue

        if scope.mode == "session" and scope.umo:
            if meta.reserved:
                active.append(meta)
                continue
            if meta.name and SessionPluginManager.is_plugin_enabled_for_session(scope.umo, meta.name):
                active.append(meta)
            continue

        active.append(meta)
    return active


def _iter_handlers_in_scope(active_plugins: list[StarMetadata]) -> list[StarHandlerMetadata]:
    active_modules = {p.module_path for p in active_plugins if p.module_path}
    handlers: list[StarHandlerMetadata] = []
    for h in star_handlers_registry:
        if h.handler_module_path in active_modules:
            handlers.append(h)
    return handlers


def _build_participant(
    *,
    stage_id: str,
    handler: StarHandlerMetadata,
    plugin_meta: StarMetadata | None,
    cmd: str | None,
    trigger: dict[str, Any] | None,
    filters_summary: str | None,
    permission: str | None,
    risks: list[dict[str, Any]],
    effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    participant_id = stable_id(stage_id, handler.event_type.name, handler.handler_full_name)

    meta: dict[str, Any] = {
        "event_type": handler.event_type.name,
        "priority": _priority(handler),
        "enabled": bool(handler.enabled),
        "trigger": trigger,
        "description": handler.desc or "",
    }
    if permission:
        meta["permission"] = permission
    if cmd is not None:
        meta["cmd"] = cmd
    if filters_summary is not None:
        meta["filters_summary"] = filters_summary

    participant: dict[str, Any] = {
        "id": participant_id,
        "plugin": _plugin_ref(plugin_meta, handler.handler_module_path),
        "handler": _handler_ref(handler),
        "meta": meta,
        "risks": risks,
        "_stage": stage_id,  # internal: for conflict analyzers
    }
    if effects:
        participant["effects"] = effects
    return participant


def _build_command_descriptors(
    handlers: list[StarHandlerMetadata],
    module_to_plugin: dict[str, StarMetadata],
) -> list[dict[str, Any]]:
    """
    生成命令冲突检测所需的最小描述符（仅 AdapterMessageEvent）。
    注意：这里只检测 activated scope 内 handler，enabled 必须为 True 才参与冲突分组。
    """
    descriptors: list[dict[str, Any]] = []
    for h in handlers:
        if h.event_type != EventType.AdapterMessageEvent:
            continue

        plugin_meta = module_to_plugin.get(h.handler_module_path)
        cmd, _trigger, _filters_summary, _permission = summarize_filters(h)
        if not cmd:
            continue

        # alias 仅对 CommandFilter/CommandGroupFilter 提取，summarize_filters 已把 alias 放在 trigger.extra 里
        aliases: list[str] = []
        if isinstance(_trigger, dict):
            extra = _trigger.get("extra") or {}
            if isinstance(extra, dict):
                aliases = [str(x) for x in (extra.get("aliases") or []) if str(x).strip()]

        descriptors.append(
            {
                "plugin": _plugin_ref(plugin_meta, h.handler_module_path),
                "handler": _handler_ref(h),
                "stage": "WakingCheckStage",
                "event_type": EventType.AdapterMessageEvent.name,
                "priority": _priority(h),
                "enabled": bool(h.enabled),
                "cmd": cmd,
                "aliases": aliases,
            }
        )
    return descriptors


def _scan_persona_prompt_modifiers(
    active_plugins: list[StarMetadata],
    *,
    debug: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    通过静态 AST 扫描插件的 __init__/initialize，捕获对 persona.prompt 的修改来源。
    说明：
    - 仅扫描插件覆写的方法（避免扫描基类 Star 的默认实现）
    - 不抛异常；源码不可得/解析失败时直接忽略（仅用于补全 injected_by 链路）
    """
    injected_by: list[dict[str, Any]] = []
    scan_debug: list[dict[str, Any]] = []

    for meta in active_plugins:
        if not meta.activated:
            continue
        cls = meta.star_cls_type
        module_path = meta.module_path or (getattr(cls, "__module__", None) if cls else None)
        if not cls or not module_path:
            continue

        cls_dict = getattr(cls, "__dict__", {}) or {}
        for method_name in ("__init__", "initialize"):
            if method_name not in cls_dict:
                continue
            fn = getattr(cls, method_name, None)
            if not callable(fn):
                continue

            # Scan the entry method itself
            mutations, reason = scan_static_mutations_from_callable(
                fn,
                debug=debug,
                label=f"{meta.name or module_path}:{method_name}",
                module_path=module_path,
            )

            scan_debug.append(
                {
                    "plugin": meta.name or "<unknown>",
                    "module": module_path,
                    "method": method_name,
                    "mutations": mutations,
                    "reason": reason,
                }
            )

            if debug:
                logger.info(
                    "pipeline snapshot debug: persona prompt modifier scan; plugin=%s module=%s method=%s mutations=%s reason=%s",
                    meta.name or "<unknown>",
                    module_path,
                    method_name,
                    mutations,
                    reason,
                )

            def _record_injected_by(*, target_method: str, persona_mutation: str) -> None:
                cls_name = (
                    getattr(cls, "__qualname__", None)
                    or getattr(cls, "__name__", None)
                    or "Star"
                )
                safe_module_path = str(module_path or "")
                handler_full_name = f"{getattr(cls, '__module__', safe_module_path)}.{cls_name}.{target_method}"
                injected_by.append(
                    {
                        "plugin": _plugin_ref(meta, safe_module_path),
                        "handler": {
                            "handler_full_name": handler_full_name,
                            "handler_name": target_method,
                            "handler_module_path": safe_module_path,
                        },
                        "priority": 0,
                        "mutation": "append" if persona_mutation == "append" else "overwrite",
                        "field": "persona_prompt",
                        "source_type": "persona",
                    }
                )

            m = mutations.get("persona_prompt")
            if m in {"append", "overwrite"}:
                _record_injected_by(target_method=method_name, persona_mutation=m)

            # Recursively scan call graph from __init__/initialize:
            # - self.xxx() methods (within the same class)
            # - foo() name calls resolved to functions defined in the same module as the plugin class
            #
            # Depth is limited to avoid infinite recursion / heavy scans.
            max_depth = 3

            mod = getattr(cls, "__module__", None)
            if isinstance(mod, str) and mod:
                try:
                    module_obj = __import__(mod, fromlist=["*"])
                except Exception:
                    module_obj = None
            else:
                module_obj = None

            cls_name = (
                getattr(cls, "__qualname__", None)
                or getattr(cls, "__name__", None)
                or "Star"
            )
            safe_module_path = str(module_path or "")
            base_module_for_handler = getattr(cls, "__module__", safe_module_path)

            recorded: set[tuple[str, str, str]] = set()

            def _record_injected_by_callable(
                *,
                handler_full_name: str,
                handler_name: str,
                persona_mutation: str,
            ) -> None:
                key = (
                    (meta.name or "<unknown>"),
                    handler_full_name,
                    "append" if persona_mutation == "append" else "overwrite",
                )
                if key in recorded:
                    return
                recorded.add(key)
                injected_by.append(
                    {
                        "plugin": _plugin_ref(meta, safe_module_path),
                        "handler": {
                            "handler_full_name": handler_full_name,
                            "handler_name": handler_name,
                            "handler_module_path": safe_module_path,
                        },
                        "priority": 0,
                        "mutation": "append" if persona_mutation == "append" else "overwrite",
                        "field": "persona_prompt",
                        "source_type": "persona",
                    }
                )

            def _scan_callable(
                *,
                kind: Literal["method", "module_fn"],
                name: str,
                target: Any,
                depth: int,
                chain: str,
            ) -> tuple[set[str], set[str]]:
                called_self: set[str] = set()
                called_names: set[str] = set()

                mutations, reason = scan_static_mutations_from_callable(
                    target,
                    debug=debug,
                    label=f"{meta.name or module_path}:{chain}",
                    module_path=module_path,
                )
                scan_debug.append(
                    {
                        "plugin": meta.name or "<unknown>",
                        "module": module_path,
                        "method": chain,
                        "mutations": mutations,
                        "reason": reason,
                    }
                )

                m = mutations.get("persona_prompt")
                if m in {"append", "overwrite"}:
                    if kind == "method":
                        handler_full_name = f"{base_module_for_handler}.{cls_name}.{name}"
                        _record_injected_by_callable(
                            handler_full_name=handler_full_name,
                            handler_name=name,
                            persona_mutation=m,
                        )
                    else:
                        handler_full_name = f"{base_module_for_handler}.{name}"
                        _record_injected_by_callable(
                            handler_full_name=handler_full_name,
                            handler_name=name,
                            persona_mutation=m,
                        )

                if depth >= max_depth:
                    return set(), set()

                # Collect next calls
                if kind == "method":
                    called_self, calls_reason = scan_static_self_calls_from_callable(
                        target,
                        debug=debug,
                        label=f"{meta.name or module_path}:{chain}",
                        module_path=module_path,
                    )
                    if calls_reason:
                        scan_debug.append(
                            {
                                "plugin": meta.name or "<unknown>",
                                "module": module_path,
                                "method": f"{chain}#self_calls",
                                "mutations": {},
                                "reason": calls_reason,
                            }
                        )

                called_names, name_calls_reason = scan_static_name_calls_from_callable(
                    target,
                    debug=debug,
                    label=f"{meta.name or module_path}:{chain}",
                    module_path=module_path,
                )
                if name_calls_reason:
                    scan_debug.append(
                        {
                            "plugin": meta.name or "<unknown>",
                            "module": module_path,
                            "method": f"{chain}#name_calls",
                            "mutations": {},
                            "reason": name_calls_reason,
                        }
                    )

                return called_self, called_names

            visited: set[tuple[str, str]] = {("method", method_name)}
            queue: list[tuple[str, str, Any, int, str]] = []

            # Seed: calls from the entry method
            entry_self_calls, entry_name_calls = _scan_callable(
                kind="method",
                name=method_name,
                target=fn,
                depth=0,
                chain=method_name,
            )

            for called_name in sorted(entry_self_calls):
                if called_name in cls_dict:
                    called_fn = getattr(cls, called_name, None)
                    if callable(called_fn):
                        queue.append(("method", called_name, called_fn, 1, f"{method_name}->self.{called_name}"))

            if module_obj:
                for called_name in sorted(entry_name_calls):
                    target = getattr(module_obj, called_name, None)
                    if callable(target):
                        queue.append(("module_fn", called_name, target, 1, f"{method_name}->{called_name}()"))

            while queue:
                kind, name, target, depth, chain = queue.pop(0)
                key = (kind, name)
                if key in visited:
                    continue
                visited.add(key)

                called_self, called_names = _scan_callable(
                    kind=cast(Literal["method", "module_fn"], kind),
                    name=name,
                    target=target,
                    depth=depth,
                    chain=chain,
                )

                if kind == "method":
                    for next_name in sorted(called_self):
                        if next_name in cls_dict:
                            next_fn = getattr(cls, next_name, None)
                            if callable(next_fn):
                                queue.append(("method", next_name, next_fn, depth + 1, f"{chain}->self.{next_name}"))

                if module_obj:
                    for next_name in sorted(called_names):
                        next_fn = getattr(module_obj, next_name, None)
                        if callable(next_fn):
                            queue.append(("module_fn", next_name, next_fn, depth + 1, f"{chain}->{next_name}()"))

    return injected_by, scan_debug


def build_pipeline_snapshot(
    *,
    umo: str | None = None,
    force_refresh: bool = False,
    debug: bool = False,
) -> dict[str, Any]:
    # force_refresh：当前后端不做缓存，仅用于与前端协议对齐
    _ = force_refresh

    def _sanitize_effects(raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list) or not raw:
            return []
        allowed_keys = ("target", "op", "confidence", "evidence", "lineno", "col")
        sanitized: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            sanitized.append({k: item.get(k) for k in allowed_keys if k in item})
        return sanitized

    scope = SnapshotScope(mode="session" if umo else "global", umo=umo)
    active_plugins = _collect_active_plugins(scope)
    module_to_plugin = {p.module_path: p for p in active_plugins if p.module_path}

    handlers_in_scope = _iter_handlers_in_scope(active_plugins)

    participants: list[dict[str, Any]] = []
    llm_mutations_by_handler_full_name: dict[str, dict[str, str]] = {}

    persona_prompt_modifiers, persona_prompt_scan_debug = _scan_persona_prompt_modifiers(
        active_plugins, debug=debug
    )
    if debug:
        logger.info(
            "pipeline snapshot debug: persona_prompt_modifiers=%s",
            [
                {
                    "plugin": (x.get("plugin") or {}).get("name"),
                    "handler": (x.get("handler") or {}).get("handler_full_name"),
                    "mutation": x.get("mutation"),
                }
                for x in (persona_prompt_modifiers or [])
                if isinstance(x, dict)
            ],
        )

    for h in handlers_in_scope:
        stage_ids = stage_for_event_type(h.event_type)
        if not stage_ids:
            continue

        plugin_meta = module_to_plugin.get(h.handler_module_path)
        cmd, trigger, filters_summary, permission = summarize_filters(h)

        scan_result = scan_static_risks(h, debug=debug)
        risks = scan_result.risks
        llm_mutations = cast(dict[str, str], scan_result.llm_mutations)
        effects = _sanitize_effects(scan_result.effects)

        llm_mutations_by_handler_full_name[h.handler_full_name] = llm_mutations

        for stage_id in stage_ids:
            participants.append(
                _build_participant(
                    stage_id=stage_id,
                    handler=h,
                    plugin_meta=plugin_meta,
                    cmd=cmd,
                    trigger=trigger,
                    filters_summary=filters_summary,
                    permission=permission,
                    risks=risks,
                    effects=effects,
                )
            )

    # stages
    stages: list[dict[str, Any]] = []
    by_stage: dict[str, list[dict[str, Any]]] = {sid: [] for sid in STAGES_ORDER}
    for p in participants:
        by_stage.setdefault(str(p.get("_stage") or ""), []).append(p)

    for stage_id in STAGES_ORDER:
        stage_participants = by_stage.get(stage_id, [])
        stage_participants = sorted(
            stage_participants,
            key=lambda p: (
                str(p.get("meta", {}).get("event_type") or ""),
                -int(p.get("meta", {}).get("priority") or 0),
                str(p.get("handler", {}).get("handler_full_name") or ""),
            ),
        )
        stages.append(build_stage_snapshot(stage_id, stage_participants))

    # conflicts + llm preview
    conflicts: list[dict[str, Any]] = []
    command_desc = _build_command_descriptors(handlers_in_scope, module_to_plugin)

    llm_preview = build_llm_prompt_preview(
        participants,
        llm_mutations_by_handler_full_name,
        persona_prompt_modifiers,
    )
    if debug:
        injected = (llm_preview or {}).get("injected_by") or []
        counts: dict[str, int] = {}
        for item in injected:
            key = f"{item.get('field')}:{item.get('mutation')}"
            counts[key] = counts.get(key, 0) + 1
        logger.info(
            "pipeline snapshot debug: llm_prompt_preview=%s",
            {
                "present": bool(llm_preview),
                "injected_by_len": len(injected),
                "counts": counts,
            },
        )

    conflicts.extend(detect_command_conflicts(command_desc))
    conflicts.extend(detect_tool_name_conflicts(active_plugins))
    conflicts.extend(detect_priority_ties(participants))
    conflicts.extend(detect_duplicate_send(participants))
    conflicts.extend(detect_prompt_overwrite_conflicts(llm_preview))
    conflicts.extend(detect_stop_interception(participants))

    # stats + snapshot_id
    by_type: dict[str, int] = {}
    for c in conflicts:
        t = c.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    risk_count = sum(len(p.get("risks") or []) for p in participants)

    plugin_refs = [
        _plugin_ref(p, p.module_path or "")
        for p in sorted(active_plugins, key=lambda x: (x.name or "", x.module_path or ""))
    ]

    snapshot_material: list[str] = []
    for p in participants:
        snapshot_material.append(
            "|".join(
                [
                    str(p.get("_stage") or ""),
                    str(p.get("handler", {}).get("handler_full_name") or ""),
                    str(p.get("meta", {}).get("event_type") or ""),
                    str(p.get("meta", {}).get("priority") or 0),
                    "1" if p.get("meta", {}).get("enabled") else "0",
                    str(p.get("meta", {}).get("cmd") or ""),
                    str(p.get("meta", {}).get("filters_summary") or ""),
                ]
            )
        )
    snapshot_id = "sha256:" + sha256_hex("\n".join(sorted(snapshot_material)))

    payload: dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "generated_at": utc_now_iso(),
        "scope": {"mode": scope.mode, "umo": scope.umo},
        "plugins": plugin_refs,
        "stages": stages,
        "conflicts": conflicts,
        "llm_prompt_preview": llm_preview,
        "stats": {
            "pluginCount": len(plugin_refs),
            "handlerCount": len(participants),
            "conflictCount": len(conflicts),
            "riskCount": risk_count,
            "byConflictType": by_type,
        },
    }

    if debug:
        payload["_debug"] = {
            "persona_prompt_scan": persona_prompt_scan_debug,
            "persona_prompt_modifiers_count": len(persona_prompt_modifiers or []),
            "llm_prompt_preview_present": bool(llm_preview),
            "llm_prompt_preview_injected_by_len": len((llm_preview or {}).get("injected_by") or []),
        }

    return payload


__all__ = ["build_pipeline_snapshot"]