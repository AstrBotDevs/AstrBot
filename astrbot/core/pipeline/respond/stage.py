import asyncio
import math
import random
from collections.abc import AsyncGenerator

import astrbot.core.message.components as Comp
from astrbot.core import logger
from astrbot.core.agent.stop_policy import (
    AGENT_OUTPUT_DELIVERY_CONFIRMED_KEY,
    AgentOutputStopped,
    event_requests_agent_stop,
)
from astrbot.core.message.components import BaseMessageComponent, ComponentType
from astrbot.core.message.message_event_result import MessageChain, ResultContentType
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.path_util import path_Mapping

from ..context import PipelineContext, call_event_hook
from ..stage import Stage, register_stage


def _discard_result_if_stopped(event: AstrMessageEvent) -> bool:
    if not event_requests_agent_stop(event):
        return False
    event.clear_result()
    return True


@register_stage
class RespondStage(Stage):
    # 组件类型到其非空判断函数的映射
    _component_validators = {
        Comp.Plain: lambda comp: bool(
            comp.text and comp.text.strip(),
        ),  # 纯文本消息需要strip
        Comp.Face: lambda comp: comp.id is not None,  # QQ表情
        Comp.Record: lambda comp: bool(comp.file),  # 语音
        Comp.Video: lambda comp: bool(comp.file),  # 视频
        Comp.At: lambda comp: bool(comp.qq) or bool(comp.name),  # @
        Comp.Image: lambda comp: bool(comp.file),  # 图片
        Comp.Reply: lambda comp: bool(comp.id) and comp.sender_id is not None,  # 回复
        Comp.Poke: lambda comp: comp.target_id() is not None,  # 戳一戳
        Comp.Node: lambda comp: bool(comp.content),  # 转发节点
        Comp.Nodes: lambda comp: bool(comp.nodes),  # 多个转发节点
        Comp.File: lambda comp: bool(comp.file_ or comp.url),
        Comp.Json: lambda comp: bool(comp.data),  # Json 卡片
        Comp.Share: lambda comp: bool(comp.url) or bool(comp.title),
        Comp.Music: lambda comp: (
            (comp.id and comp._type and comp._type != "custom")
            or (comp._type == "custom" and comp.url and comp.audio and comp.title)
        ),  # 音乐分享
        Comp.Forward: lambda comp: bool(comp.id),  # 合并转发
        Comp.Location: lambda comp: bool(
            comp.lat is not None and comp.lon is not None
        ),  # 位置
        Comp.Contact: lambda comp: bool(comp._type and comp.id),  # 推荐好友 or 群
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
            except BaseException as e:
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

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None, None]:
        if _discard_result_if_stopped(event):
            return
        result = event.get_result()
        if result is None:
            return
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
            event.set_extra(AGENT_OUTPUT_DELIVERY_CONFIRMED_KEY, True)
            return

        logger.info(
            f"Prepare to send - {event.get_sender_name()}/{event.get_sender_id()}: {event._outline_chain(result.chain)}",
        )

        if result.result_content_type == ResultContentType.STREAMING_RESULT:
            if result.async_stream is None:
                logger.warning("async_stream 为空，跳过发送。")
                return
            # 流式结果直接交付平台适配器处理
            realtime_segmenting = (
                self.config.get("provider_settings", {}).get(
                    "unsupported_streaming_strategy",
                    "realtime_segmenting",
                )
                == "realtime_segmenting"
            )
            logger.info(f"应用流式输出({event.get_platform_id()})")
            source_stream = result.async_stream
            source_exhausted = False
            source_has_payload = False
            stream_delivery_succeeded = False

            async def _guarded_stream():
                nonlocal source_exhausted, source_has_payload
                async for chain in source_stream:
                    if event_requests_agent_stop(event):
                        raise AgentOutputStopped
                    if any(
                        not isinstance(component, Comp.Plain)
                        or bool(component.text.strip())
                        for component in chain.chain
                    ):
                        source_has_payload = True
                    yield chain
                    if event_requests_agent_stop(event):
                        raise AgentOutputStopped
                if event_requests_agent_stop(event):
                    raise AgentOutputStopped
                source_exhausted = True

            guarded_stream = _guarded_stream()
            try:
                await event.send_streaming(guarded_stream, realtime_segmenting)
            except AgentOutputStopped:
                pass
            except Exception as e:
                logger.error("发送流式消息失败: %s", e, exc_info=True)
            else:
                if source_exhausted and source_has_payload:
                    stream_delivery_succeeded = True
                    event.set_extra(AGENT_OUTPUT_DELIVERY_CONFIRMED_KEY, True)
            finally:
                await guarded_stream.aclose()
                close_source = getattr(source_stream, "aclose", None)
                if close_source is not None:
                    await close_source()
            if not stream_delivery_succeeded:
                event.clear_result()
            _discard_result_if_stopped(event)
            return

        sent_any = False
        send_failed = False
        if len(result.chain) > 0:
            # 检查路径映射
            if mappings := self.platform_settings.get("path_mapping", []):
                for idx, component in enumerate(result.chain):
                    if isinstance(component, Comp.File) and component.file:
                        # 支持 File 消息段的路径映射。
                        component.file = path_Mapping(mappings, component.file)
                        result.chain[idx] = component

            # 检查消息链是否为空
            try:
                if await self._is_empty_message_chain(result.chain):
                    logger.info("消息为空，跳过发送阶段")
                    return
            except Exception as e:
                logger.warning(f"空内容检查异常: {e}")

            # 将 Plain 为空的消息段移除
            result.chain = [
                comp
                for comp in result.chain
                if not (
                    isinstance(comp, Comp.Plain)
                    and (not comp.text or not comp.text.strip())
                )
            ]

            # 发送消息链
            # Record 需要强制单独发送
            need_separately = {ComponentType.Record}
            if self.is_seg_reply_required(event):
                header_comps = self._extract_comp(
                    result.chain,
                    {ComponentType.Reply, ComponentType.At},
                    modify_raw_chain=True,
                )
                if not result.chain or len(result.chain) == 0:
                    # may fix #2670
                    logger.warning(
                        f"实际消息链为空, 跳过发送阶段。header_chain: {header_comps}, actual_chain: {result.chain}",
                    )
                    return
                for comp in result.chain:
                    i = await self._calc_comp_interval(comp)
                    if _discard_result_if_stopped(event):
                        return
                    await asyncio.sleep(i)
                    if _discard_result_if_stopped(event):
                        return
                    try:
                        if comp.type in need_separately:
                            await event.send(result.derive([comp]))
                        else:
                            await event.send(result.derive([*header_comps, comp]))
                            header_comps.clear()
                    except AgentOutputStopped:
                        event.clear_result()
                        return
                    except Exception as e:
                        send_failed = True
                        logger.error(
                            f"发送消息链失败: chain = {MessageChain([comp])}, error = {e}",
                            exc_info=True,
                        )
                    else:
                        sent_any = True
            else:
                if all(
                    comp.type in {ComponentType.Reply, ComponentType.At}
                    for comp in result.chain
                ):
                    # may fix #2670
                    logger.warning(
                        f"消息链全为 Reply 和 At 消息段, 跳过发送阶段。chain: {result.chain}",
                    )
                    return
                sep_comps = self._extract_comp(
                    result.chain,
                    need_separately,
                    modify_raw_chain=True,
                )
                for comp in sep_comps:
                    if _discard_result_if_stopped(event):
                        return
                    chain = result.derive([comp])
                    try:
                        await event.send(chain)
                    except AgentOutputStopped:
                        event.clear_result()
                        return
                    except Exception as e:
                        send_failed = True
                        logger.error(
                            f"发送消息链失败: chain = {chain}, error = {e}",
                            exc_info=True,
                        )
                    else:
                        sent_any = True
                chain = result.derive(result.chain)
                if result.chain and len(result.chain) > 0:
                    if _discard_result_if_stopped(event):
                        return
                    try:
                        await event.send(chain)
                    except AgentOutputStopped:
                        event.clear_result()
                        return
                    except Exception as e:
                        send_failed = True
                        logger.error(
                            f"发送消息链失败: chain = {chain}, error = {e}",
                            exc_info=True,
                        )
                    else:
                        sent_any = True

        if not sent_any or send_failed:
            event.clear_result()
            return
        event.set_extra(AGENT_OUTPUT_DELIVERY_CONFIRMED_KEY, True)
        if _discard_result_if_stopped(event):
            return
        if await call_event_hook(event, EventType.OnAfterMessageSentEvent):
            return

        event.clear_result()
