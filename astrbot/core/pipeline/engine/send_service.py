from __future__ import annotations

import asyncio
import math
import random
import re
from typing import Any

import astrbot.core.message.components as Comp
from astrbot.core import logger
from astrbot.core.message.components import (
    At,
    BaseMessageComponent,
    ComponentType,
    File,
    Node,
    Plain,
    Reply,
)
from astrbot.core.message.message_event_result import MessageChain, ResultContentType
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.path_util import path_Mapping

from ..context_utils import call_event_hook


class SendService:
    """独立发送服务，包含可配置的发送前装饰功能

    此服务从 RespondStage + ResultDecorateStage 抽取，包含：
    - 空消息过滤
    - 路径映射
    - 可配置装饰功能（reply_prefix, segment_split, forward_wrapper, at_mention, quote_reply）
    - 分段发送
    - 流式发送
    """

    # 组件类型到其非空判断函数的映射
    _component_validators: dict[type, Any] = {
        Comp.Plain: lambda comp: bool(comp.text and comp.text.strip()),
        Comp.Face: lambda comp: comp.id is not None,
        Comp.Record: lambda comp: bool(comp.file),
        Comp.Video: lambda comp: bool(comp.file),
        Comp.At: lambda comp: bool(comp.qq) or bool(comp.name),
        Comp.Image: lambda comp: bool(comp.file),
        Comp.Reply: lambda comp: bool(comp.id) and comp.sender_id is not None,
        Comp.Poke: lambda comp: comp.id != 0 and comp.qq != 0,
        Comp.Node: lambda comp: bool(comp.content),
        Comp.Nodes: lambda comp: bool(comp.nodes),
        Comp.File: lambda comp: bool(comp.file_ or comp.url),
        Comp.WechatEmoji: lambda comp: comp.md5 is not None,
    }

    def __init__(self, ctx: PipelineContext):
        self.ctx = ctx
        config = ctx.astrbot_config
        platform_settings = config.get("platform_settings", {})
        provider_cfg = config.get("provider_settings", {})

        self.reply_prefix: str = platform_settings.get("reply_prefix", "")
        self.forward_wrapper: bool = platform_settings.get("forward_wrapper", False)
        self.forward_threshold: int = platform_settings.get("forward_threshold", 1500)
        self.reply_with_mention: bool = platform_settings.get(
            "reply_with_mention", False
        )
        self.reply_with_quote: bool = platform_settings.get("reply_with_quote", False)

        # 分段相关
        segmented_reply_cfg = platform_settings.get("segmented_reply", {})
        self.enable_segment = segmented_reply_cfg.get("enable", False)
        self.segment_mode = segmented_reply_cfg.get("split_mode", "regex")

        self.words_count_threshold: int = segmented_reply_cfg.get(
            "words_count_threshold", 150
        )
        try:
            self.words_count_threshold = max(int(self.words_count_threshold), 1)
        except (TypeError, ValueError):
            self.words_count_threshold = 150
        self.only_llm_result: bool = segmented_reply_cfg.get("only_llm_result", False)
        self.regex_pattern: str = segmented_reply_cfg.get(
            "regex", r".*?[。？！~…]+|.+$"
        )
        self.split_words: list[str] = segmented_reply_cfg.get(
            "split_words", ["。", "？", "！", "~", "…"]
        )
        self.content_cleanup_rule: str = segmented_reply_cfg.get(
            "content_cleanup_rule", ""
        )

        # 分段回复时间间隔
        self.interval_method: str = segmented_reply_cfg.get("interval_method", "random")
        self.log_base: float = float(segmented_reply_cfg.get("log_base", 2.6))
        interval_str: str = segmented_reply_cfg.get("interval", "1.5, 3.5")
        try:
            self.interval = [float(t) for t in interval_str.replace(" ", "").split(",")]
        except Exception:
            self.interval = [1.5, 3.5]

        # 构建 split_words pattern
        if self.split_words:
            escaped_words = sorted(
                [re.escape(word) for word in self.split_words], key=len, reverse=True
            )
            self.split_words_pattern = re.compile(
                f"(.*?({'|'.join(escaped_words)})|.+$)", re.DOTALL
            )
        else:
            self.split_words_pattern = None

        # 路径映射
        self.path_mapping: list[str] = platform_settings.get("path_mapping", [])

        # reasoning 输出
        self.show_reasoning: bool = provider_cfg.get("display_reasoning_text", False)

    async def send(self, event: AstrMessageEvent) -> None:
        """发送消息（由 Agent 的 send tool 或 Pipeline 末端调用）"""
        result = event.get_result()
        if result is None:
            return

        # 已经流式发送完成
        if event.get_extra("_streaming_finished", False):
            return

        # 流式发送
        if result.result_content_type == ResultContentType.STREAMING_RESULT:
            await self._send_streaming(event, result)
            return

        if result.result_content_type == ResultContentType.STREAMING_FINISH:
            if result.chain:
                if await self._trigger_decorate_hook(event, is_stream=True):
                    return
            event.set_extra("_streaming_finished", True)
            return

        if not result.chain:
            return

        # 发送消息前事件钩子
        if await self._trigger_decorate_hook(event, is_stream=False):
            return

        # 需要再获取一次。
        result = event.get_result()
        if result is None or not result.chain:
            return

        # reasoning 内容插入（仅在未启用 TTS/T2I 时）
        self._maybe_inject_reasoning(event, result)

        # 应用路径映射
        if self.path_mapping:
            for idx, comp in enumerate(result.chain):
                if isinstance(comp, Comp.File) and comp.file:
                    comp.file = path_Mapping(self.path_mapping, comp.file)
                    result.chain[idx] = comp

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

        if not result.chain:
            return

        logger.info(
            f"Prepare to send - {event.get_sender_name()}/{event.get_sender_id()}: {event._outline_chain(result.chain)}"
        )

        # 应用装饰
        chain = result.chain

        # 1. 回复前缀
        if self.reply_prefix:
            chain = self._add_reply_prefix(chain)

        # 2. 文本分段（仅在 segmented_reply 启用时）
        chain = self._split_chain_for_segmented_reply(event, result, chain)

        # 3. 合并转发包装（aiocqhttp）
        if self.forward_wrapper and self._should_forward_wrap(event, chain):
            chain = self._wrap_forward(event, chain)

        # 4. 是否需要分段发送
        need_segment = self._is_seg_reply_required(event, result)

        # 5. @提及 和 引用回复
        has_plain = any(isinstance(item, Plain) for item in chain)
        if has_plain:
            if (
                self.reply_with_mention
                and event.get_message_type() != MessageType.FRIEND_MESSAGE
            ):
                chain = self._add_at_mention(chain, event)
            if self.reply_with_quote:
                chain = self._add_quote_reply(chain, event)

        # 发送
        need_separately = {ComponentType.Record}
        if need_segment:
            await self._send_segmented(event, chain, need_separately)
        else:
            await self._send_normal(event, chain, need_separately)

        # 触发 OnAfterMessageSentEvent
        await self._trigger_post_send_hook(event)
        event.clear_result()

    @staticmethod
    async def _trigger_decorate_hook(
            event: AstrMessageEvent, is_stream: bool
    ) -> bool:
        if is_stream:
            logger.warning(
                "启用流式输出时，依赖发送消息前事件钩子的插件可能无法正常工作",
            )
        return await call_event_hook(event, EventType.OnDecoratingResultEvent)

    def _maybe_inject_reasoning(self, event: AstrMessageEvent, result) -> None:
        if not self.show_reasoning:
            return
        reasoning_content = event.get_extra("_llm_reasoning_content")
        if not reasoning_content:
            return
        if result.chain and isinstance(result.chain[0], Plain):
            if result.chain[0].text.startswith("🤔 思考:"):
                return
        result.chain.insert(0, Plain(f"🤔 思考: {reasoning_content}\n"))

    async def _send_streaming(self, event: AstrMessageEvent, result) -> None:
        """流式发送"""
        if result.async_stream is None:
            logger.warning("async_stream 为空，跳过发送。")
            return

        realtime_segmenting = (
            self.ctx.astrbot_config.get("provider_settings", {}).get(
                "unsupported_streaming_strategy", "realtime_segmenting"
            )
            == "realtime_segmenting"
        )
        logger.info(f"应用流式输出({event.get_platform_id()})")
        await event.send_streaming(result.async_stream, realtime_segmenting)

    async def _send_normal(
        self,
        event: AstrMessageEvent,
        chain: list[BaseMessageComponent],
        need_separately: set[ComponentType],
    ) -> None:
        """普通发送（非分段）"""
        if all(comp.type in {ComponentType.Reply, ComponentType.At} for comp in chain):
            logger.warning("消息链全为 Reply 和 At 消息段, 跳过发送阶段。")
            return

        # 提取需要单独发送的组件
        sep_comps = self._extract_comp(chain, need_separately, modify_raw_chain=True)

        for comp in sep_comps:
            try:
                await event.send(MessageChain([comp]))
            except Exception as e:
                logger.error(f"发送消息链失败: {e}", exc_info=True)

        if chain:
            try:
                await event.send(MessageChain(chain))
            except Exception as e:
                logger.error(f"发送消息链失败: {e}", exc_info=True)

    async def _send_segmented(
        self,
        event: AstrMessageEvent,
        chain: list[BaseMessageComponent],
        need_separately: set[ComponentType],
    ) -> None:
        """分段发送"""
        # 提取 header 组件（Reply, At）
        header_comps = self._extract_comp(
            chain, {ComponentType.Reply, ComponentType.At}, modify_raw_chain=True
        )

        if not chain:
            logger.warning("实际消息链为空, 跳过发送阶段。")
            return

        for comp in chain:
            interval = await self._calc_comp_interval(comp)
            await asyncio.sleep(interval)
            try:
                if comp.type in need_separately:
                    await event.send(MessageChain([comp]))
                else:
                    await event.send(MessageChain([*header_comps, comp]))
                    header_comps.clear()
            except Exception as e:
                logger.error(f"发送消息链失败: {e}", exc_info=True)

    def _split_text_by_words(self, text: str) -> list[str]:
        if not self.split_words_pattern:
            return [text]

        segments = self.split_words_pattern.findall(text)
        result: list[str] = []
        for seg in segments:
            if isinstance(seg, tuple):
                content = seg[0]
                if not isinstance(content, str):
                    continue
                for word in self.split_words:
                    if content.endswith(word):
                        content = content[: -len(word)]
                        break
                if content.strip():
                    result.append(content)
            elif seg and seg.strip():
                result.append(seg)
        return result if result else [text]

    def _split_chain_for_segmented_reply(
        self,
        event: AstrMessageEvent,
        result,
        chain: list[BaseMessageComponent],
    ) -> list[BaseMessageComponent]:
        if not self._is_seg_reply_required(event, result):
            return chain

        new_chain: list[BaseMessageComponent] = []
        for comp in chain:
            if isinstance(comp, Plain):
                if len(comp.text) > self.words_count_threshold:
                    new_chain.append(comp)
                    continue

                if self.segment_mode == "words":
                    split_response = self._split_text_by_words(comp.text)
                else:
                    try:
                        split_response = re.findall(
                            self.regex_pattern,
                            comp.text,
                            re.DOTALL | re.MULTILINE,
                        )
                    except re.error:
                        logger.error(
                            "分段回复正则表达式错误，使用默认分段方式。",
                            exc_info=True,
                        )
                        split_response = re.findall(
                            r".*?[。？！~…]+|.+$",
                            comp.text,
                            re.DOTALL | re.MULTILINE,
                        )

                if not split_response:
                    new_chain.append(comp)
                    continue

                for seg in split_response:
                    if self.content_cleanup_rule:
                        seg = re.sub(self.content_cleanup_rule, "", seg)
                    if seg.strip():
                        new_chain.append(Plain(seg))
            else:
                new_chain.append(comp)

        return new_chain

    def _add_reply_prefix(
        self, chain: list[BaseMessageComponent]
    ) -> list[BaseMessageComponent]:
        """添加回复前缀"""
        for comp in chain:
            if isinstance(comp, Plain):
                comp.text = self.reply_prefix + comp.text
                break
        return chain

    @staticmethod
    def _add_at_mention(
            chain: list[BaseMessageComponent], event: AstrMessageEvent
    ) -> list[BaseMessageComponent]:
        """添加 @提及"""
        chain.insert(0, At(qq=event.get_sender_id(), name=event.get_sender_name()))
        if len(chain) > 1 and isinstance(chain[1], Plain):
            chain[1].text = "\n" + chain[1].text
        return chain

    @staticmethod
    def _add_quote_reply(
            chain: list[BaseMessageComponent], event: AstrMessageEvent
    ) -> list[BaseMessageComponent]:
        """添加引用回复"""
        if not any(isinstance(item, File) for item in chain):
            chain.insert(0, Reply(id=event.message_obj.message_id))
        return chain

    def _should_forward_wrap(
        self, event: AstrMessageEvent, chain: list[BaseMessageComponent]
    ) -> bool:
        """判断是否需要合并转发"""
        if event.get_platform_name() != "aiocqhttp":
            return False
        word_cnt = sum(len(comp.text) for comp in chain if isinstance(comp, Plain))
        return word_cnt > self.forward_threshold

    @staticmethod
    def _wrap_forward(
            event: AstrMessageEvent, chain: list[BaseMessageComponent]
    ) -> list[BaseMessageComponent]:
        """合并转发包装"""
        if event.get_platform_name() != "aiocqhttp":
            return chain
        node = Node(
            uin=event.get_self_id(),
            name="AstrBot",
            content=[*chain],
        )
        return [node]

    def _is_seg_reply_required(self, event: AstrMessageEvent, result) -> bool:
        """检查是否需要分段回复"""
        if not self.enable_segment:
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

    async def _is_empty_message_chain(self, chain: list[BaseMessageComponent]) -> bool:
        """检查消息链是否为空"""
        if not chain:
            return True
        for comp in chain:
            comp_type = type(comp)
            if comp_type in self._component_validators:
                if self._component_validators[comp_type](comp):
                    return False
        return True

    @staticmethod
    def _extract_comp(
            raw_chain: list[BaseMessageComponent],
        extract_types: set[ComponentType],
        modify_raw_chain: bool = True,
    ) -> list[BaseMessageComponent]:
        """提取特定类型的组件"""
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

    async def _calc_comp_interval(self, comp: BaseMessageComponent) -> float:
        """计算分段回复间隔时间"""
        if self.interval_method == "log":
            if isinstance(comp, Comp.Plain):
                wc = await self._word_cnt(comp.text)
                i = math.log(wc + 1, self.log_base)
                return random.uniform(i, i + 0.5)
            return random.uniform(1, 1.75)
        return random.uniform(self.interval[0], self.interval[1])

    @staticmethod
    async def _word_cnt(text: str) -> int:
        """统计字数"""
        if all(ord(c) < 128 for c in text):
            return len(text.split())
        else:
            return len([c for c in text if c.isalnum()])

    @staticmethod
    async def _trigger_post_send_hook(event: AstrMessageEvent) -> None:
        """触发发送后钩子"""
        await call_event_hook(event, EventType.OnAfterMessageSentEvent)
