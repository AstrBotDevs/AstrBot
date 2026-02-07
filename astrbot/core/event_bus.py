"""事件总线 - 消息队列消费 + Pipeline 分发"""

from __future__ import annotations

import asyncio
from asyncio import Queue
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.pipeline.engine.wait_registry import build_wait_key, wait_registry
from astrbot.core.star.modality import extract_modalities

if TYPE_CHECKING:
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
    from astrbot.core.pipeline.engine.executor import PipelineExecutor
    from astrbot.core.pipeline.engine.router import ChainRouter
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class EventBus:
    def __init__(
        self,
        event_queue: Queue,
        pipeline_executor_mapping: dict[str, PipelineExecutor],
        astrbot_config_mgr: AstrBotConfigManager,
        chain_router: ChainRouter,
    ) -> None:
        self.event_queue = event_queue
        self.pipeline_executor_mapping = pipeline_executor_mapping
        self.astrbot_config_mgr = astrbot_config_mgr
        self.chain_router = chain_router

    async def dispatch(self) -> None:
        """消息队列消费循环"""
        while True:
            event: AstrMessageEvent = await self.event_queue.get()

            wait_state = await wait_registry.pop(build_wait_key(event))
            if wait_state is not None:
                event.message_str = event.message_str.strip()

                current_chain_config = self.chain_router.get_by_chain_id(
                    wait_state.chain_config.chain_id
                )

                if not wait_state.is_valid(current_chain_config):
                    logger.debug(
                        f"WaitState invalidated for {event.unified_msg_origin}, "
                        "falling back to normal routing."
                    )
                    modality = extract_modalities(event.get_messages())
                    routed_chain_config = self.chain_router.route(
                        event.unified_msg_origin,
                        modality,
                        event.message_str,
                    )
                    if routed_chain_config is None:
                        logger.debug(
                            f"No chain matched for {event.unified_msg_origin}, "
                            "event ignored."
                        )
                        continue

                    if not self._dispatch_with_chain_config(
                        event,
                        routed_chain_config,
                    ):
                        continue
                    continue

                event.chain_config = wait_state.chain_config
                event.set_extra("_resume_node_uuid", wait_state.node_uuid)

                if not self._dispatch_with_chain_config(event, wait_state.chain_config):
                    continue
                continue

            event.message_str = event.message_str.strip()
            modality = extract_modalities(event.get_messages())
            chain_config = self.chain_router.route(
                event.unified_msg_origin,
                modality,
                event.message_str,
            )
            if chain_config is None:
                logger.debug(
                    f"No chain matched for {event.unified_msg_origin}, event ignored."
                )
                continue

            event.chain_config = chain_config
            if not self._dispatch_with_chain_config(event, chain_config):
                continue

    @staticmethod
    def _print_event(event: AstrMessageEvent, conf_name: str) -> None:
        """记录事件信息"""
        sender = event.get_sender_name()
        sender_id = event.get_sender_id()
        platform_id = event.get_platform_id()
        platform_name = event.get_platform_name()
        outline = event.get_message_outline()

        if sender:
            logger.info(
                f"[{conf_name}] [{platform_id}({platform_name})] "
                f"{sender}/{sender_id}: {outline}"
            )
        else:
            logger.info(
                f"[{conf_name}] [{platform_id}({platform_name})] {sender_id}: {outline}"
            )

    def _dispatch_with_chain_config(
        self,
        event: AstrMessageEvent,
        chain_config,
    ) -> bool:
        event.chain_config = chain_config
        config_id = chain_config.config_id or "default"
        self.astrbot_config_mgr.set_runtime_config_id(
            event.unified_msg_origin,
            config_id,
        )
        config_info = self.astrbot_config_mgr.get_config_info_by_id(config_id)
        self._print_event(event, config_info["name"])

        executor = self.pipeline_executor_mapping.get(config_id)
        if executor is None:
            executor = self.pipeline_executor_mapping.get("default")
        if executor is None:
            logger.error(
                f"PipelineExecutor not found for config_id: {config_id}, event ignored."
            )
            return False

        # 分发到 Pipeline（fire-and-forget）
        asyncio.create_task(executor.execute(event))
        return True
