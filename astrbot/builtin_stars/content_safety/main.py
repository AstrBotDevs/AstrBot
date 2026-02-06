from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.star.node_star import NodeResult, NodeStar

from .strategies import StrategySelector

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class ContentSafetyStar(NodeStar):
    """Content safety checks for input/output text."""

    def __init__(self, context, config: dict | None = None):
        super().__init__(context, config)
        self._strategy_selector: StrategySelector | None = None
        self._config_signature: str | None = None

    def _ensure_strategy_selector(self, event: AstrMessageEvent) -> None:
        config = event.node_config or {}
        signature = hashlib.sha256(
            json.dumps(config, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        if signature != self._config_signature:
            self._strategy_selector = StrategySelector(config)
            self._config_signature = signature

    def _check_content(self, text: str) -> tuple[bool, str]:
        if not self._strategy_selector:
            return True, ""
        return self._strategy_selector.check(text)

    @staticmethod
    def _block_event(event: AstrMessageEvent, reason: str) -> NodeResult:
        if event.is_at_or_wake_command:
            event.set_result(
                MessageEventResult().message(
                    "你的消息或者大模型的响应中包含不适当的内容，已被屏蔽。"
                )
            )
        event.stop_event()
        logger.info(f"内容安全检查不通过，原因：{reason}")
        return NodeResult.STOP

    async def process(self, event: AstrMessageEvent) -> NodeResult:
        self._ensure_strategy_selector(event)

        # 检查输入
        text = event.get_message_str()
        if text:
            ok, info = self._check_content(text)
            if not ok:
                return self._block_event(event, info)

        # 检查输出（如果是流式消息先收集）
        result = event.get_result()
        if result and result.result_content_type == ResultContentType.STREAMING_RESULT:
            await self.collect_stream(event)
            result = event.get_result()

        if result and result.chain:
            output_parts = []
            for comp in result.chain:
                if isinstance(comp, Plain):
                    output_parts.append(comp.text)
            output_text = "".join(output_parts)

            if output_text:
                ok, info = self._check_content(output_text)
                if not ok:
                    return self._block_event(event, info)

        # Write output to ctx for downstream nodes (pass through the result)
        if result:
            event.set_node_output(result)

        return NodeResult.CONTINUE
