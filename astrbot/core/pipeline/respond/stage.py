import random
import asyncio
import math
import traceback
import astrbot.core.message.components as Comp
from typing import Union, AsyncGenerator
from ..stage import register_stage, Stage
from ..context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain, ResultContentType
from astrbot.core import logger
from astrbot.core.message.message_event_result import BaseMessageComponent
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from astrbot.core.star.star import star_map
from astrbot.core.utils.path_util import path_Mapping


@register_stage
class RespondStage(Stage):
    # 组件类型到其非空判断函数的映射
    _component_validators = {
        Comp.Plain: lambda comp: bool(
            comp.text and comp.text.strip()
        ),  # 纯文本消息需要strip
        Comp.Face: lambda comp: comp.id is not None,  # QQ表情
        Comp.Record: lambda comp: bool(comp.file),  # 语音
        Comp.Video: lambda comp: bool(comp.file),  # 视频
        Comp.At: lambda comp: bool(comp.qq) or bool(comp.name),  # @
        Comp.AtAll: lambda comp: True,  # @所有人
        Comp.RPS: lambda comp: True,  # 不知道是啥(未完成)
        Comp.Dice: lambda comp: True,  # 骰子(未完成)
        Comp.Shake: lambda comp: True,  # 摇一摇(未完成)
        Comp.Anonymous: lambda comp: True,  # 匿名(未完成)
        Comp.Share: lambda comp: bool(comp.url) and bool(comp.title),  # 分享
        Comp.Contact: lambda comp: True,  # 联系人(未完成)
        Comp.Location: lambda comp: bool(comp.lat and comp.lon),  # 位置
        Comp.Music: lambda comp: bool(comp._type)
        and bool(comp.url)
        and bool(comp.audio),  # 音乐
        Comp.Image: lambda comp: bool(comp.file),  # 图片
        Comp.Reply: lambda comp: bool(comp.id) and comp.sender_id is not None,  # 回复
        Comp.RedBag: lambda comp: bool(comp.title),  # 红包
        Comp.Poke: lambda comp: comp.id != 0 and comp.qq != 0,  # 戳一戳
        Comp.Forward: lambda comp: bool(comp.id and comp.id.strip()),  # 转发
        Comp.Node: lambda comp: bool(comp.name)
        and comp.uin != 0
        and bool(comp.content),  # 一个转发节点
        Comp.Nodes: lambda comp: bool(comp.nodes),  # 多个转发节点
        Comp.Xml: lambda comp: bool(comp.data and comp.data.strip()),  # XML
        Comp.Json: lambda comp: bool(comp.data),  # JSON
        Comp.CardImage: lambda comp: bool(comp.file),  # 卡片图片
        Comp.TTS: lambda comp: bool(comp.text and comp.text.strip()),  # 语音合成
        Comp.Unknown: lambda comp: bool(comp.text and comp.text.strip()),  # 未知消息
        Comp.File: lambda comp: bool(comp.file),  # 文件
        Comp.WechatEmoji: lambda comp: bool(comp.md5),  # 微信表情
    }

    async def initialize(self, ctx: PipelineContext):
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
            ctx.astrbot_config["platform_settings"]["segmented_reply"]["log_base"]
        )
        interval_str: str = ctx.astrbot_config["platform_settings"]["segmented_reply"][
            "interval"
        ]
        interval_str_ls = interval_str.replace(" ", "").split(",")
        try:
            self.interval = [float(t) for t in interval_str_ls]
        except BaseException as e:
            logger.error(f"解析分段回复的间隔时间失败。{e}")
            self.interval = [1.5, 3.5]
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
            else:
                return random.uniform(1, 1.75)
        else:
            # random
            return random.uniform(self.interval[0], self.interval[1])

    async def _is_empty_message_chain(self, chain: list[BaseMessageComponent]):
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
            else:
                logger.info(f"空内容检查: 无法识别的组件类型: {comp_type.__name__}")

        # 如果所有组件都为空
        return True

    async def process(
        self, event: AstrMessageEvent
    ) -> Union[None, AsyncGenerator[None, None]]:
        result = event.get_result()
        if result is None:
            return
        if result.result_content_type == ResultContentType.STREAMING_FINISH:
            return

        if result.result_content_type == ResultContentType.STREAMING_RESULT:
            # 流式结果直接交付平台适配器处理
            use_fallback = self.config.get("provider_settings", {}).get(
                "streaming_segmented", False
            )
            logger.info(f"应用流式输出({event.get_platform_name()})")
            await event._pre_send()
            await event.send_streaming(result.async_stream, use_fallback)
            await event._post_send()
            return
        elif len(result.chain) > 0:
            # 检查路径映射
            if mappings := self.platform_settings.get("path_mapping", []):
                for idx, component in enumerate(result.chain):
                    if isinstance(component, Comp.File) and component.file:
                        # 支持 File 消息段的路径映射。
                        component.file = path_Mapping(mappings, component.file)
                        event.get_result().chain[idx] = component

            await event._pre_send()

            # 检查消息链是否为空
            try:
                if await self._is_empty_message_chain(result.chain):
                    logger.info("消息为空，跳过发送阶段")
                    event.clear_result()
                    event.stop_event()
                    return
            except Exception as e:
                logger.warning(f"空内容检查异常: {e}")

            if self.enable_seg and (
                (self.only_llm_result and result.is_llm_result())
                or not self.only_llm_result
            ):
                decorated_comps = []
                if self.reply_with_mention:
                    for comp in result.chain:
                        if isinstance(comp, Comp.At):
                            decorated_comps.append(comp)
                            result.chain.remove(comp)
                            break
                if self.reply_with_quote:
                    for comp in result.chain:
                        if isinstance(comp, Comp.Reply):
                            decorated_comps.append(comp)
                            result.chain.remove(comp)
                            break
                # 分段回复
                for comp in result.chain:
                    i = await self._calc_comp_interval(comp)
                    await asyncio.sleep(i)
                    try:
                        await event.send(MessageChain([*decorated_comps, comp]))
                    except Exception as e:
                        logger.error(f"发送消息失败: {e} chain: {result.chain}")
                        break
            else:
                try:
                    await event.send(result)
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"发送消息失败: {e} chain: {result.chain}")
            await event._post_send()
            logger.info(
                f"AstrBot -> {event.get_sender_name()}/{event.get_sender_id()}: {event._outline_chain(result.chain)}"
            )

        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnAfterMessageSentEvent, platform_id=event.get_platform_id()
        )
        for handler in handlers:
            try:
                logger.debug(
                    f"hook(on_after_message_sent) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}"
                )
                await handler.handler(event)
            except BaseException:
                logger.error(traceback.format_exc())

            if event.is_stopped():
                logger.info(
                    f"{star_map[handler.handler_module_path].name} - {handler.handler_name} 终止了事件传播。"
                )
                return

        event.clear_result()
