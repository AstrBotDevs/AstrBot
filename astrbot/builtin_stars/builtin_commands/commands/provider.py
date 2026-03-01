from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.provider.entities import ProviderType
from astrbot.core.utils.error_redaction import safe_error

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider


MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT = 30.0
MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT = 4
MODEL_LOOKUP_MAX_CONCURRENCY_UPPER_BOUND = 16
MODEL_LIST_CACHE_TTL_KEY = "model_list_cache_ttl_seconds"
MODEL_LOOKUP_MAX_CONCURRENCY_KEY = "model_lookup_max_concurrency"


class ProviderCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context
        self._model_cache: dict[str, tuple[float, list[str]]] = {}
        self._register_provider_change_hook()

    def _register_provider_change_hook(self) -> None:
        set_change_callback = getattr(
            self.context.provider_manager,
            "set_provider_change_callback",
            None,
        )
        if callable(set_change_callback):
            set_change_callback(self._on_provider_manager_changed)
            return
        register_change_hook = getattr(
            self.context.provider_manager,
            "register_provider_change_hook",
            None,
        )
        if callable(register_change_hook):
            register_change_hook(self._on_provider_manager_changed)

    def invalidate_provider_models_cache(self, provider_id: str | None = None) -> None:
        """Public hook for cache invalidation on external provider config changes."""
        if provider_id is None:
            self._model_cache.clear()
            return
        self._model_cache.pop(provider_id, None)

    def _on_provider_manager_changed(
        self,
        provider_id: str,
        provider_type: ProviderType,
        umo: str | None,
    ) -> None:
        if provider_type == ProviderType.CHAT_COMPLETION:
            self.invalidate_provider_models_cache(provider_id)

    def _get_cached_models(
        self, provider_id: str, *, ttl_seconds: float
    ) -> list[str] | None:
        if ttl_seconds <= 0:
            return None
        entry = self._model_cache.get(provider_id)
        if not entry:
            return None
        timestamp, models = entry
        if time.monotonic() - timestamp > ttl_seconds:
            self._model_cache.pop(provider_id, None)
            return None
        return list(models)

    def _set_cached_models(self, provider_id: str, models: list[str]) -> None:
        self._model_cache[provider_id] = (time.monotonic(), list(models))

    def _get_ttl_setting(self, umo: str | None) -> float:
        if not umo:
            return MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT
        try:
            cfg = self.context.get_config(umo).get("provider_settings", {})
            raw = cfg.get(MODEL_LIST_CACHE_TTL_KEY)
            if raw is None:
                return MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT
            return float(raw)
        except Exception as e:
            logger.debug(
                "读取 %s 失败，回退默认值 %r: %s",
                MODEL_LIST_CACHE_TTL_KEY,
                MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT,
                safe_error("", e),
            )
            return MODEL_LIST_CACHE_TTL_SECONDS_DEFAULT

    def _get_lookup_concurrency(self, umo: str | None) -> int:
        if not umo:
            return MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT
        try:
            cfg = self.context.get_config(umo).get("provider_settings", {})
            raw = cfg.get(MODEL_LOOKUP_MAX_CONCURRENCY_KEY)
            if raw is None:
                return MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT
            return int(raw)
        except Exception as e:
            logger.debug(
                "读取 %s 失败，回退默认值 %r: %s",
                MODEL_LOOKUP_MAX_CONCURRENCY_KEY,
                MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT,
                safe_error("", e),
            )
            return MODEL_LOOKUP_MAX_CONCURRENCY_DEFAULT

    def _resolve_model_name(
        self,
        model_name: str,
        models: Sequence[str],
    ) -> str | None:
        """Resolve model name with precedence:
        exact > case-insensitive > provider-qualified suffix.
        """
        requested = model_name.strip()
        if not requested:
            return None

        requested_norm = requested.casefold()

        # exact / case-insensitive match
        for candidate in models:
            if candidate == requested or candidate.casefold() == requested_norm:
                return candidate

        # provider-qualified suffix match:
        # e.g. candidate `openai/gpt-4o` should match requested `gpt-4o`.
        def _match_qualified_suffix(req: str, cand: str) -> bool:
            return cand.endswith(f"/{req}") or cand.endswith(f":{req}")

        for candidate in models:
            if _match_qualified_suffix(requested_norm, candidate.casefold()):
                return candidate

        return None

    def _apply_model(self, prov: Provider, model_name: str) -> str:
        prov.set_model(model_name)
        self.invalidate_provider_models_cache(prov.meta().id)
        return f"切换模型成功。当前提供商: [{prov.meta().id}] 当前模型: [{prov.get_model()}]"

    async def _get_provider_models(
        self,
        provider: Provider,
        *,
        use_cache: bool = True,
        umo: str | None = None,
    ) -> list[str]:
        provider_id = provider.meta().id
        ttl_seconds = max(float(self._get_ttl_setting(umo)), 0.0)
        if use_cache:
            cached = self._get_cached_models(provider_id, ttl_seconds=ttl_seconds)
            if cached is not None:
                return cached

        models = list(await provider.get_models())
        if use_cache and ttl_seconds > 0:
            self._set_cached_models(provider_id, models)
        return models

    def _log_reachability_failure(
        self,
        provider,
        provider_capability_type: ProviderType | None,
        err_code: str,
        err_reason: str,
    ) -> None:
        """记录不可达原因到日志。"""
        meta = provider.meta()
        logger.warning(
            "Provider reachability check failed: id=%s type=%s code=%s reason=%s",
            meta.id,
            provider_capability_type.name if provider_capability_type else "unknown",
            err_code,
            err_reason,
        )

    async def _test_provider_capability(self, provider):
        """测试单个 provider 的可用性"""
        meta = provider.meta()
        provider_capability_type = meta.provider_type

        try:
            await provider.test()
            return True, None, None
        except Exception as e:
            err_code = "TEST_FAILED"
            err_reason = safe_error("", e)
            self._log_reachability_failure(
                provider, provider_capability_type, err_code, err_reason
            )
            return False, err_code, err_reason

    async def _find_provider_for_model(
        self,
        model_name: str,
        exclude_provider_id: str | None = None,
        umo: str | None = None,
    ) -> tuple[Provider | None, str | None]:
        all_providers = []
        for provider in self.context.get_all_providers():
            provider_meta = provider.meta()
            if provider_meta.provider_type != ProviderType.CHAT_COMPLETION:
                continue
            if (
                exclude_provider_id is not None
                and provider_meta.id == exclude_provider_id
            ):
                continue
            all_providers.append(provider)
        if not all_providers:
            return None, None

        failed_provider_errors: list[tuple[str, str]] = []
        raw_concurrency = self._get_lookup_concurrency(umo)
        max_concurrency = min(
            max(int(raw_concurrency), 1),
            MODEL_LOOKUP_MAX_CONCURRENCY_UPPER_BOUND,
        )
        for start in range(0, len(all_providers), max_concurrency):
            batch_providers = all_providers[start : start + max_concurrency]
            batch_results = await asyncio.gather(
                *[
                    self._get_provider_models(provider, umo=umo)
                    for provider in batch_providers
                ],
                return_exceptions=True,
            )
            for provider, result in zip(batch_providers, batch_results, strict=False):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                provider_id = provider.meta().id
                if isinstance(result, Exception):
                    failed_provider_errors.append((provider_id, safe_error("", result)))
                    continue
                matched_model_name = self._resolve_model_name(model_name, result)
                if matched_model_name is not None:
                    return provider, matched_model_name

        if failed_provider_errors and len(failed_provider_errors) == len(all_providers):
            failed_ids = ",".join(
                provider_id for provider_id, _ in failed_provider_errors
            )
            logger.error(
                "跨提供商查找模型 %s 时，所有 %d 个提供商的 get_models() 均失败: %s。请检查配置或网络",
                model_name,
                len(all_providers),
                failed_ids,
            )
        elif failed_provider_errors:
            logger.debug(
                "跨提供商查找模型 %s 时有 %d 个提供商获取模型失败: %s",
                model_name,
                len(failed_provider_errors),
                ",".join(
                    f"{provider_id}({error})"
                    for provider_id, error in failed_provider_errors
                ),
            )
        return None, None

    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ) -> None:
        """查看或者切换 LLM Provider"""
        umo = event.unified_msg_origin
        cfg = self.context.get_config(umo).get("provider_settings", {})
        reachability_check_enabled = cfg.get("reachability_check", True)

        if idx is None:
            parts = ["## 载入的 LLM 提供商\n"]

            # 获取所有类型的提供商
            llms = list(self.context.get_all_providers())
            ttss = self.context.get_all_tts_providers()
            stts = self.context.get_all_stt_providers()

            # 构造待检测列表: [(provider, type_label), ...]
            all_providers = []
            all_providers.extend([(p, "llm") for p in llms])
            all_providers.extend([(p, "tts") for p in ttss])
            all_providers.extend([(p, "stt") for p in stts])

            # 并发测试连通性
            if reachability_check_enabled:
                if all_providers:
                    await event.send(
                        MessageEventResult().message(
                            "正在进行提供商可达性测试，请稍候..."
                        )
                    )
                check_results = await asyncio.gather(
                    *[self._test_provider_capability(p) for p, _ in all_providers],
                    return_exceptions=True,
                )
            else:
                # 用 None 表示未检测
                check_results = [None for _ in all_providers]

            # 整合结果
            display_data = []
            for (p, p_type), reachable in zip(all_providers, check_results):
                meta = p.meta()
                id_ = meta.id
                error_code = None

                if isinstance(reachable, asyncio.CancelledError):
                    raise reachable
                if isinstance(reachable, Exception):
                    # 异常情况下兜底处理，避免单个 provider 导致列表失败
                    self._log_reachability_failure(
                        p,
                        None,
                        reachable.__class__.__name__,
                        safe_error("", reachable),
                    )
                    reachable_flag = False
                    error_code = reachable.__class__.__name__
                elif isinstance(reachable, tuple):
                    reachable_flag, error_code, _ = reachable
                else:
                    reachable_flag = reachable

                # 根据类型构建显示名称
                if p_type == "llm":
                    info = f"{id_} ({meta.model})"
                else:
                    info = f"{id_}"

                # 确定状态标记
                if reachable_flag is True:
                    mark = " ✅"
                elif reachable_flag is False:
                    if error_code:
                        mark = f" ❌(错误码: {error_code})"
                    else:
                        mark = " ❌"
                else:
                    mark = ""  # 不支持检测时不显示标记

                display_data.append(
                    {
                        "type": p_type,
                        "info": info,
                        "mark": mark,
                        "provider": p,
                    }
                )

            # 分组输出
            # 1. LLM
            llm_data = [d for d in display_data if d["type"] == "llm"]
            for i, d in enumerate(llm_data):
                line = f"{i + 1}. {d['info']}{d['mark']}"
                provider_using = self.context.get_using_provider(umo=umo)
                if (
                    provider_using
                    and provider_using.meta().id == d["provider"].meta().id
                ):
                    line += " (当前使用)"
                parts.append(line + "\n")

            # 2. TTS
            tts_data = [d for d in display_data if d["type"] == "tts"]
            if tts_data:
                parts.append("\n## 载入的 TTS 提供商\n")
                for i, d in enumerate(tts_data):
                    line = f"{i + 1}. {d['info']}{d['mark']}"
                    tts_using = self.context.get_using_tts_provider(umo=umo)
                    if tts_using and tts_using.meta().id == d["provider"].meta().id:
                        line += " (当前使用)"
                    parts.append(line + "\n")

            # 3. STT
            stt_data = [d for d in display_data if d["type"] == "stt"]
            if stt_data:
                parts.append("\n## 载入的 STT 提供商\n")
                for i, d in enumerate(stt_data):
                    line = f"{i + 1}. {d['info']}{d['mark']}"
                    stt_using = self.context.get_using_stt_provider(umo=umo)
                    if stt_using and stt_using.meta().id == d["provider"].meta().id:
                        line += " (当前使用)"
                    parts.append(line + "\n")

            parts.append("\n使用 /provider <序号> 切换 LLM 提供商。")
            ret = "".join(parts)

            if ttss:
                ret += "\n使用 /provider tts <序号> 切换 TTS 提供商。"
            if stts:
                ret += "\n使用 /provider stt <序号> 切换 STT 提供商。"
            if not reachability_check_enabled:
                ret += "\n已跳过提供商可达性检测，如需检测请在配置文件中开启。"

            event.set_result(MessageEventResult().message(ret))
        elif idx == "tts":
            if idx2 is None:
                event.set_result(MessageEventResult().message("请输入序号。"))
                return
            if idx2 > len(self.context.get_all_tts_providers()) or idx2 < 1:
                event.set_result(MessageEventResult().message("无效的提供商序号。"))
                return
            provider = self.context.get_all_tts_providers()[idx2 - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.TEXT_TO_SPEECH,
                umo=umo,
            )
            event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))
        elif idx == "stt":
            if idx2 is None:
                event.set_result(MessageEventResult().message("请输入序号。"))
                return
            if idx2 > len(self.context.get_all_stt_providers()) or idx2 < 1:
                event.set_result(MessageEventResult().message("无效的提供商序号。"))
                return
            provider = self.context.get_all_stt_providers()[idx2 - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.SPEECH_TO_TEXT,
                umo=umo,
            )
            event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))
        elif isinstance(idx, int):
            if idx > len(self.context.get_all_providers()) or idx < 1:
                event.set_result(MessageEventResult().message("无效的提供商序号。"))
                return
            provider = self.context.get_all_providers()[idx - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.CHAT_COMPLETION,
                umo=umo,
            )
            event.set_result(MessageEventResult().message(f"成功切换到 {id_}。"))
        else:
            event.set_result(MessageEventResult().message("无效的参数。"))

    async def _switch_model_by_name(
        self, message: AstrMessageEvent, model_name: str, prov: Provider
    ) -> None:
        model_name = model_name.strip()
        if not model_name:
            message.set_result(MessageEventResult().message("模型名不能为空。"))
            return

        umo = message.unified_msg_origin
        curr_provider_id = prov.meta().id

        try:
            models = await self._get_provider_models(prov, umo=umo)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            err_msg = safe_error("", e)
            logger.warning(
                "获取当前提供商 %s 模型列表失败，停止跨提供商查找: %s",
                curr_provider_id,
                err_msg,
            )
            message.set_result(
                MessageEventResult().message(
                    safe_error("获取当前提供商模型列表失败: ", e)
                )
            )
            return

        matched_model_name = self._resolve_model_name(model_name, models)
        if matched_model_name is not None:
            message.set_result(
                MessageEventResult().message(
                    self._apply_model(prov, matched_model_name)
                ),
            )
            return

        target_prov, matched_target_model_name = await self._find_provider_for_model(
            model_name, exclude_provider_id=curr_provider_id, umo=umo
        )

        if target_prov is None or matched_target_model_name is None:
            message.set_result(
                MessageEventResult().message(
                    f"模型 [{model_name}] 未在任何已配置的提供商中找到，或所有提供商模型列表获取失败，请检查配置或网络后重试。",
                ),
            )
            return

        target_id = target_prov.meta().id
        try:
            await self.context.provider_manager.set_provider(
                provider_id=target_id,
                provider_type=ProviderType.CHAT_COMPLETION,
                umo=umo,
            )
            target_prov.set_model(matched_target_model_name)
            self.invalidate_provider_models_cache(target_prov.meta().id)
            message.set_result(
                MessageEventResult().message(
                    f"检测到模型 [{matched_target_model_name}] 属于提供商 [{target_id}]，已自动切换提供商并设置模型。",
                ),
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            message.set_result(
                MessageEventResult().message(
                    safe_error("跨提供商切换并设置模型失败: ", e)
                ),
            )

    async def model_ls(
        self,
        message: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ) -> None:
        """查看或者切换模型"""
        prov = self.context.get_using_provider(message.unified_msg_origin)
        if not prov:
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"),
            )
            return

        if idx_or_name is None:
            models = []
            try:
                models = await self._get_provider_models(
                    prov, umo=message.unified_msg_origin
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                message.set_result(
                    MessageEventResult()
                    .message(safe_error("获取模型列表失败: ", e))
                    .use_t2i(False),
                )
                return
            parts = ["下面列出了此模型提供商可用模型:"]
            for i, model in enumerate(models, 1):
                parts.append(f"\n{i}. {model}")

            curr_model = prov.get_model() or "无"
            parts.append(f"\n当前模型: [{curr_model}]")
            parts.append(
                "\nTips: 使用 /model <模型名/编号> 切换模型。输入模型名时可自动跨提供商查找并切换；跨提供商也可使用 /provider 切换。"
            )

            ret = "".join(parts)
            message.set_result(MessageEventResult().message(ret).use_t2i(False))
        elif isinstance(idx_or_name, int):
            models = []
            try:
                models = await self._get_provider_models(
                    prov, umo=message.unified_msg_origin
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                message.set_result(
                    MessageEventResult().message(safe_error("获取模型列表失败: ", e)),
                )
                return
            if idx_or_name > len(models) or idx_or_name < 1:
                message.set_result(MessageEventResult().message("模型序号错误。"))
            else:
                try:
                    new_model = models[idx_or_name - 1]
                    message.set_result(
                        MessageEventResult().message(
                            self._apply_model(prov, new_model)
                        ),
                    )
                except Exception as e:
                    message.set_result(
                        MessageEventResult().message(
                            safe_error("切换模型未知错误: ", e)
                        ),
                    )
                    return
        else:
            await self._switch_model_by_name(message, idx_or_name, prov)

    async def key(self, message: AstrMessageEvent, index: int | None = None) -> None:
        prov = self.context.get_using_provider(message.unified_msg_origin)
        if not prov:
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"),
            )
            return

        if index is None:
            keys_data = prov.get_keys()
            curr_key = prov.get_current_key()
            parts = ["Key:"]
            for i, k in enumerate(keys_data, 1):
                parts.append(f"\n{i}. {k[:8]}")

            parts.append(f"\n当前 Key: {curr_key[:8]}")
            parts.append("\n当前模型: " + prov.get_model())
            parts.append("\n使用 /key <idx> 切换 Key。")

            ret = "".join(parts)
            message.set_result(MessageEventResult().message(ret).use_t2i(False))
        else:
            keys_data = prov.get_keys()
            if index > len(keys_data) or index < 1:
                message.set_result(MessageEventResult().message("Key 序号错误。"))
            else:
                try:
                    new_key = keys_data[index - 1]
                    prov.set_key(new_key)
                    self.invalidate_provider_models_cache(prov.meta().id)
                    message.set_result(MessageEventResult().message("切换 Key 成功。"))
                except Exception as e:
                    message.set_result(
                        MessageEventResult().message(
                            safe_error("切换 Key 未知错误: ", e)
                        ),
                    )
                    return
