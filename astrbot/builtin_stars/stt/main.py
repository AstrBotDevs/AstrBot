from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.message.components import Plain, Record
from astrbot.core.pipeline.engine.chain_runtime_flags import (
    FEATURE_STT,
    is_chain_runtime_feature_enabled,
)
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class STTStar(NodeStar):
    """Speech-to-text."""

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        chain_id = event.chain_config.chain_id if event.chain_config else None
        if not await is_chain_runtime_feature_enabled(chain_id, FEATURE_STT):
            return NodeResult.SKIP

        stt_provider = self.get_stt_provider(event)
        if not stt_provider:
            logger.warning(
                f"Session {event.unified_msg_origin} has no STT provider configured."
            )
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
                            logger.info("STT result: " + result)
                            message_chain[idx] = Plain(result)
                            event.message_str += result
                            event.message_obj.message_str += result
                            transcribed_texts.append(result)
                        break
                    except FileNotFoundError as e:
                        logger.warning(f"STT retry {i + 1}/{retry}: {e}")
                        await asyncio.sleep(0.5)
                        continue
                    except Exception as e:
                        logger.error(f"STT failed: {e}")
                        break

        if transcribed_texts:
            event.set_node_output("\n".join(transcribed_texts))

        return NodeResult.CONTINUE
