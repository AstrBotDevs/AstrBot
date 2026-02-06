from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import (
    MessageChain,
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

        # 输入检查使用当前 message_str（已反映 STT/文件提取结果）。
        # get_node_input 仅包含已执行节点输出，受链路顺序影响。
        text = event.get_message_str()
        if text:
            ok, info = self._check_content(text)
            if not ok:
                return self._block_event(event, info)

        upstream_output = await event.get_node_input(strategy="last")
        output_text = ""
        if isinstance(upstream_output, MessageEventResult):
            event.set_result(upstream_output)
            if (
                upstream_output.result_content_type
                == ResultContentType.STREAMING_RESULT
            ):
                await self.collect_stream(event)
                result = upstream_output
            else:
                result = upstream_output
            if result.chain:
                output_text = "".join(
                    comp.text for comp in result.chain if isinstance(comp, Plain)
                )
        elif isinstance(upstream_output, MessageChain):
            output_text = "".join(
                comp.text for comp in upstream_output.chain if isinstance(comp, Plain)
            )
        elif isinstance(upstream_output, str):
            output_text = upstream_output
        elif upstream_output is not None:
            output_text = str(upstream_output)

        if output_text:
            ok, info = self._check_content(output_text)
            if not ok:
                return self._block_event(event, info)

        # 向下游传递上游输出
        if upstream_output is not None:
            event.set_node_output(upstream_output)

        return NodeResult.CONTINUE
