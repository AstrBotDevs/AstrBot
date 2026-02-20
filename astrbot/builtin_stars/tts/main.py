from __future__ import annotations

import random
import traceback
from typing import TYPE_CHECKING

from astrbot.core import file_token_service, logger
from astrbot.core.message.components import Plain, Record
from astrbot.core.message.message_event_result import MessageEventResult
from astrbot.core.pipeline.engine.chain_runtime_flags import (
    FEATURE_TTS,
    is_chain_runtime_feature_enabled,
)
from astrbot.core.star.node_star import NodeResult, NodeStar

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class TTSStar(NodeStar):
    """Text-to-speech."""

    def __init__(self, context, config: dict | None = None):
        super().__init__(context, config)

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        chain_id = event.chain_config.chain_id if event.chain_config else None
        if not await is_chain_runtime_feature_enabled(chain_id, FEATURE_TTS):
            return NodeResult.SKIP

        node_config = event.node_config or {}
        chain_config_id = event.chain_config.config_id if event.chain_config else None
        runtime_cfg = self.context.get_config_by_id(chain_config_id)
        callback_api_base = runtime_cfg.get("callback_api_base", "")

        use_file_service = node_config.get("use_file_service", False)
        dual_output = node_config.get("dual_output", False)
        trigger_probability = node_config.get("trigger_probability", 1.0)
        try:
            trigger_probability = max(0.0, min(float(trigger_probability), 1.0))
        except (TypeError, ValueError):
            trigger_probability = 1.0

        upstream_output = await event.get_node_input(strategy="last")
        if not isinstance(upstream_output, MessageEventResult):
            logger.warning(
                "TTS upstream output is not MessageEventResult. type=%s",
                type(upstream_output).__name__,
            )
            return NodeResult.SKIP
        result = upstream_output
        await self.collect_stream(event, result)

        if not result.chain:
            return NodeResult.SKIP

        if not result.is_llm_result():
            return NodeResult.SKIP

        if random.random() > trigger_probability:
            return NodeResult.SKIP

        tts_provider = self.context.get_tts_provider_for_event(event)
        if not tts_provider:
            logger.warning(
                f"Session {event.unified_msg_origin} has no TTS provider configured."
            )
            return NodeResult.SKIP

        new_chain = []

        for comp in result.chain:
            if isinstance(comp, Plain) and len(comp.text) > 1:
                try:
                    logger.info(f"TTS request: {comp.text}")
                    audio_path = await tts_provider.get_audio(comp.text)
                    logger.info(f"TTS result: {audio_path}")

                    if not audio_path:
                        logger.error(f"TTS audio not found: {comp.text}")
                        new_chain.append(comp)
                        continue

                    url = None
                    if use_file_service and callback_api_base:
                        token = await file_token_service.register_file(audio_path)
                        url = f"{callback_api_base}/api/file/{token}"
                        logger.debug(f"Registered file service url: {url}")

                    new_chain.append(
                        Record(
                            file=url or audio_path,
                            url=url or audio_path,
                            text=comp.text,
                        )
                    )

                    if dual_output:
                        new_chain.append(comp)

                except Exception:
                    logger.error(traceback.format_exc())
                    logger.error("TTS failed, fallback to text output.")
                    new_chain.append(comp)
            else:
                new_chain.append(comp)

        result.chain = new_chain
        event.set_node_output(result)

        return NodeResult.CONTINUE
