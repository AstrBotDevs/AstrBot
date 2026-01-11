from __future__ import annotations

import asyncio
import hashlib
import time
from copy import deepcopy
from typing import Any, cast

from quart import request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot import logger
from astrbot.api import sp
from astrbot.api.event import AstrMessageEvent
from astrbot.builtin_stars.astrbot.process_llm_request import ProcessLLMRequest
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.po import Conversation, ConversationV2
from astrbot.core.pipeline.prompt_preview_dry_run import (
    DryRunAstrMessageEvent,
    build_prompt_preview_render_result,
    compute_effective_plugins_name_for_preview,
    dry_run_execute_on_llm_request,
)
from astrbot.core.pipeline.snapshot import build_pipeline_snapshot
from astrbot.core.provider.entities import ProviderRequest

from .route import Response, Route, RouteContext


# preview event is implemented in `astrbot.core.pipeline.prompt_preview_dry_run`


class PipelineRoute(Route):
    _static_cache: dict[tuple[str, str, bool], tuple[dict[str, Any], float]] = {}
    _render_cache: dict[tuple[str, str, str, bool], tuple[dict[str, Any], float]] = {}
    _inflight: dict[tuple[str, tuple[Any, ...]], asyncio.Future] = {}
    _cache_lock: asyncio.Lock = asyncio.Lock()
    STATIC_CACHE_TTL: float = 15.0
    RENDER_CACHE_TTL: float = 10.0

    def __init__(self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle | None = None) -> None:
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.routes = {
            "/pipeline/snapshot": ("GET", self.get_snapshot),
        }
        self.register_routes()

    async def _infer_render_umo(self) -> str | None:
        """
        Pick a real UMO for rendering when the request doesn't provide one.

        Motivation: persona/session rules are keyed by UMO; using the default
        "preview:preview:preview" often results in empty system_prompt.
        """
        if not self.core_lifecycle:
            return None
        try:
            async with self.core_lifecycle.db.get_db() as session:
                session = cast(AsyncSession, session)
                result = await session.execute(
                    select(ConversationV2.user_id).order_by(col(ConversationV2.updated_at).desc()).limit(1),
                )
                row = result.first()
                if not row:
                    return None
                umo = str(row[0] or "").strip()
                return umo or None
        except Exception:
            return None

    async def _render_final_prompt_preview(
        self,
        *,
        umo: str,
        prompt: str,
        debug: bool = False,
        persona_prompt_influencers: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self.core_lifecycle:
            return {
                "prompt": "",
                "system_prompt": "",
                "contexts": {
                    "present": False,
                    "source": "unknown",
                    "count": 0,
                    "note": "Render is disabled because PipelineRoute was initialized without core_lifecycle.",
                },
                "_debug": {
                    "render_disabled_no_core_lifecycle": True,
                }
                if debug
                else None,
            }

        ctx = self.core_lifecycle.star_context
        conv_mgr = self.core_lifecycle.conversation_manager

        conv: Conversation | None = None
        try:
            cid = await conv_mgr.get_curr_conversation_id(umo)
            if cid:
                conv = await conv_mgr.get_conversation(umo, cid)
        except Exception:
            conv = None

        # If there is no conversation record, still render using a minimal conversation object
        # so persona injection can run (ProcessLLMRequest._ensure_persona checks req.conversation).
        if not conv:
            platform_id = (umo.split(":", 1)[0] if ":" in umo else "") or "unknown"
            conv = Conversation(platform_id=platform_id, user_id=umo, cid="preview", persona_id="")

        extra_debug: dict[str, Any] | None = None
        if debug:
            extra_debug = {"umo": umo, "conversation_persona_id": getattr(conv, "persona_id", "") or ""}

        req = ProviderRequest(prompt=prompt, system_prompt="", conversation=conv)

        # Determine effective plugins allowlist for this UMO, to keep preview aligned with snapshot scope.
        cfg = ctx.get_config(umo=umo) or {}
        plugin_set_raw = cfg.get("plugin_set", ["*"])
        plugin_set = None
        if isinstance(plugin_set_raw, list):
            plugin_set = [str(x) for x in plugin_set_raw if str(x).strip()]
        if plugin_set == ["*"]:
            plugin_set = None

        plugins_name = compute_effective_plugins_name_for_preview(umo=umo, plugin_set=plugin_set)

        provider_settings = cfg.get("provider_settings") or {}

        persona_prompt_text: str | None = None
        persona_id_effective: str | None = None
        persona_id_source: str = "unknown"

        async def _resolve_persona_id_for_preview() -> tuple[str | None, str]:
            try:
                sess_cfg = await sp.get_async(
                    scope="umo",
                    scope_id=umo,
                    key="session_service_config",
                    default={},
                )
                if isinstance(sess_cfg, dict):
                    pid = str(sess_cfg.get("persona_id") or "").strip()
                    if pid:
                        return pid, "session_rule"
            except Exception:
                pass

            try:
                pid_conv = str(getattr(conv, "persona_id", "") or "").strip()
                if pid_conv:
                    return pid_conv, "conversation"
            except Exception:
                pass

            pid_cfg = str(provider_settings.get("default_personality") or "").strip()
            if pid_cfg:
                return pid_cfg, "config_default_personality"

            return None, "unset"

        try:
            persona_id_effective, persona_id_source = await _resolve_persona_id_for_preview()

            if (not persona_id_effective or persona_id_effective == "default") and persona_id_effective != "[%None]":
                default_persona = getattr(ctx.persona_manager, "selected_default_persona_v3", None)
                if not default_persona:
                    try:
                        default_persona = await ctx.persona_manager.get_default_persona_v3(umo)
                    except Exception:
                        default_persona = None
                if isinstance(default_persona, dict) and default_persona.get("name"):
                    persona_id_effective = str(default_persona.get("name") or "").strip() or persona_id_effective
                    persona_id_source = "persona_manager_default"
        except Exception as e:
            if debug:
                logger.error("prompt preview: failed to resolve persona_id: %s", e, exc_info=True)

        # IMPORTANT:
        # We must use the *raw* persona system_prompt as the anchor text for attribution.
        # `selected_default_persona_v3` can be modified by plugins like meme_manager; if we use that modified
        # prompt here, the whole injected block will be mis-attributed as "persona:*" and cannot be split.
        raw_persona_prompt_text: str | None = None
        if persona_id_effective and persona_id_effective != "[%None]":
            try:
                p = next(
                    (
                        x
                        for x in (getattr(ctx.persona_manager, "personas", None) or [])
                        if str(getattr(x, "persona_id", "") or "") == str(persona_id_effective)
                    ),
                    None,
                )
                if p is not None:
                    raw_persona_prompt_text = str(getattr(p, "system_prompt", "") or "") or None
                else:
                    p2 = await ctx.persona_manager.get_persona(str(persona_id_effective))
                    raw_persona_prompt_text = str(getattr(p2, "system_prompt", "") or "") or None
            except Exception as e:
                raw_persona_prompt_text = None
                if debug:
                    logger.error("prompt preview: failed to load raw persona prompt: %s", e, exc_info=True)
        try:
            if raw_persona_prompt_text is not None:
                persona_prompt_text = raw_persona_prompt_text
            else:
                tmp_req = ProviderRequest(prompt=prompt, system_prompt="", conversation=conv)
                proc = ProcessLLMRequest(ctx)
                await proc._ensure_persona(tmp_req, provider_settings, umo)
                persona_prompt_text = str(tmp_req.system_prompt or "") or None
        except Exception as e:
            if debug:
                logger.error("prompt preview: failed to resolve persona prompt text: %s", e, exc_info=True)

        if debug and extra_debug is not None:
            extra_debug["persona_prompt_text_len"] = len(str(persona_prompt_text or ""))
            extra_debug["persona_prompt_text_is_raw"] = bool(raw_persona_prompt_text)

        persona_sources: list[dict[str, Any]] = []
        if persona_prompt_text:
            primary_plugin = f"persona:{(persona_id_effective or 'unknown')}"
            primary_handler = f"selected({persona_id_source})"
            persona_sources.append(
                {
                    "plugin": primary_plugin,
                    "handler": primary_handler,
                    "priority": 0,
                    "field": "persona_prompt",
                    "mutation": "selected",
                    "status": "static",
                }
            )

            seen_influencers: set[tuple[str, str, int, str, str]] = set()
            for item in persona_prompt_influencers or []:
                if not isinstance(item, dict):
                    continue
                plugin_name = str(item.get("plugin") or "").strip()
                handler_name = str(item.get("handler") or "").strip()
                if not plugin_name or not handler_name:
                    continue
                if plugin_name.startswith("persona:"):
                    continue
                mutation = str(item.get("mutation") or "unknown").strip() or "unknown"
                priority = int(item.get("priority") or 0)
                key = (plugin_name, handler_name, priority, "persona_prompt", mutation)
                if key in seen_influencers:
                    continue
                seen_influencers.add(key)
                persona_sources.append(
                    {
                        "plugin": plugin_name,
                        "handler": handler_name,
                        "priority": priority,
                        "field": "persona_prompt",
                        "mutation": mutation,
                        "status": str(item.get("status") or "inferred"),
                    }
                )

        # Use dry-run event to block side effects and record stop_event impacts.
        # Note: persona/system injection is implemented by AstrBot's built-in OnLLMRequestEvent handler,
        # so we DO NOT call ProcessLLMRequest here to avoid duplicate injection.
        dry_event = DryRunAstrMessageEvent(umo=umo, message_str=str(req.prompt or ""), plugins_name=plugins_name)

        render_handlers, render_warnings, rendered_system_prompt_segments = await dry_run_execute_on_llm_request(
            event=dry_event,
            req=req,
            persona_prompt_text=persona_prompt_text,
            persona_prompt_sources=cast(list, persona_sources) if persona_sources else None,
            debug=debug,
        )

        if debug and extra_debug is not None:
            extra_debug["persona_id_effective"] = persona_id_effective or ""
            extra_debug["persona_id_source"] = persona_id_source
            extra_debug["persona_prompt_influencers_len"] = len(list(persona_prompt_influencers or []))
            extra_debug["persona_sources_len"] = len(persona_sources)

        contexts_source = "conversation_history" if req.contexts else "unknown"
        contexts_note = (
            "Rendered via dry-run OnLLMRequestEvent hooks (includes AstrBot built-in persona/system injection); "
            "side effects (send/request_llm/etc.) are blocked and reported."
        )

        result = build_prompt_preview_render_result(
            umo=umo,
            req=req,
            preview_prompt=prompt,
            contexts_source=contexts_source,
            contexts_note=contexts_note,
            render_handlers=render_handlers,
            render_warnings=render_warnings,
            rendered_system_prompt_segments=rendered_system_prompt_segments,
        )

        if debug and extra_debug is not None:
            result["_debug"] = extra_debug
        return result

    async def get_snapshot(self):
        umo = request.args.get("umo")
        force_refresh = request.args.get("force_refresh", "false").lower() == "true"
        debug = str(request.args.get("debug", "")).strip().lower() in {"1", "true", "yes", "on"}

        render_raw = request.args.get("render")
        if render_raw is None:
            render = True
        else:
            render = str(render_raw).strip().lower() in {"1", "true", "yes", "on"}

        preview_prompt_raw = request.args.get("preview_prompt")
        preview_prompt_raw_str = str(preview_prompt_raw or "").strip()
        preview_prompt_provided = bool(preview_prompt_raw_str)
        preview_prompt = preview_prompt_raw_str if preview_prompt_provided else "（预览）用户输入：<未提供>"

        cls = self.__class__
        scope_mode = "session" if umo else "global"
        static_key = (scope_mode, str(umo or ""), bool(debug))

        base_snapshot: dict[str, Any] | None = None
        if not force_refresh:
            now = time.monotonic()
            async with cls._cache_lock:
                entry = cls._static_cache.get(static_key)
                if entry is not None:
                    cached_snapshot, ts = entry
                    if now - ts <= cls.STATIC_CACHE_TTL:
                        base_snapshot = cached_snapshot
                    else:
                        cls._static_cache.pop(static_key, None)

        if base_snapshot is None:
            base_snapshot = build_pipeline_snapshot(umo=umo, force_refresh=force_refresh, debug=debug)
            async with cls._cache_lock:
                now = time.monotonic()
                for k, (_, ts) in list(cls._static_cache.items()):
                    if now - ts > cls.STATIC_CACHE_TTL:
                        cls._static_cache.pop(k, None)
                cls._static_cache[static_key] = (deepcopy(base_snapshot), now)

        snapshot = deepcopy(base_snapshot)

        if render:
            snapshot.setdefault("_debug", {})
            snapshot["_debug"]["render_requested"] = True
            snapshot["_debug"]["render_preview_prompt_provided"] = preview_prompt_provided
            snapshot["_debug"]["render_preview_prompt_effective_is_default"] = not preview_prompt_provided
            snapshot["_debug"]["render_preview_prompt_len"] = len(preview_prompt)
            snapshot["_debug"]["render_has_llm_prompt_preview"] = bool(snapshot.get("llm_prompt_preview"))

        if render and snapshot.get("llm_prompt_preview"):
            render_umo_source = "request" if umo else "fallback"
            render_umo = str(umo or "")
            if not render_umo:
                inferred = await self._infer_render_umo()
                if inferred:
                    render_umo = inferred
                    render_umo_source = "db_latest_conversation"
                else:
                    render_umo = "preview:preview:preview"
                    render_umo_source = "default_preview"

            snapshot.setdefault("_debug", {})
            snapshot["_debug"]["render_branch_entered"] = True
            snapshot["_debug"]["render_umo"] = render_umo
            snapshot["_debug"]["render_umo_source"] = render_umo_source
            snapshot["_debug"]["render_umo_is_default"] = not bool(umo)
            snapshot["_debug"]["render_has_core_lifecycle"] = bool(self.core_lifecycle)
            try:
                persona_influencers: list[dict[str, Any]] = []
                try:
                    injected_by = (snapshot.get("llm_prompt_preview") or {}).get("injected_by") or []
                    seen: set[tuple[str, str, str, int]] = set()
                    for item in injected_by:
                        if not isinstance(item, dict):
                            continue
                        if item.get("field") != "persona_prompt":
                            continue
                        plugin_name = str(
                            (
                                (item.get("plugin") or {})
                                if isinstance(item.get("plugin"), dict)
                                else {}
                            ).get("name")
                            or ""
                        ).strip()
                        handler_full_name = str(
                            (
                                (item.get("handler") or {})
                                if isinstance(item.get("handler"), dict)
                                else {}
                            ).get("handler_full_name")
                            or ""
                        ).strip()
                        mutation = str(item.get("mutation") or "unknown").strip() or "unknown"
                        priority = int(item.get("priority") or 0)
                        key = (plugin_name, handler_full_name, mutation, priority)
                        if key in seen:
                            continue
                        seen.add(key)
                        persona_influencers.append(
                            {
                                "plugin": plugin_name,
                                "handler": handler_full_name,
                                "priority": priority,
                                "mutation": mutation,
                                "status": "injected_by",
                            }
                        )
                except Exception:
                    persona_influencers = []

                snapshot.setdefault("_debug", {})
                snapshot["_debug"]["persona_prompt_influencers_len"] = len(persona_influencers)

                preview_hash = hashlib.sha256(preview_prompt.encode("utf-8")).hexdigest()
                render_cache_key = (str(snapshot.get("snapshot_id") or ""), str(render_umo or ""), preview_hash, bool(debug))

                rendered: dict[str, Any] | None = None
                if not force_refresh:
                    now = time.monotonic()
                    async with cls._cache_lock:
                        entry = cls._render_cache.get(render_cache_key)
                        if entry is not None:
                            cached_rendered, ts = entry
                            if now - ts <= cls.RENDER_CACHE_TTL:
                                rendered = deepcopy(cached_rendered)
                            else:
                                cls._render_cache.pop(render_cache_key, None)

                if rendered is None:
                    inflight_key = ("render", render_cache_key)
                    fut: asyncio.Future | None = None
                    owner = False

                    async with cls._cache_lock:
                        if not force_refresh and rendered is None:
                            entry = cls._render_cache.get(render_cache_key)
                            if entry is not None:
                                cached_rendered, ts = entry
                                if time.monotonic() - ts <= cls.RENDER_CACHE_TTL:
                                    rendered = deepcopy(cached_rendered)

                        if rendered is None:
                            fut = cls._inflight.get(inflight_key)
                            if fut is None:
                                fut = asyncio.get_running_loop().create_future()
                                cls._inflight[inflight_key] = fut
                                owner = True

                    if rendered is None and fut is not None and not owner:
                        rendered = cast(dict[str, Any], await fut)

                    if rendered is None and owner:
                        try:
                            computed = await self._render_final_prompt_preview(
                                umo=render_umo,
                                prompt=preview_prompt,
                                debug=debug,
                                persona_prompt_influencers=persona_influencers,
                            )
                            rendered = computed
                            async with cls._cache_lock:
                                now = time.monotonic()
                                for k, (_, ts) in list(cls._render_cache.items()):
                                    if now - ts > cls.RENDER_CACHE_TTL:
                                        cls._render_cache.pop(k, None)
                                cls._render_cache[render_cache_key] = (deepcopy(computed), now)
                                inflight_fut = cls._inflight.pop(inflight_key, None)
                                if inflight_fut is not None and not inflight_fut.done():
                                    inflight_fut.set_result(deepcopy(computed))
                        except Exception as e:
                            async with cls._cache_lock:
                                inflight_fut = cls._inflight.pop(inflight_key, None)
                                if inflight_fut is not None and not inflight_fut.done():
                                    inflight_fut.set_exception(e)
                            raise

                if rendered is None:
                    rendered = {
                        "prompt": "",
                        "system_prompt": "",
                    }

                rendered_prompt = rendered.get("prompt") or ""
                rendered_system_prompt = rendered.get("system_prompt") or ""

                snapshot["_debug"]["rendered_prompt_len"] = len(rendered_prompt)
                snapshot["_debug"]["rendered_system_prompt_len"] = len(rendered_system_prompt)

                snapshot["_debug"]["rendered_has_segments_field"] = "rendered_system_prompt_segments" in rendered
                segs = rendered.get("rendered_system_prompt_segments")
                snapshot["_debug"]["rendered_segments_type"] = type(segs).__name__
                if isinstance(segs, list):
                    snapshot["_debug"]["rendered_segments_len"] = len(segs)
                else:
                    snapshot["_debug"]["rendered_segments_len"] = None

                if debug and isinstance(rendered.get("_debug"), dict):
                    snapshot["_debug"]["render_persona"] = rendered["_debug"]

                llm_preview = snapshot["llm_prompt_preview"]
                llm_preview["prompt"] = rendered_prompt
                llm_preview["system_prompt"] = rendered_system_prompt

                if isinstance(rendered.get("contexts"), dict):
                    llm_preview["contexts"] = rendered["contexts"]

                inserted_fields: list[str] = []
                # Optional newer fields (backward compatible)
                for k in (
                    "rendered_prompt",
                    "rendered_system_prompt",
                    "rendered_system_prompt_segments",
                    "rendered_extra_user_content_segments",
                    "render_warnings",
                    "render_executed_handlers",
                ):
                    if k in rendered:
                        llm_preview[k] = rendered[k]
                        inserted_fields.append(k)
                snapshot["_debug"]["render_inserted_fields"] = inserted_fields
            except Exception as e:
                snapshot.setdefault("_debug", {})
                snapshot["_debug"]["render_error"] = f"{e.__class__.__name__}: {e}"
                logger.error("pipeline snapshot render failed: %s", snapshot["_debug"]["render_error"], exc_info=True)

        return Response().ok(snapshot).__dict__