"""事件总线 - 消息队列消费 + Pipeline 分发

架构:
    Platform Adapter → Queue.put_nowait(event)
                            ↓
    EventBus.dispatch() → 路由到对应 PipelineExecutor
                            ↓
                       PipelineExecutor.execute()
"""

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
    """事件总线 - 消息队列消费 + Pipeline 分发"""

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
                event.chain_config = wait_state.chain_config
                event.set_extra("_resume_node", wait_state.node_name)
                event.set_extra("_resume_node_uuid", wait_state.node_uuid)
                event.set_extra("_resume_from_wait", True)
                config_id = wait_state.config_id or "default"
                self.astrbot_config_mgr.set_runtime_conf_id(
                    event.unified_msg_origin,
                    config_id,
                )
                conf_info = self.astrbot_config_mgr.get_conf_info_by_id(config_id)
                self._print_event(event, conf_info["name"])
                executor = self.pipeline_executor_mapping.get(config_id)
                if executor is None:
                    executor = self.pipeline_executor_mapping.get("default")
                if executor is None:
                    logger.error(
                        "PipelineExecutor not found for config_id: "
                        f"{config_id}, event ignored."
                    )
                    continue
                asyncio.create_task(executor.execute(event))
                continue

            # 轻量路由：使用 UMO + 原始文本 + 原始模态，决定链与 config_id
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
            config_id = chain_config.config_id or "default"
            self.astrbot_config_mgr.set_runtime_conf_id(
                event.unified_msg_origin,
                config_id,
            )
            conf_info = self.astrbot_config_mgr.get_conf_info_by_id(config_id)

            self._print_event(event, conf_info["name"])

            # 获取对应的 PipelineExecutor
            executor = self.pipeline_executor_mapping.get(config_id)
            if executor is None:
                executor = self.pipeline_executor_mapping.get("default")

            if executor is None:
                logger.error(
                    f"PipelineExecutor not found for config_id: {config_id}, event ignored."
                )
                continue

            # 分发到 Pipeline（fire-and-forget）
            asyncio.create_task(executor.execute(event))

    def _print_event(self, event: AstrMessageEvent, conf_name: str) -> None:
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
