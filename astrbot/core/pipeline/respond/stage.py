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
        Comp.Image: lambda comp: bool(comp.file),  # 图片
        Comp.Reply: lambda comp: bool(comp.id) and comp.sender_id is not None,  # 回复
        Comp.Poke: lambda comp: comp.id != 0 and comp.qq != 0,  # 戳一戳
        Comp.Node: lambda comp: bool(comp.content),  # 转发节点
        Comp.Nodes: lambda comp: bool(comp.nodes),  # 多个转发节点
        Comp.File: lambda comp: bool(comp.file_ or comp.url),
        Comp.WechatEmoji: lambda comp: comp.md5 is not None,  # 微信表情
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
            await event.send_streaming(result.async_stream, use_fallback)
            return
        elif len(result.chain) > 0:
            # 检查路径映射
            if mappings := self.platform_settings.get("path_mapping", []):
                for idx, component in enumerate(result.chain):
                    if isinstance(component, Comp.File) and component.file:
                        # 支持 File 消息段的路径映射。
                        component.file = path_Mapping(mappings, component.file)
                        event.get_result().chain[idx] = component

            # 检查消息链是否为空
            try:
                if await self._is_empty_message_chain(result.chain):
                    logger.info("消息为空，跳过发送阶段")
                    event.clear_result()
                    event.stop_event()
                    return
            except Exception as e:
                logger.warning(f"空内容检查异常: {e}")

            record_comps = [c for c in result.chain if isinstance(c, Comp.Record)]
            non_record_comps = [
                c for c in result.chain if not isinstance(c, Comp.Record)
            ]

            if (
                self.enable_seg
                and (
                    (self.only_llm_result and result.is_llm_result())
                    or not self.only_llm_result
                )
                and event.get_platform_name()
                not in ["qq_official", "weixin_official_account", "dingtalk"]
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

                for rcomp in record_comps:
                    i = await self._calc_comp_interval(rcomp)
                    await asyncio.sleep(i)
                    try:
                        await event.send(MessageChain([rcomp]))
                    except Exception as e:
                        logger.error(f"发送消息失败: {e} chain: {result.chain}")
                        break

                # 分段回复
                for comp in non_record_comps:
                    i = await self._calc_comp_interval(comp)
                    await asyncio.sleep(i)
                    try:
                        await event.send(MessageChain([*decorated_comps, comp]))
                        decorated_comps = []  # 清空已发送的装饰组件
                    except Exception as e:
                        logger.error(f"发送消息失败: {e} chain: {result.chain}")
                        break
            else:
                for rcomp in record_comps:
                    try:
                        await event.send(MessageChain([rcomp]))
                    except Exception as e:
                        logger.error(f"发送消息失败: {e} chain: {result.chain}")

                try:
                    await event.send(MessageChain(non_record_comps))
                except Exception as e:
                    logger.error(traceback.format_exc())
                    logger.error(f"发送消息失败: {e} chain: {result.chain}")

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
