import asyncio
import math
import random
from collections.abc import AsyncGenerator

import astrbot.core.message.components as Comp
from astrbot import logger
from astrbot.core.assistant_history import make_projection
from astrbot.core.message.components import BaseMessageComponent, ComponentType
from astrbot.core.message.message_event_result import MessageChain, ResultContentType
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import (
    DeliveryAttempt,
    DeliveryReceipt,
    PlatformSendResult,
)
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.path_util import path_Mapping

from ..context import PipelineContext, call_event_hook
from ..stage import Stage


class RespondStage(Stage):
    # 组件类型到其非空判断函数的映射
    _component_validators = {
        Comp.Plain: lambda comp: bool(
            comp.text and comp.text.strip(),
        ),  # 纯文本消息需要strip
        Comp.Face: lambda comp: comp.id is not None,  # QQ表情
        Comp.MFace: lambda comp: bool(comp.emoji_id and comp.key and comp.summary),
        Comp.Anonymous: lambda _: True,
        Comp.Record: lambda comp: bool(comp.file),  # 语音
        Comp.Video: lambda comp: bool(comp.file),  # 视频
        Comp.At: lambda comp: bool(comp.qq) or bool(comp.name),  # @
        Comp.Image: lambda comp: bool(comp.file),  # 图片
        Comp.Reply: lambda comp: bool(comp.id) and comp.sender_id is not None,  # 回复
        Comp.Poke: lambda comp: comp.id not in (None, "", 0, "0"),  # 戳一戳
        Comp.Node: lambda comp: bool(comp.content),  # 转发节点
        Comp.Nodes: lambda comp: bool(comp.nodes),  # 多个转发节点
        Comp.File: lambda comp: bool(comp.file_ or comp.url),
        Comp.Json: lambda comp: bool(comp.data),  # Json 卡片
        Comp.Xml: lambda comp: bool(comp.data),  # Xml 卡片
        Comp.Share: lambda comp: bool(comp.url) or bool(comp.title),
        Comp.Markdown: lambda comp: bool(comp.content),
        Comp.MiniApp: lambda comp: bool(comp.data),
        Comp.OnlineFile: lambda comp: bool(
            comp.msg_id and comp.element_id and comp.file_name
        ),
        Comp.Music: lambda comp: (
            (comp.id and comp.sub_type and comp.sub_type != "custom")
            or (comp.sub_type == "custom" and comp.url and comp.audio and comp.title)
        ),  # 音乐分享
        Comp.FlashTransfer: lambda comp: bool(comp.file_set_id),
        Comp.Forward: lambda comp: bool(comp.id),  # 合并转发
        Comp.Location: lambda comp: bool(
            comp.lat is not None and comp.lon is not None
        ),  # 位置
        Comp.Contact: lambda comp: bool(comp.sub_type and comp.id),  # 推荐好友 or 群
        Comp.Shake: lambda _: True,  # 窗口抖动（戳一戳）
        Comp.Dice: lambda _: True,  # 掷骰子魔法表情
        Comp.RPS: lambda _: True,  # 猜拳魔法表情
        Comp.Unknown: lambda comp: bool(comp.text and comp.text.strip()),
    }

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        self.platform_settings: dict = self.config.get("platform_settings", {})

        self.reply_with_mention = ctx.astrbot_config["platform_settings"][
            "reply_with_mention"
        ]
        self.reply_with_quote = ctx.astrbot_config["platform_settings"][
            "reply_with_quote"
        ]

        # 分段回复
        self.enable_seg: bool = ctx.astrbot_config["platform_settings"][
            "segmented_reply"
        ]["enable"]
        self.only_llm_result = ctx.astrbot_config["platform_settings"][
            "segmented_reply"
        ]["only_llm_result"]

        self.interval_method = ctx.astrbot_config["platform_settings"][
            "segmented_reply"
        ]["interval_method"]
        self.log_base = float(
            ctx.astrbot_config["platform_settings"]["segmented_reply"]["log_base"],
        )
        self.interval = [1.5, 3.5]
        if self.enable_seg:
            interval_str: str = ctx.astrbot_config["platform_settings"][
                "segmented_reply"
            ]["interval"]
            interval_str_ls = interval_str.replace(" ", "").split(",")
            try:
                self.interval = [float(t) for t in interval_str_ls]
            except Exception as e:
                logger.error(f"解析分段回复的间隔时间失败。{e}")
            logger.info(f"分段回复间隔时间：{self.interval}")

    async def _word_cnt(self, text: str) -> int:
        """分段回复 统计字数"""
        if all(ord(c) < 128 for c in text):
            word_count = len(text.split())
        else:
            word_count = len([c for c in text if c.isalnum()])
        return word_count

    async def _calc_comp_interval(self, comp: BaseMessageComponent) -> float:
        """分段回复 计算间隔时间"""
        if self.interval_method == "log":
            if isinstance(comp, Comp.Plain):
                wc = await self._word_cnt(comp.text)
                i = math.log(wc + 1, self.log_base)
                return random.uniform(i, i + 0.5)
            return random.uniform(1, 1.75)
        # random
        return random.uniform(self.interval[0], self.interval[1])

    async def _is_empty_message_chain(self, chain: list[BaseMessageComponent]) -> bool:
        """检查消息链是否为空

        Args:
            chain (list[BaseMessageComponent]): 包含消息对象的列表

        """
        if not chain:
            return True

        for comp in chain:
            comp_type = type(comp)

            # 检查组件类型是否在字典中
            if comp_type in self._component_validators:
                if self._component_validators[comp_type](comp):
                    return False

        # 如果所有组件都为空
        return True

    async def _stop_typing_before_send(self, event: AstrMessageEvent) -> None:
        """Best-effort stop_typing right before the actual reply send."""
        try:
            await event.stop_typing()
        except Exception:
            logger.warning("stop_typing failed before send", exc_info=True)

    def _log_send_result(
        self,
        result,
        *,
        chain: MessageChain | None = None,
    ) -> None:
        if result is None or getattr(result, "success", True):
            return
        logger.error(
            "发送消息链失败: target=%s chain=%s error=%s",
            getattr(result, "target", ""),
            chain,
            getattr(result, "error_message", "unknown error"),
        )

    def is_seg_reply_required(self, event: AstrMessageEvent) -> bool:
        """检查是否需要分段回复"""
        if not self.enable_seg:
            return False

        if (result := event.get_result()) is None:
            return False
        if self.only_llm_result and not result.is_model_result():
            return False

        if event.get_platform_name() in [
            "qq_official_webhook",
            "weixin_official_account",
            "dingtalk",
        ]:
            return False

        return True

    def _extract_comp(
        self,
        raw_chain: list[BaseMessageComponent],
        extract_types: set[ComponentType],
        modify_raw_chain: bool = True,
    ):
        extracted = []
        if modify_raw_chain:
            remaining = []
            for comp in raw_chain:
                if comp.type in extract_types:
                    extracted.append(comp)
                else:
                    remaining.append(comp)
            raw_chain[:] = remaining
        else:
            extracted = [comp for comp in raw_chain if comp.type in extract_types]

        return extracted

    def _chain_semantic_text(self, chain: MessageChain) -> str:
        """Return submitted user-visible text without transport wrappers."""
        text_parts: list[str] = []
        for component in chain.chain:
            if isinstance(component, (Comp.At, Comp.AtAll, Comp.Reply)):
                continue
            if isinstance(component, (Comp.Plain, Comp.Unknown)) and component.text:
                text_parts.append(component.text)
            elif isinstance(component, Comp.Markdown) and component.content:
                text_parts.append(component.content)
        return "".join(text_parts)

    def _receipt_for_attempts(
        self,
        event: AstrMessageEvent,
        attempts: list[DeliveryAttempt],
    ) -> DeliveryReceipt:
        return DeliveryReceipt.aggregate(
            attempts,
            platform_id=event.get_platform_id(),
            target=getattr(getattr(event, "route_identity", None), "target_id", ""),
        )

    async def _send_attempt(
        self,
        event: AstrMessageEvent,
        chain: MessageChain,
    ) -> DeliveryAttempt:
        """Submit one chain without conflating exceptions with acceptance."""
        try:
            await self._stop_typing_before_send(event)
            from astrbot.core.group_sender_concurrency import serialize_group_outbound

            gate = getattr(self.ctx.execution_context, "group_outbound_gate", None)
            async with serialize_group_outbound(event.unified_msg_origin, gate):
                result = await event.send(chain)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("发送消息链异常: %s", safe_error("", exc))
            return DeliveryAttempt(
                status="unknown",
                semantic_text=self._chain_semantic_text(chain),
                error_summary="platform submission outcome unknown",
            )

        if not isinstance(result, PlatformSendResult):
            logger.warning("平台未返回发送回执，发送结果未知。")
            return DeliveryAttempt(
                status="unknown",
                semantic_text=self._chain_semantic_text(chain),
                error_summary="platform did not return an acceptance receipt",
            )
        self._log_send_result(result, chain=chain)
        attempts = result.to_delivery_attempts(
            semantic_text=self._chain_semantic_text(chain),
        )
        if len(attempts) != 1:
            logger.warning("普通发送返回了多个投递回执，按不确定结果处理。")
            return DeliveryAttempt(
                status="unknown",
                semantic_text=self._chain_semantic_text(chain),
                error_summary="platform returned an unexpected multi-part receipt",
            )
        attempt = attempts[0]
        if attempt.status == "accepted":
            logger.info(
                "Platform message accepted",
                extra={
                    "category": "platform_send",
                    "privacy": "internal",
                    "platform": event.get_platform_id(),
                    "conversation_id": getattr(event, "unified_msg_origin", ""),
                    "sender_id": str(event.get_sender_id()),
                    "summary": "Platform message accepted",
                },
            )
        return attempt

    async def _send_streaming_result(
        self, event: AstrMessageEvent, result
    ) -> DeliveryReceipt:
        """Deliver a streaming result using the platform's configured strategy."""
        if result.async_stream is None:
            logger.warning("async_stream 为空，跳过发送。")
            return DeliveryReceipt.skipped(platform_id=event.get_platform_id())
        realtime_segmenting = (
            self.config.get("provider_settings", {}).get(
                "unsupported_streaming_strategy",
                "realtime_segmenting",
            )
            == "realtime_segmenting"
        )
        logger.info("应用流式输出(%s)", event.get_platform_id())
        streamed_text: list[str] = []

        async def tracked_stream():
            async for chain in result.async_stream:
                if isinstance(chain, MessageChain) and chain.type not in {
                    "reasoning",
                    "break",
                    "tool_call",
                }:
                    streamed_text.append(self._chain_semantic_text(chain))
                yield chain

        try:
            await self._stop_typing_before_send(event)
            send_result = await event.send_streaming(
                tracked_stream(), realtime_segmenting
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("流式消息发送异常: %s", safe_error("", exc))
            return self._receipt_for_attempts(
                event,
                [
                    DeliveryAttempt(
                        status="unknown",
                        semantic_text="".join(streamed_text),
                        error_summary="platform streaming outcome unknown",
                    )
                ],
            )
        if not isinstance(send_result, PlatformSendResult):
            return self._receipt_for_attempts(
                event,
                [
                    DeliveryAttempt(
                        status="unknown",
                        semantic_text="".join(streamed_text),
                        error_summary="platform did not return an acceptance receipt",
                    )
                ],
            )
        self._log_send_result(send_result)
        logger.info(
            "Platform streaming message accepted",
            extra={
                "category": "platform_send",
                "privacy": "internal",
                "platform": event.get_platform_id(),
                "conversation_id": getattr(event, "unified_msg_origin", ""),
                "sender_id": str(event.get_sender_id()),
                "summary": "Platform streaming message accepted",
            },
        )
        return self._receipt_for_attempts(
            event,
            list(
                send_result.to_delivery_attempts(
                    semantic_text="".join(streamed_text),
                ),
            ),
        )

    async def _prepare_result_chain(self, result) -> bool:
        """Map files and remove empty content before ordinary delivery."""
        if mappings := self.platform_settings.get("path_mapping", []):
            for idx, component in enumerate(result.chain):
                if isinstance(component, Comp.File) and component.file:
                    component.file = path_Mapping(mappings, component.file)
                    result.chain[idx] = component
        try:
            if await self._is_empty_message_chain(result.chain):
                logger.info("消息为空，跳过发送阶段")
                return False
        except Exception as exc:
            logger.warning("空内容检查异常: %s", exc)
        result.chain = [
            comp
            for comp in result.chain
            if not (
                isinstance(comp, Comp.Plain)
                and (not comp.text or not comp.text.strip())
            )
        ]
        return True

    async def _send_segmented_result(
        self, event: AstrMessageEvent, result
    ) -> DeliveryReceipt:
        """Deliver a result component by component, retaining reply headers once."""
        header_comps = self._extract_comp(
            result.chain,
            {ComponentType.Reply, ComponentType.At},
            modify_raw_chain=True,
        )
        if not result.chain:
            logger.warning(
                "实际消息链为空, 跳过发送阶段。header_chain: %s, actual_chain: %s",
                header_comps,
                result.chain,
            )
            return DeliveryReceipt.skipped(platform_id=event.get_platform_id())
        attempts: list[DeliveryAttempt] = []
        for comp in result.chain:
            await asyncio.sleep(await self._calc_comp_interval(comp))
            if comp.type == ComponentType.Record:
                chain = result.derive([comp])
            else:
                chain = result.derive([*header_comps, comp])
                header_comps.clear()
            attempts.append(await self._send_attempt(event, chain))
        return self._receipt_for_attempts(event, attempts)

    async def _send_standard_result(
        self, event: AstrMessageEvent, result
    ) -> DeliveryReceipt:
        """Deliver records separately, then the remaining ordinary message chain."""
        if all(
            comp.type in {ComponentType.Reply, ComponentType.At}
            for comp in result.chain
        ):
            logger.warning(
                "消息链全为 Reply 和 At 消息段, 跳过发送阶段。chain: %s",
                result.chain,
            )
            return DeliveryReceipt.skipped(platform_id=event.get_platform_id())
        attempts: list[DeliveryAttempt] = []
        separate_components = self._extract_comp(
            result.chain,
            {ComponentType.Record},
            modify_raw_chain=True,
        )
        for comp in separate_components:
            chain = result.derive([comp])
            attempts.append(await self._send_attempt(event, chain))
        if not result.chain:
            return self._receipt_for_attempts(event, attempts)
        chain = result.derive(result.chain)
        attempts.append(await self._send_attempt(event, chain))
        return self._receipt_for_attempts(event, attempts)

    def _store_delivery_receipt(
        self,
        event: AstrMessageEvent,
        receipt: DeliveryReceipt,
    ) -> None:
        """Expose immutable receipt/projection data to Agent finalization only."""
        event.set_extra("delivery_receipt", receipt)
        event.set_extra("history_projection", make_projection(receipt))

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None]:
        result = event.get_result()
        if result is None:
            return
        Comp.bind_file_service(
            result.chain,
            str(self.ctx.astrbot_config.get("callback_api_base", "") or ""),
            self.ctx.file_token_service,
        )
        if event.get_extra("_streaming_finished", False):
            # prevent some plugin make result content type to LLM_RESULT after streaming finished, lead to send again
            return
        if result.result_content_type == ResultContentType.STREAMING_FINISH:
            event.set_extra("_streaming_finished", True)
            return
        sent_plain_texts = event.get_extra(
            "_send_message_to_user_current_session_plain_texts",
            [],
        )
        result_plain_text = result.get_plain_text().strip()
        if (
            result_plain_text
            and isinstance(sent_plain_texts, list)
            and result_plain_text in sent_plain_texts
            and all(
                comp.type
                in {
                    ComponentType.Plain,
                    ComponentType.Reply,
                    ComponentType.At,
                }
                for comp in result.chain
            )
        ):
            logger.info(
                "send_message_to_user already delivered the same text in this session, skip respond stage to avoid duplicate reply.",
            )
            self._store_delivery_receipt(
                event,
                DeliveryReceipt.skipped(platform_id=event.get_platform_id()),
            )
            return

        logger.info(
            f"Prepare to send - {event.get_sender_name()}/{event.get_sender_id()}: {event._outline_chain(result.chain)}",
        )

        if result.result_content_type == ResultContentType.STREAMING_RESULT:
            self._store_delivery_receipt(
                event,
                await self._send_streaming_result(event, result),
            )
            return
        receipt = DeliveryReceipt.skipped(platform_id=event.get_platform_id())
        if len(result.chain) > 0:
            if not await self._prepare_result_chain(result):
                self._store_delivery_receipt(event, receipt)
                return

            if self.is_seg_reply_required(event):
                receipt = await self._send_segmented_result(event, result)
            else:
                receipt = await self._send_standard_result(event, result)
        self._store_delivery_receipt(event, receipt)
        await self.ctx.execution_context.persist_accepted_group_response(event, receipt)

        if await call_event_hook(
            event,
            EventType.OnAfterMessageSentEvent,
            handler_registry=self.ctx.handlers,
            plugin_registry=self.ctx.plugins,
        ):
            return

        event.clear_result()
