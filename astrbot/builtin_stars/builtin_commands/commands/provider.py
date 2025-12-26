import asyncio
import re

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.provider.entities import ProviderType


class ProviderCommands:
    def __init__(self, context: star.Context):
        self.context = context

    def _log_reachability_failure(
        self,
        provider,
        provider_capability_type: ProviderType | None,
        err_code: str,
        err_reason: str,
    ):
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

    async def provider(
        self,
        event: AstrMessageEvent,
        idx: str | int | None = None,
        idx2: int | None = None,
    ):
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

    async def model_ls(
        self,
        message: AstrMessageEvent,
        idx_or_name: int | str | None = None,
    ):
        """查看或者切换模型"""
        prov = self.context.get_using_provider(message.unified_msg_origin)
        if not prov:
            message.set_result(
                MessageEventResult().message("未找到任何 LLM 提供商。请先配置。"),
            )
            return
        # 定义正则表达式匹配 API 密钥
        api_key_pattern = re.compile(r"key=[^&'\" ]+")

        if idx_or_name is None:
            models = []
            try:
                models = await prov.get_models()
            except BaseException as e:
                err_msg = api_key_pattern.sub("key=***", str(e))
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
                "\nTips: 使用 /model <模型名/编号>，即可实时更换模型。如目标模型不存在于上表，请输入模型名。"
            )

            ret = "".join(parts)
            message.set_result(MessageEventResult().message(ret).use_t2i(False))
        elif isinstance(idx_or_name, int):
            models = []
            try:
                models = await prov.get_models()
            except BaseException as e:
                message.set_result(
                    MessageEventResult().message("获取模型列表失败: " + str(e)),
                )
                return
            if idx_or_name > len(models) or idx_or_name < 1:
                message.set_result(MessageEventResult().message("模型序号错误。"))
            else:
                try:
                    new_model = models[idx_or_name - 1]
                    prov.set_model(new_model)
                except BaseException as e:
                    message.set_result(
                        MessageEventResult().message("切换模型未知错误: " + str(e)),
                    )
                message.set_result(
                    MessageEventResult().message(
                        f"切换模型成功。当前提供商: [{prov.meta().id}] 当前模型: [{prov.get_model()}]",
                    ),
                )
        else:
            prov.set_model(idx_or_name)
            message.set_result(
                MessageEventResult().message(f"切换模型到 {prov.get_model()}。"),
            )

    async def key(self, message: AstrMessageEvent, index: int | None = None):
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
                except BaseException as e:
                    message.set_result(
                        MessageEventResult().message(f"切换 Key 未知错误: {e!s}"),
                    )
                message.set_result(MessageEventResult().message("切换 Key 成功。"))
