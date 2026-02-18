import asyncio
import math
import random
from collections.abc import AsyncGenerator

import astrbot.core.message.components as Comp
from astrbot.core import logger
from astrbot.core.message.components import BaseMessageComponent, ComponentType
from astrbot.core.message.message_event_result import MessageChain, ResultContentType
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.path_util import path_Mapping

from ..context import PipelineContext, call_event_hook
from ..stage import Stage, register_stage


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
        Comp.Poke: lambda comp: comp.id != 0 and comp.qq != 0,  # 戳一戳
        Comp.Node: lambda comp: bool(comp.content),  # 转发节点
        Comp.Nodes: lambda comp: bool(comp.nodes),  # 多个转发节点
        Comp.File: lambda comp: bool(comp.file_ or comp.url),
        Comp.WechatEmoji: lambda comp: comp.md5 is not None,  # 微信表情
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
        if self.only_llm_result and not result.is_llm_result():
            return False

        if event.get_platform_name() in [
            "qq_official",
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
        result = event.get_result()
        if result is None:
            return
        if event.get_extra("_streaming_finished", False):
            # prevent some plugin make result content type to LLM_RESULT after streaming finished, lead to send again
            return
        if result.result_content_type == ResultContentType.STREAMING_FINISH:
            event.set_extra("_streaming_finished", True)
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
            await event.send_streaming(result.async_stream, realtime_segmenting)
            return
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
                    await asyncio.sleep(i)
                    try:
                        if comp.type in need_separately:
                            await event.send(MessageChain([comp]))
                        else:
                            await event.send(MessageChain([*header_comps, comp]))
                            header_comps.clear()
                    except Exception as e:
                        logger.error(
                            f"发送消息链失败: chain = {MessageChain([comp])}, error = {e}",
                            exc_info=True,
                        )
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
                    chain = MessageChain([comp])
                    try:
                        await event.send(chain)
                    except Exception as e:
                        logger.error(
                            f"发送消息链失败: chain = {chain}, error = {e}",
                            exc_info=True,
                        )
                chain = MessageChain(result.chain)
                if result.chain and len(result.chain) > 0:
                    try:
                        await event.send(chain)
                    except Exception as e:
                        logger.error(
                            f"发送消息链失败: chain = {chain}, error = {e}",
                            exc_info=True,
                        )

        if await call_event_hook(event, EventType.OnAfterMessageSentEvent):
            return

        event.clear_result()
