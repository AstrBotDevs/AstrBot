import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from astrbot.api import logger, safe_error, star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.provider import Provider, ProviderType

from .reply import reply_i18n, reply_text, send_i18n

MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT = 30.0
MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT = 4
MODEL_LOOKUP_MAX_CONCURRENCY_UPPER_BOUND = 16
MODEL_LIST_CACHE_TTL_KEY = "model_list_cache_ttl_seconds"
MODEL_LOOKUP_MAX_CONCURRENCY_KEY = "model_lookup_max_concurrency"
MODEL_CACHE_MAX_ENTRIES = 512


class _SwitchableProvider(Protocol):
    def meta(self) -> Any: ...


@dataclass(frozen=True)
class _ModelLookupConfig:
    umo: str | None
    cache_ttl_seconds: float
    max_concurrency: int


class _ModelCache:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str | None], tuple[float, list[str]]] = {}

    def get(self, provider_id: str, umo: str | None, ttl: float) -> list[str] | None:
        if ttl <= 0:
            return None
        entry = self._store.get((provider_id, umo))
        if not entry:
            return None
        timestamp, models = entry
        if time.monotonic() - timestamp > ttl:
            self._store.pop((provider_id, umo), None)
            return None
        return models

    def set(
        self,
        provider_id: str,
        umo: str | None,
        models: list[str],
        ttl: float,
    ) -> None:
        if ttl <= 0:
            return
        self._store[(provider_id, umo)] = (time.monotonic(), list(models))
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        if len(self._store) <= MODEL_CACHE_MAX_ENTRIES:
            return
        overflow = len(self._store) - MODEL_CACHE_MAX_ENTRIES
        for key, _ in sorted(self._store.items(), key=lambda item: item[1][0])[
            :overflow
        ]:
            self._store.pop(key, None)

    def invalidate(
        self,
        provider_id: str | None = None,
        *,
        umo: str | None = None,
    ) -> None:
        if provider_id is None:
            self._store.clear()
            return
        if umo is not None:
            self._store.pop((provider_id, umo), None)
            return
        stale_keys = [
            cache_key for cache_key in self._store if cache_key[0] == provider_id
        ]
        for cache_key in stale_keys:
            self._store.pop(cache_key, None)


class ProviderCommands:
    def __init__(self, context: star.PluginContext) -> None:
        self.context = context
        self._model_cache = _ModelCache()
        self._register_provider_change_hook()

    def _register_provider_change_hook(self) -> None:
        self.context.models.on_change(self._on_provider_manager_changed)

    def invalidate_provider_models_cache(
        self,
        provider_id: str | None = None,
        *,
        umo: str | None = None,
    ) -> None:
        self._model_cache.invalidate(provider_id, umo=umo)

    def _on_provider_manager_changed(
        self,
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None,
    ) -> None:
        if provider_type == ProviderType.CHAT_COMPLETION:
            self.invalidate_provider_models_cache(provider_id, umo=umo)

    def _get_provider_settings(self, umo: str | None) -> dict:
        if not umo:
            return {}
        try:
            return self.context.config.get(umo).get("provider_settings", {}) or {}
        except Exception as exc:
            logger.debug("Failed to read provider settings, using defaults: %s", exc)
            return {}

    def _get_model_cache_ttl(self, umo: str | None) -> float:
        raw = self._get_provider_settings(umo).get(
            MODEL_LIST_CACHE_TTL_KEY,
            MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT,
        )
        try:
            return max(float(raw), 0.0)
        except Exception as exc:
            logger.debug("Invalid %s value %r: %s", MODEL_LIST_CACHE_TTL_KEY, raw, exc)
            return MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT

    def _get_model_lookup_concurrency(self, umo: str | None) -> int:
        raw = self._get_provider_settings(umo).get(
            MODEL_LOOKUP_MAX_CONCURRENCY_KEY,
            MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT,
        )
        try:
            value = int(raw)
        except Exception as exc:
            logger.debug(
                "Invalid %s value %r: %s",
                MODEL_LOOKUP_MAX_CONCURRENCY_KEY,
                raw,
                exc,
            )
            value = MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT
        return min(max(value, 1), MODEL_LOOKUP_MAX_CONCURRENCY_UPPER_BOUND)

    def _get_model_lookup_config(self, umo: str | None) -> _ModelLookupConfig:
        return _ModelLookupConfig(
            umo=umo,
            cache_ttl_seconds=self._get_model_cache_ttl(umo),
            max_concurrency=self._get_model_lookup_concurrency(umo),
        )

    def _resolve_model_name(
        self,
        model_name: str,
        models: Sequence[str],
    ) -> str | None:
        requested = model_name.strip()
        if not requested:
            return None

        requested_norm = requested.casefold()
        for candidate in models:
            if candidate == requested or candidate.casefold() == requested_norm:
                return candidate

        for candidate in models:
            cand_norm = candidate.casefold()
            if cand_norm.endswith(f"/{requested_norm}") or cand_norm.endswith(
                f":{requested_norm}"
            ):
                return candidate

        return None

    async def _apply_model(
        self,
        event: AstrMessageEvent,
        provider: Provider,
        model_name: str,
        *,
        umo: str | None = None,
    ) -> str:
        provider.set_model(model_name)
        self.invalidate_provider_models_cache(provider.meta().id, umo=umo)
        return await self.context.i18n.t(
            event,
            "provider.models.switched",
            provider_id=provider.meta().id,
            model=provider.get_model(),
        )

    async def _get_provider_models(
        self,
        provider: Provider,
        *,
        config: _ModelLookupConfig,
        use_cache: bool = True,
    ) -> list[str]:
        provider_id = provider.meta().id
        if use_cache:
            cached = self._model_cache.get(
                provider_id,
                config.umo,
                config.cache_ttl_seconds,
            )
            if cached is not None:
                return cached

        models = list(await provider.get_models())
        if use_cache:
            self._model_cache.set(
                provider_id,
                config.umo,
                models,
                config.cache_ttl_seconds,
            )
        return models

    async def _get_models_or_reply_error(
        self,
        event: AstrMessageEvent,
        provider: Provider,
        config: _ModelLookupConfig,
        *,
        warning_log: str | None = None,
    ) -> list[str] | None:
        try:
            return await self._get_provider_models(provider, config=config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if warning_log is not None:
                logger.warning(warning_log, provider.meta().id, safe_error("", exc))
            await reply_i18n(
                self.context,
                event,
                "provider.models.fetch_failed",
                error=safe_error("", exc),
            )
            return None

    async def _find_provider_for_model(
        self,
        model_name: str,
        *,
        exclude_provider_id: str | None = None,
        config: _ModelLookupConfig,
        use_cache: bool = True,
    ) -> tuple[Provider | None, str | None]:
        all_providers: list[Provider] = []
        for provider in self.context.models.chat():
            if provider.meta().provider_type != ProviderType.CHAT_COMPLETION:
                continue
            if (
                exclude_provider_id is not None
                and provider.meta().id == exclude_provider_id
            ):
                continue
            all_providers.append(provider)
        if not all_providers:
            return None, None

        semaphore = asyncio.Semaphore(config.max_concurrency)

        async def fetch_models(
            provider: Provider,
        ) -> tuple[Provider, list[str] | None, str | None]:
            async with semaphore:
                try:
                    models = await self._get_provider_models(
                        provider,
                        config=config,
                        use_cache=use_cache,
                    )
                    return provider, models, None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    err = safe_error("", exc)
                    logger.debug(
                        "Failed to fetch model list from %s while looking for %s: %s",
                        provider.meta().id,
                        model_name,
                        err,
                    )
                    return provider, None, err

        results = await asyncio.gather(
            *(fetch_models(provider) for provider in all_providers)
        )
        failed_provider_errors: list[tuple[str, str]] = []
        for provider, models, err in results:
            if err is not None:
                failed_provider_errors.append((provider.meta().id, err))
                continue
            if models is None:
                continue

            matched_model_name = self._resolve_model_name(model_name, models)
            if matched_model_name is not None:
                return provider, matched_model_name

        if failed_provider_errors and len(failed_provider_errors) == len(all_providers):
            logger.error(
                "All providers failed while looking up model %s: %s",
                model_name,
                ",".join(provider_id for provider_id, _ in failed_provider_errors),
            )
        return None, None

    def _log_reachability_failure(
        self,
        provider,
        provider_capability_type: ProviderType | None,
        err_code: str,
        err_reason: str,
    ) -> None:
        meta = provider.meta()
        logger.warning(
            "Provider reachability check failed: id=%s type=%s code=%s reason=%s",
            meta.id,
            provider_capability_type.name if provider_capability_type else "unknown",
            err_code,
            err_reason,
        )

    async def _test_provider_capability(self, provider):
        meta = provider.meta()
        provider_capability_type = meta.provider_type

        try:
            await provider.test()
            return True, None, None
        except Exception as exc:
            err_code = "TEST_FAILED"
            err_reason = safe_error("", exc)
            self._log_reachability_failure(
                provider,
                provider_capability_type,
                err_code,
                err_reason,
            )
            return False, err_code, err_reason

    async def _reachability_mark(
        self,
        event: AstrMessageEvent,
        reachable_flag: bool | None,
        error_code: str | None,
    ) -> str:
        if reachable_flag is True:
            return await self.context.i18n.t(event, "provider.list.ok")
        if reachable_flag is False:
            if error_code:
                return await self.context.i18n.t(
                    event,
                    "provider.list.fail_code",
                    error_code=error_code,
                )
            return await self.context.i18n.t(event, "provider.list.fail")
        return ""

    async def _build_provider_display_data(
        self,
        event: AstrMessageEvent,
        providers,
        provider_type: str,
        reachability_check_enabled: bool,
    ) -> list[dict]:
        if not providers:
            return []

        if reachability_check_enabled:
            check_results = await asyncio.gather(
                *[self._test_provider_capability(provider) for provider in providers],
                return_exceptions=True,
            )
        else:
            check_results = [None for _ in providers]

        display_data = []
        for provider, reachable in zip(providers, check_results):
            meta = provider.meta()
            id_ = meta.id
            error_code = None

            if isinstance(reachable, asyncio.CancelledError):
                raise reachable
            if isinstance(reachable, Exception):
                self._log_reachability_failure(
                    provider,
                    None,
                    reachable.__class__.__name__,
                    safe_error("", reachable),
                )
                reachable_flag = False
                error_code = reachable.__class__.__name__
            elif isinstance(reachable, tuple):
                reachable_flag, error_code, _ = reachable
                reachable_flag = (
                    bool(reachable_flag) if reachable_flag is not None else None
                )
            else:
                reachable_flag = reachable if isinstance(reachable, bool) else None

            if provider_type == "llm":
                info = f"{id_} ({meta.model})"
            else:
                info = f"{id_}"

            display_data.append(
                {
                    "info": info,
                    "mark": await self._reachability_mark(
                        event,
                        reachable_flag,
                        error_code,
                    ),
                    "provider": provider,
                },
            )

        return display_data

    async def list_providers(self, event: AstrMessageEvent) -> None:
        """List configured LLM, TTS, and STT providers."""
        umo = event.unified_msg_origin
        cfg = self.context.config.get(umo).get("provider_settings", {})
        reachability_check_enabled = cfg.get("reachability_check", True)

        llm_header = await self.context.i18n.t(event, "provider.list.llm_header")
        parts = [f"{llm_header}\n"]
        llms = list(self.context.models.chat())
        ttss = self.context.models.text_to_speech()
        stts = self.context.models.speech_to_text()

        if reachability_check_enabled and (llms or ttss or stts):
            await send_i18n(self.context, event, "provider.list.testing")

        llm_data, tts_data, stt_data = await asyncio.gather(
            self._build_provider_display_data(
                event,
                llms,
                "llm",
                reachability_check_enabled,
            ),
            self._build_provider_display_data(
                event,
                ttss,
                "tts",
                reachability_check_enabled,
            ),
            self._build_provider_display_data(
                event,
                stts,
                "stt",
                reachability_check_enabled,
            ),
        )

        provider_using = self.context.models.using_chat(umo=umo)
        for index, data in enumerate(llm_data):
            line = f"{index + 1}. {data['info']}{data['mark']}"
            if (
                provider_using
                and provider_using.meta().id == data["provider"].meta().id
            ):
                line += " " + await self.context.i18n.t(event, "provider.list.current")
            parts.append(line + "\n")

        if tts_data:
            tts_header = await self.context.i18n.t(event, "provider.list.tts_header")
            parts.append(f"\n## {tts_header}\n")
            tts_using = self.context.models.using_text_to_speech(umo=umo)
            for index, data in enumerate(tts_data):
                line = f"{index + 1}. {data['info']}{data['mark']}"
                if tts_using and tts_using.meta().id == data["provider"].meta().id:
                    line += " " + await self.context.i18n.t(
                        event, "provider.list.current"
                    )
                parts.append(line + "\n")

        if stt_data:
            stt_header = await self.context.i18n.t(event, "provider.list.stt_header")
            parts.append(f"\n## {stt_header}\n")
            stt_using = self.context.models.using_speech_to_text(umo=umo)
            for index, data in enumerate(stt_data):
                line = f"{index + 1}. {data['info']}{data['mark']}"
                if stt_using and stt_using.meta().id == data["provider"].meta().id:
                    line += " " + await self.context.i18n.t(
                        event, "provider.list.current"
                    )
                parts.append(line + "\n")

        parts.append("\n" + await self.context.i18n.t(event, "provider.list.llm_hint"))
        if ttss:
            parts.append(
                "\n" + await self.context.i18n.t(event, "provider.list.tts_hint")
            )
        if stts:
            parts.append(
                "\n" + await self.context.i18n.t(event, "provider.list.stt_hint")
            )
        reply_text(event, "".join(parts))

    async def set_llm_provider(self, event: AstrMessageEvent, index: int) -> None:
        await self._set_provider_by_index(
            event,
            index,
            list(self.context.models.chat()),
            ProviderType.CHAT_COMPLETION,
        )

    async def set_tts_provider(self, event: AstrMessageEvent, index: int) -> None:
        await self._set_provider_by_index(
            event,
            index,
            self.context.models.text_to_speech(),
            ProviderType.TEXT_TO_SPEECH,
        )

    async def set_stt_provider(self, event: AstrMessageEvent, index: int) -> None:
        await self._set_provider_by_index(
            event,
            index,
            self.context.models.speech_to_text(),
            ProviderType.SPEECH_TO_TEXT,
        )

    async def _set_provider_by_index(
        self,
        event: AstrMessageEvent,
        index: int,
        providers: Sequence[_SwitchableProvider],
        provider_type: ProviderType,
    ) -> None:
        if index < 1 or index > len(providers):
            await reply_i18n(self.context, event, "provider.set.invalid")
            return
        provider = providers[index - 1]
        provider_id = provider.meta().id
        await self.context.models.select(
            provider_id=provider_id,
            provider_type=provider_type,
            umo=event.unified_msg_origin,
        )
        await reply_i18n(
            self.context, event, "provider.set.ok", provider_id=provider_id
        )

    async def _switch_model_by_name(
        self,
        event: AstrMessageEvent,
        model_name: str,
        provider: Provider,
    ) -> None:
        model_name = model_name.strip()
        if not model_name:
            await reply_i18n(self.context, event, "provider.models.empty_name")
            return

        umo = event.unified_msg_origin
        config = self._get_model_lookup_config(umo)
        current_provider_id = provider.meta().id

        models = await self._get_models_or_reply_error(
            event,
            provider,
            config,
            warning_log="Failed to fetch models from provider %s: %s",
        )
        if models is None:
            return

        matched_model_name = self._resolve_model_name(model_name, models)
        if matched_model_name is not None:
            reply_text(
                event,
                await self._apply_model(event, provider, matched_model_name, umo=umo),
            )
            return

        (
            target_provider,
            matched_target_model_name,
        ) = await self._find_provider_for_model(
            model_name,
            exclude_provider_id=current_provider_id,
            config=config,
        )
        if target_provider is None or matched_target_model_name is None:
            await reply_i18n(
                self.context,
                event,
                "provider.models.not_found",
                model_name=model_name,
            )
            return

        target_id = target_provider.meta().id
        try:
            await self.context.models.select(
                provider_id=target_id,
                provider_type=ProviderType.CHAT_COMPLETION,
                umo=umo,
            )
            await self._apply_model(
                event, target_provider, matched_target_model_name, umo=umo
            )
            await reply_i18n(
                self.context,
                event,
                "provider.models.switched_provider",
                provider_id=target_id,
                model=matched_target_model_name,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await reply_i18n(
                self.context,
                event,
                "provider.models.switch_failed",
                error=safe_error("", exc),
            )

    async def list_models(self, event: AstrMessageEvent) -> None:
        """List models for the current chat provider."""
        provider = self.context.models.using_chat(event.unified_msg_origin)
        if not provider:
            await reply_i18n(self.context, event, "provider.models.none")
            return

        config = self._get_model_lookup_config(event.unified_msg_origin)
        models = await self._get_models_or_reply_error(
            event,
            provider,
            config,
        )
        if models is None:
            return

        header = await self.context.i18n.t(event, "provider.models.header")
        parts = [header]
        for index, model in enumerate(models, 1):
            parts.append(f"\n{index}. {model}")
        current_model = provider.get_model() or await self.context.i18n.t(
            event, "provider.models.empty_current"
        )
        parts.append(
            "\n"
            + await self.context.i18n.t(
                event, "provider.models.current", model=current_model
            )
        )
        parts.append("\n" + await self.context.i18n.t(event, "provider.models.hint"))
        reply_text(event, "".join(parts))

    async def set_model(self, event: AstrMessageEvent, name_or_index: str) -> None:
        """Switch the current chat model by name or list index."""
        provider = self.context.models.using_chat(event.unified_msg_origin)
        if not provider:
            await reply_i18n(self.context, event, "provider.models.none")
            return

        config = self._get_model_lookup_config(event.unified_msg_origin)
        if name_or_index.isdecimal():
            model_index = int(name_or_index)
            models = await self._get_models_or_reply_error(
                event,
                provider,
                config,
            )
            if models is None:
                return
            if model_index < 1 or model_index > len(models):
                await reply_i18n(self.context, event, "provider.models.invalid_index")
                return

            try:
                new_model = models[model_index - 1]
                reply_text(
                    event,
                    await self._apply_model(
                        event,
                        provider,
                        new_model,
                        umo=event.unified_msg_origin,
                    ),
                )
            except Exception as exc:
                await reply_i18n(
                    self.context,
                    event,
                    "provider.models.switch_failed",
                    error=safe_error("", exc),
                )
            return

        await self._switch_model_by_name(event, name_or_index, provider)
