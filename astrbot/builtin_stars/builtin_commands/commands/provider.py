from __future__ import annotations

import asyncio

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.provider.entities import ProviderType
from astrbot.core.utils.error_redaction import safe_error


class ProviderCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

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
        except Exception as e:
            err_code = "TEST_FAILED"
            err_reason = safe_error("", e)
            self._log_reachability_failure(
                provider, provider_capability_type, err_code, err_reason
            )
            return False, err_code, err_reason

    async def _build_provider_display_data(
        self,
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
            else:
                reachable_flag = reachable

            if provider_type == "llm":
                info = f"{id_} ({meta.model})"
            else:
                info = f"{id_}"

            if reachable_flag is True:
                mark = " ✅"
            elif reachable_flag is False:
                if error_code:
                    mark = f" ❌(errcode: {error_code})"
                else:
                    mark = " ❌"
            else:
                mark = ""

            display_data.append(
                {
                    "info": info,
                    "mark": mark,
                    "provider": provider,
                }
            )

        return display_data

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
            parts = ["## LLM Providers\n"]

            llms = list(self.context.get_all_providers())
            ttss = self.context.get_all_tts_providers()
            stts = self.context.get_all_stt_providers()

            if reachability_check_enabled and (llms or ttss or stts):
                await event.send(
                    MessageEventResult().message("👀 Testing provider reachability...")
                )

            llm_data, tts_data, stt_data = await asyncio.gather(
                self._build_provider_display_data(
                    llms,
                    "llm",
                    reachability_check_enabled,
                ),
                self._build_provider_display_data(
                    ttss,
                    "tts",
                    reachability_check_enabled,
                ),
                self._build_provider_display_data(
                    stts,
                    "stt",
                    reachability_check_enabled,
                ),
            )

            provider_using = self.context.get_using_provider(umo=umo)
            for i, d in enumerate(llm_data):
                line = f"{i + 1}. {d['info']}{d['mark']}"
                if (
                    provider_using
                    and provider_using.meta().id == d["provider"].meta().id
                ):
                    line += " 👈"
                parts.append(line + "\n")

            if tts_data:
                parts.append("\n## TTS Providers\n")
                tts_using = self.context.get_using_tts_provider(umo=umo)
                for i, d in enumerate(tts_data):
                    line = f"{i + 1}. {d['info']}{d['mark']}"
                    if tts_using and tts_using.meta().id == d["provider"].meta().id:
                        line += " 👈"
                    parts.append(line + "\n")

            if stt_data:
                parts.append("\n## STT Providers\n")
                stt_using = self.context.get_using_stt_provider(umo=umo)
                for i, d in enumerate(stt_data):
                    line = f"{i + 1}. {d['info']}{d['mark']}"
                    if stt_using and stt_using.meta().id == d["provider"].meta().id:
                        line += " 👈"
                    parts.append(line + "\n")

            parts.append("\nUse /provider <idx> to switch LLM providers.")
            ret = "".join(parts)

            if ttss:
                ret += "\nUse /provider tts <idx> to switch TTS providers."
            if stts:
                ret += "\nUse /provider stt <idx> to switch STT providers."

            event.set_result(MessageEventResult().message(ret))
        elif idx == "tts":
            if idx2 is None:
                event.set_result(
                    MessageEventResult().message("Please enter the index.")
                )
                return
            if idx2 > len(self.context.get_all_tts_providers()) or idx2 < 1:
                event.set_result(
                    MessageEventResult().message("❌ Invalid provider index.")
                )
                return
            provider = self.context.get_all_tts_providers()[idx2 - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.TEXT_TO_SPEECH,
                umo=umo,
            )
            event.set_result(
                MessageEventResult().message(f"✅ Successfully switched to {id_}.")
            )
        elif idx == "stt":
            if idx2 is None:
                event.set_result(
                    MessageEventResult().message("Please enter the index.")
                )
                return
            if idx2 > len(self.context.get_all_stt_providers()) or idx2 < 1:
                event.set_result(
                    MessageEventResult().message("❌ Invalid provider index.")
                )
                return
            provider = self.context.get_all_stt_providers()[idx2 - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.SPEECH_TO_TEXT,
                umo=umo,
            )
            event.set_result(
                MessageEventResult().message(f"✅ Successfully switched to {id_}.")
            )
        elif isinstance(idx, int):
            if idx > len(self.context.get_all_providers()) or idx < 1:
                event.set_result(
                    MessageEventResult().message("❌ Invalid provider index.")
                )
                return
            provider = self.context.get_all_providers()[idx - 1]
            id_ = provider.meta().id
            await self.context.provider_manager.set_provider(
                provider_id=id_,
                provider_type=ProviderType.CHAT_COMPLETION,
                umo=umo,
            )
            event.set_result(
                MessageEventResult().message(f"✅ Successfully switched to {id_}.")
            )
        else:
            event.set_result(MessageEventResult().message("❌ Invalid parameter."))
