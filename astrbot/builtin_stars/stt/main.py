from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.message.components import Plain, Record
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class STTStar(NodeStar):
    """Speech-to-text."""

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        config = self.context.get_config(umo=event.unified_msg_origin)
        stt_settings = config.get("provider_stt_settings", {})
        if not stt_settings.get("enable", False):
            return NodeResult.SKIP

        stt_provider = self.get_stt_provider(event)
        if not stt_provider:
            logger.warning(f"会话 {event.unified_msg_origin} 未配置语音转文本模型。")
            return NodeResult.SKIP

        message_chain = event.get_messages()
        transcribed_texts = []

        for idx, component in enumerate(message_chain):
            if isinstance(component, Record) and component.url:
                path = component.url.removeprefix("file://")
                retry = 5
                for i in range(retry):
                    try:
                        result = await stt_provider.get_text(audio_url=path)
                        if result:
                            logger.info("语音转文本结果: " + result)
                            message_chain[idx] = Plain(result)
                            event.message_str += result
                            event.message_obj.message_str += result
                            transcribed_texts.append(result)
                        break
                    except FileNotFoundError as e:
                        logger.warning(f"STT 重试中: {i + 1}/{retry}: {e}")
                        await asyncio.sleep(0.5)
                        continue
                    except Exception as e:
                        logger.error(f"语音转文本失败: {e}")
                        break

        if transcribed_texts:
            event.set_node_output("\n".join(transcribed_texts))

        return NodeResult.CONTINUE
