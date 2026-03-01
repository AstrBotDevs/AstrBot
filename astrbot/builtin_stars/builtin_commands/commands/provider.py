import asyncio
import re
import time
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.provider.entities import ProviderType

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider

_API_KEY_PATTERN = re.compile(r"(?i)(api_?key|key)=[^&'\" ]+")


class _AllProvidersModelFetchFailedError(RuntimeError):
    pass


class ProviderCommands:
    _MODEL_LIST_CACHE_TTL_SECONDS = 30.0

    def __init__(self, context: star.Context) -> None:
        self.context = context
        self._provider_models_cache: dict[str, tuple[float, tuple[str, ...]]] = {}

    def _invalidate_provider_models_cache(self, provider_id: str | None = None) -> None:
        if provider_id is None:
            self._provider_models_cache.clear()
            return
        self._provider_models_cache.pop(provider_id, None)

    @staticmethod
    def _mask_sensitive_text(value: str) -> str:
        return _API_KEY_PATTERN.sub("key=***", value)

    def _safe_err(self, e: BaseException) -> str:
        return self._mask_sensitive_text(str(e))

    async def _get_provider_models(
        self, provider: "Provider", *, use_cache: bool = True
    ) -> list[str]:
        provider_id = provider.meta().id
        now = time.monotonic()
        if use_cache:
            cached = self._provider_models_cache.get(provider_id)
            if cached and now - cached[0] <= self._MODEL_LIST_CACHE_TTL_SECONDS:
                return list(cached[1])

        models = list(await provider.get_models())
        self._provider_models_cache[provider_id] = (now, tuple(models))
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
            err_reason = str(e)
            self._log_reachability_failure(
                provider, provider_capability_type, err_code, err_reason
            )
            return False, err_code, err_reason

    async def _find_provider_for_model(
        self, model_name: str, exclude_provider_id: str | None = None
    ) -> "Provider | None":
        """在所有 LLM 提供商中查找包含指定模型的提供商。"""
        all_providers = [
            p
            for p in self.context.get_all_providers()
            if not exclude_provider_id or p.meta().id != exclude_provider_id
        ]
        if not all_providers:
            return None
        results = await asyncio.gather(
            *[self._get_provider_models(p) for p in all_providers],
            return_exceptions=True,
        )
        failed_provider_errors: list[tuple[str, str]] = []
        for provider, result in zip(all_providers, results):
            if isinstance(result, BaseException):
                masked_error = self._safe_err(result)
                failed_provider_errors.append((provider.meta().id, masked_error))
                continue
            if model_name in result:
                return provider
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
            raise _AllProvidersModelFetchFailedError(
                f"all providers failed to fetch models: {failed_ids}"
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
        return None

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
                        str(reachable),
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
        self, message: AstrMessageEvent, model_name: str, prov: "Provider"
    ) -> None:
        model_name = model_name.strip()
        if not model_name:
            message.set_result(MessageEventResult().message("模型名不能为空。"))
            return

        umo = message.unified_msg_origin
        curr_provider_id = prov.meta().id

        try:
            models = await self._get_provider_models(prov)
        except BaseException as e:
            err_msg = self._safe_err(e)
            logger.warning(
                "获取当前提供商 %s 模型列表失败，停止跨提供商查找: %s",
                curr_provider_id,
                err_msg,
            )
            message.set_result(
                MessageEventResult().message("获取当前提供商模型列表失败: " + err_msg),
            )
            return

        if model_name in models:
            prov.set_model(model_name)
            self._invalidate_provider_models_cache(curr_provider_id)
            message.set_result(
                MessageEventResult().message(
                    f"切换模型成功。当前提供商: [{curr_provider_id}] 当前模型: [{model_name}]",
                ),
            )
            return

        try:
            target_prov = await self._find_provider_for_model(
                model_name, exclude_provider_id=curr_provider_id
            )
        except _AllProvidersModelFetchFailedError:
            message.set_result(
                MessageEventResult().message(
                    "跨提供商查询模型失败：所有提供商的模型列表均获取失败，请检查提供商配置或网络后重试。",
                ),
            )
            return

        if not target_prov:
            message.set_result(
                MessageEventResult().message(
                    f"模型 [{model_name}] 未在任何已配置的提供商中找到。请使用 /provider 切换到目标提供商，或确认模型名正确。",
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
            target_prov.set_model(model_name)
            self._invalidate_provider_models_cache(target_id)
            message.set_result(
                MessageEventResult().message(
                    f"检测到模型 [{model_name}] 属于提供商 [{target_id}]，已自动切换提供商并设置模型。",
                ),
            )
        except BaseException as e:
            err_msg = self._safe_err(e)
            message.set_result(
                MessageEventResult().message("跨提供商切换并设置模型失败: " + err_msg),
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
                models = await self._get_provider_models(prov)
            except BaseException as e:
                err_msg = self._safe_err(e)
                message.set_result(
                    MessageEventResult()
                    .message("获取模型列表失败: " + err_msg)
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
                models = await self._get_provider_models(prov)
            except BaseException as e:
                err_msg = self._safe_err(e)
                message.set_result(
                    MessageEventResult().message("获取模型列表失败: " + err_msg),
                )
                return
            if idx_or_name > len(models) or idx_or_name < 1:
                message.set_result(MessageEventResult().message("模型序号错误。"))
            else:
                try:
                    new_model = models[idx_or_name - 1]
                    prov.set_model(new_model)
                    self._invalidate_provider_models_cache(prov.meta().id)
                    message.set_result(
                        MessageEventResult().message(
                            f"切换模型成功。当前提供商: [{prov.meta().id}] 当前模型: [{prov.get_model()}]",
                        ),
                    )
                except BaseException as e:
                    err_msg = self._safe_err(e)
                    message.set_result(
                        MessageEventResult().message("切换模型未知错误: " + err_msg),
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
                    self._invalidate_provider_models_cache(prov.meta().id)
                except BaseException as e:
                    message.set_result(
                        MessageEventResult().message(f"切换 Key 未知错误: {e!s}"),
                    )
                message.set_result(MessageEventResult().message("切换 Key 成功。"))
