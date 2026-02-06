from __future__ import annotations

import random
import traceback
from typing import TYPE_CHECKING

from astrbot.core import file_token_service, logger, sp
from astrbot.core.message.components import Plain, Record
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class TTSStar(NodeStar):
    """Text-to-speech."""

    def __init__(self, context, config: dict | None = None):
        super().__init__(context, config)
        self.callback_api_base = None

    @staticmethod
    async def _session_tts_enabled(umo: str) -> bool:
        session_config = await sp.session_get(
            umo,
            "session_service_config",
            default={},
        )
        session_config = session_config or {}
        tts_enabled = session_config.get("tts_enabled")
        if tts_enabled is None:
            return True
        return bool(tts_enabled)

    async def node_initialize(self) -> None:
        config = self.context.get_config()
        self.callback_api_base = config.get("callback_api_base", "")

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        config = self.context.get_config(umo=event.unified_msg_origin)
        if not config.get("provider_tts_settings", {}).get("enable", False):
            return NodeResult.SKIP
        if not await self._session_tts_enabled(event.unified_msg_origin):
            return NodeResult.SKIP

        node_config = event.node_config or {}
        use_file_service = node_config.get("use_file_service", False)
        dual_output = node_config.get("dual_output", False)
        trigger_probability = node_config.get("trigger_probability", 1.0)
        try:
            trigger_probability = max(0.0, min(float(trigger_probability), 1.0))
        except (TypeError, ValueError):
            trigger_probability = 1.0

        result = event.get_result()
        if not result:
            return NodeResult.SKIP

        # 先收集流式内容（如果有）
        await self.collect_stream(event)

        if not result.chain:
            return NodeResult.SKIP

        if not result.is_llm_result():
            return NodeResult.SKIP

        if random.random() > trigger_probability:
            return NodeResult.SKIP

        tts_provider = self.get_tts_provider(event)
        if not tts_provider:
            logger.warning(f"会话 {event.unified_msg_origin} 未配置文本转语音模型。")
            return NodeResult.SKIP

        new_chain = []

        for comp in result.chain:
            if isinstance(comp, Plain) and len(comp.text) > 1:
                try:
                    logger.info(f"TTS 请求: {comp.text}")
                    audio_path = await tts_provider.get_audio(comp.text)
                    logger.info(f"TTS 结果: {audio_path}")

                    if not audio_path:
                        logger.error(f"TTS 音频文件未找到: {comp.text}")
                        new_chain.append(comp)
                        continue

                    url = None
                    if use_file_service and self.callback_api_base:
                        token = await file_token_service.register_file(audio_path)
                        url = f"{self.callback_api_base}/api/file/{token}"
                        logger.debug(f"已注册：{url}")

                    new_chain.append(
                        Record(
                            file=url or audio_path,
                            url=url or audio_path,
                        )
                    )

                    if dual_output:
                        new_chain.append(comp)

                except Exception:
                    logger.error(traceback.format_exc())
                    logger.error("TTS 失败，使用文本发送。")
                    new_chain.append(comp)
            else:
                new_chain.append(comp)

        result.chain = new_chain

        event.set_node_output(result)

        return NodeResult.CONTINUE
