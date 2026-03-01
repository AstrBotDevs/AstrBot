from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.provider.entities import ProviderType

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider

_SECRET_PATTERNS = [
    re.compile(
        r"(?i)\b(api_?key|key|access_?token|token|secret|auth_?token|session_?id|password)\s*=\s*[^&'\" ]+"
    ),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
]


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


@dataclass
class _ModelCacheEntry:
    timestamp: float
    models: tuple[str, ...]


class ProviderCommands:
    _MODEL_LIST_CACHE_TTL_SECONDS = 30.0
    _MODEL_LOOKUP_MAX_CONCURRENCY = 4

    def __init__(self, context: star.Context) -> None:
        self.context = context
        self._provider_models_cache: dict[str, _ModelCacheEntry] = {}

    def _invalidate_provider_models_cache(self, provider_id: str | None = None) -> None:
        if provider_id is None:
            self._provider_models_cache.clear()
            return
        self._provider_models_cache.pop(provider_id, None)

    def _update_provider_and_invalidate(
        self,
        provider: Provider,
        *,
        model_name: str | None = None,
        key: str | None = None,
    ) -> None:
        if model_name is not None:
            provider.set_model(model_name)
        if key is not None:
            provider.set_key(key)
        self._invalidate_provider_models_cache(provider.meta().id)

    @staticmethod
    def _safe_err(prefix: str, e: Exception) -> str:
        return prefix + redact_secrets(str(e))

    @staticmethod
    def _normalize_model_name(model_name: str) -> str:
        return model_name.strip().casefold()

    def _resolve_model_name(self, model_name: str, models: list[str]) -> str | None:
        normalized_model_name = self._normalize_model_name(model_name)
        if not normalized_model_name:
            return None
        if model_name in models:
            return model_name

        for candidate in models:
            normalized_candidate = self._normalize_model_name(candidate)
            if normalized_candidate == normalized_model_name:
                return candidate
            if normalized_candidate.endswith(
                f"/{normalized_model_name}"
            ) or normalized_candidate.endswith(f":{normalized_model_name}"):
                return candidate
            if normalized_model_name.endswith(
                f"/{normalized_candidate}"
            ) or normalized_model_name.endswith(f":{normalized_candidate}"):
                return candidate
        return None

    def _get_model_cache_ttl_seconds(self, umo: str | None = None) -> float:
        ttl = self._MODEL_LIST_CACHE_TTL_SECONDS
        if not umo:
            return ttl
        try:
            cfg = self.context.get_config(umo).get("provider_settings", {})
            configured_ttl = cfg.get("model_list_cache_ttl_seconds")
            if configured_ttl is not None:
                ttl = float(configured_ttl)
        except Exception as e:
            logger.debug(
                "读取 model_list_cache_ttl_seconds 失败，回退默认值 %.1f: %s",
                self._MODEL_LIST_CACHE_TTL_SECONDS,
                redact_secrets(str(e)),
            )
            ttl = self._MODEL_LIST_CACHE_TTL_SECONDS
        return max(ttl, 0.0)

    async def _get_provider_models(
        self,
        provider: Provider,
        *,
        use_cache: bool = True,
        umo: str | None = None,
    ) -> list[str]:
        provider_id = provider.meta().id
        now = time.monotonic()
        ttl_seconds = self._get_model_cache_ttl_seconds(umo)
        if use_cache and ttl_seconds > 0:
            cached = self._provider_models_cache.get(provider_id)
            if cached and now - cached.timestamp <= ttl_seconds:
                return list(cached.models)

        models = list(await provider.get_models())
        if use_cache and ttl_seconds > 0:
            self._provider_models_cache[provider_id] = _ModelCacheEntry(
                timestamp=now,
                models=tuple(models),
            )
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
            err_reason = redact_secrets(str(e))
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
        """在所有 LLM 提供商中查找包含指定模型的提供商。"""
        all_providers = [
            p
            for p in self.context.get_all_providers()
            if not exclude_provider_id or p.meta().id != exclude_provider_id
        ]
        if not all_providers:
            return None, None

        semaphore = asyncio.Semaphore(self._MODEL_LOOKUP_MAX_CONCURRENCY)

        async def _fetch_models(
            provider: Provider,
        ) -> tuple[Provider, list[str] | None, Exception | None]:
            async with semaphore:
                try:
                    return (
                        provider,
                        await self._get_provider_models(provider, umo=umo),
                        None,
                    )
                except Exception as e:
                    return provider, None, e

        results = await asyncio.gather(
            *[_fetch_models(provider) for provider in all_providers]
        )
        failed_provider_errors: list[tuple[str, str]] = []
        for provider, models, error in results:
            provider_id = provider.meta().id
            if error is not None:
                failed_provider_errors.append((provider_id, self._safe_err("", error)))
                continue
            if models is None:
                continue
            matched_model_name = self._resolve_model_name(model_name, models)
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

                if isinstance(reachable, Exception):
                    # 异常情况下兜底处理，避免单个 provider 导致列表失败
                    self._log_reachability_failure(
                        p,
                        None,
                        reachable.__class__.__name__,
                        redact_secrets(str(reachable)),
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
        except Exception as e:
            err_msg = self._safe_err("", e)
            logger.warning(
                "获取当前提供商 %s 模型列表失败，停止跨提供商查找: %s",
                curr_provider_id,
                err_msg,
            )
            message.set_result(
                MessageEventResult().message(
                    self._safe_err("获取当前提供商模型列表失败: ", e)
                )
            )
            return

        matched_model_name = self._resolve_model_name(model_name, models)
        if matched_model_name is not None:
            self._update_provider_and_invalidate(prov, model_name=matched_model_name)
            message.set_result(
                MessageEventResult().message(
                    f"切换模型成功。当前提供商: [{curr_provider_id}] 当前模型: [{matched_model_name}]",
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
            self._update_provider_and_invalidate(
                target_prov, model_name=matched_target_model_name
            )
            message.set_result(
                MessageEventResult().message(
                    f"检测到模型 [{matched_target_model_name}] 属于提供商 [{target_id}]，已自动切换提供商并设置模型。",
                ),
            )
        except Exception as e:
            message.set_result(
                MessageEventResult().message(
                    self._safe_err("跨提供商切换并设置模型失败: ", e)
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
            except Exception as e:
                message.set_result(
                    MessageEventResult()
                    .message(self._safe_err("获取模型列表失败: ", e))
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
            except Exception as e:
                message.set_result(
                    MessageEventResult().message(
                        self._safe_err("获取模型列表失败: ", e)
                    ),
                )
                return
            if idx_or_name > len(models) or idx_or_name < 1:
                message.set_result(MessageEventResult().message("模型序号错误。"))
            else:
                try:
                    new_model = models[idx_or_name - 1]
                    self._update_provider_and_invalidate(prov, model_name=new_model)
                    message.set_result(
                        MessageEventResult().message(
                            f"切换模型成功。当前提供商: [{prov.meta().id}] 当前模型: [{prov.get_model()}]",
                        ),
                    )
                except Exception as e:
                    message.set_result(
                        MessageEventResult().message(
                            self._safe_err("切换模型未知错误: ", e)
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
                    self._update_provider_and_invalidate(prov, key=new_key)
                    message.set_result(MessageEventResult().message("切换 Key 成功。"))
                except Exception as e:
                    message.set_result(
                        MessageEventResult().message(
                            self._safe_err("切换 Key 未知错误: ", e)
                        ),
                    )
                    return
