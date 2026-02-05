from __future__ import annotations

import random
import traceback
from typing import TYPE_CHECKING

from astrbot.core import logger
from astrbot.core.message.components import At, AtAll, Reply
from astrbot.core.pipeline.agent import AgentExecutor
from astrbot.core.pipeline.engine.chain_executor import ChainExecutor
from astrbot.core.pipeline.system.access_control import AccessController
from astrbot.core.pipeline.system.command_dispatcher import CommandDispatcher
from astrbot.core.pipeline.system.event_preprocessor import EventPreprocessor
from astrbot.core.pipeline.system.rate_limit import RateLimiter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_event import (
    WecomAIBotMessageEvent,
)
from astrbot.core.star.node_star import NodeResult

from .send_service import SendService

if TYPE_CHECKING:
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.star.context import Context


class PipelineExecutor:
    """Pipeline 执行器

    协调各组件完成消息处理，不直接处理业务逻辑。
    """

    def __init__(
        self,
        context: Context,
        pipeline_ctx: PipelineContext,
    ) -> None:
        self.agent_executor = AgentExecutor()
        self.context = context  # Star Context
        self.pipeline_ctx = pipeline_ctx  # Pipeline 配置上下文
        self._initialized = False

        # 基础服务
        self.preprocessor = EventPreprocessor(pipeline_ctx)
        self.send_service = SendService(pipeline_ctx)

        # 命令分发器（Star 插件）
        self.command_dispatcher = CommandDispatcher(
            self.pipeline_ctx.astrbot_config,
            self.send_service,
            self.agent_executor,
        )

        # Chain 执行器（NodeStar 插件）
        self.chain_executor = ChainExecutor(self.context)

        self.rate_limiter = RateLimiter(pipeline_ctx)
        self.access_controller = AccessController(pipeline_ctx)

    async def initialize(self) -> None:
        """初始化所有组件"""
        if self._initialized:
            return

        # AgentExecutor
        await self.agent_executor.initialize(self.pipeline_ctx)

        await self.rate_limiter.initialize()
        await self.access_controller.initialize()

        # 加载 Chain 配置
        self._initialized = True
        logger.info(
            f"PipelineExecutor initialized with {len(self.chain_executor.nodes)} nodes"
        )

    async def execute(self, event: AstrMessageEvent) -> None:
        """执行 Pipeline"""
        try:
            # 预处理
            should_continue = await self.preprocessor.preprocess(event)
            if not should_continue:
                return

            # 获取 Chain
            chain_config = event.chain_config

            if not chain_config:
                raise RuntimeError("Missing chain_config on event.")

            resume_node = event.get_extra("_resume_node")
            resume_node_uuid = event.get_extra("_resume_node_uuid")

            if resume_node or resume_node_uuid:
                if await self._run_system_mechanisms(event) == NodeResult.STOP:
                    if event.get_result():
                        await self.send_service.send(event)
                    return

                chain_result = await self.chain_executor.execute(
                    event,
                    chain_config,
                    self.send_service,
                    self.agent_executor,
                    start_node_name=resume_node,
                    start_node_uuid=resume_node_uuid,
                )

                if (
                    chain_result.should_send
                    and event.get_result()
                    and (
                        not event.is_stopped()
                        or event.get_extra("_node_stop_event", False)
                    )
                ):
                    await self.send_service.send(event)
                return

            # 唤醒检测
            self._detect_wake(event)

            # 命令匹配，匹配成功会设置 is_wake，但不执行命令
            event.plugins_name = self._resolve_plugins_name(chain_config)

            logger.debug(f"enabled_plugins_name: {event.plugins_name}")

            matched_handlers = await self.command_dispatcher.match(
                event,
                event.plugins_name,
            )

            # 如果匹配过程中权限检查失败导致 stop
            if event.is_stopped():
                if event.get_result():
                    await self.send_service.send(event)
                return

            # 如果没有命令匹配且未唤醒，直接返回
            if not matched_handlers and not event.is_wake:
                return

            # 系统机制检查（限流、权限）
            if await self._run_system_mechanisms(event) == NodeResult.STOP:
                if event.get_result():
                    await self.send_service.send(event)
                return

            # 命令执行
            if matched_handlers:
                command_executed = await self.command_dispatcher.execute(
                    event,
                    matched_handlers,
                )

                if event.is_stopped():
                    if event.get_result():
                        await self.send_service.send(event)
                    return

                # 如果命令已完全处理且无需继续，返回
                if command_executed and event.get_result():
                    await self.send_service.send(event)
                    return

            # Chain 执行（NodeStar 插件）
            chain_result = await self.chain_executor.execute(
                event,
                chain_config,
                self.send_service,
                self.agent_executor,
            )

            # 发送结果
            if (
                chain_result.should_send
                and event.get_result()
                and (
                    not event.is_stopped() or event.get_extra("_node_stop_event", False)
                )
            ):
                await self.send_service.send(event)

        except Exception as e:
            logger.error(f"Pipeline execution error: {e}")
            logger.error(traceback.format_exc())
        finally:
            await self._handle_special_platforms(event)
            logger.debug("Pipeline 执行完毕。")

    def _resolve_plugins_name(self, chain_config) -> list[str] | None:
        if chain_config and chain_config.plugin_filter:
            mode = chain_config.plugin_filter.mode or "blacklist"
            plugins = chain_config.plugin_filter.plugins or []
            if mode == "whitelist":
                return plugins
            if not plugins:
                return None
            all_names = [p.name for p in self.context.get_all_stars() if p.name]
            return [name for name in all_names if name not in set(plugins)]

        plugins_name = self.pipeline_ctx.astrbot_config.get("plugin_set", ["*"])
        if plugins_name == ["*"]:
            return None
        return plugins_name

    def _detect_wake(self, event: AstrMessageEvent) -> None:
        """唤醒检测"""
        config = self.pipeline_ctx.astrbot_config
        friend_message_needs_wake_prefix = config["platform_settings"].get(
            "friend_message_needs_wake_prefix", False
        )
        ignore_at_all = config["platform_settings"].get("ignore_at_all", False)

        wake_prefixes = config["wake_prefix"]
        messages = event.get_messages()
        is_wake = False

        # 检查唤醒前缀
        for wake_prefix in wake_prefixes:
            if event.message_str.startswith(wake_prefix):
                # 排除 @ 其他人的情况
                if (
                    not event.is_private_chat()
                    and messages
                    and isinstance(messages[0], At)
                    and str(messages[0].qq) != str(event.get_self_id())
                    and str(messages[0].qq) != "all"
                ):
                    break
                is_wake = True
                event.is_at_or_wake_command = True
                event.is_wake = True
                event.message_str = event.message_str[len(wake_prefix) :].strip()
                break

        # 检查 @ 和 Reply
        if not is_wake:
            for message in messages:
                if (
                    (
                        isinstance(message, At)
                        and str(message.qq) == str(event.get_self_id())
                    )
                    or (isinstance(message, AtAll) and not ignore_at_all)
                    or (
                        isinstance(message, Reply)
                        and str(message.sender_id) == str(event.get_self_id())
                    )
                ):
                    event.is_wake = True
                    event.is_at_or_wake_command = True
                    break

            # 私聊默认唤醒
            if event.is_private_chat() and not friend_message_needs_wake_prefix:
                event.is_wake = True
                event.is_at_or_wake_command = True

    async def _run_system_mechanisms(
        self,
        event: AstrMessageEvent,
    ) -> NodeResult:
        # 限流检查
        result = await self.rate_limiter.apply(event)
        if result == NodeResult.STOP:
            return result

        # 访问控制
        result = await self.access_controller.apply(event)
        if result == NodeResult.STOP:
            return result

        # 预回应表情
        await self._pre_ack_emoji(event)

        return NodeResult.CONTINUE

    async def _pre_ack_emoji(self, event: AstrMessageEvent) -> None:
        """预回应表情"""
        if event.get_extra("_pre_ack_sent", False):
            return

        supported = {"telegram", "lark"}
        platform = event.get_platform_name()
        cfg = (
            self.pipeline_ctx.astrbot_config.get("platform_specific", {})
            .get(platform, {})
            .get("pre_ack_emoji", {})
        ) or {}
        emojis = cfg.get("emojis") or []

        if (
            cfg.get("enable", False)
            and platform in supported
            and emojis
            and event.is_at_or_wake_command
        ):
            try:
                await event.react(random.choice(emojis))
                event.set_extra("_pre_ack_sent", True)
            except Exception as e:
                logger.warning(f"{platform} 预回应表情发送失败: {e}")

    @staticmethod
    async def _handle_special_platforms(event: AstrMessageEvent) -> None:
        """处理特殊平台"""
        if isinstance(event, WebChatMessageEvent | WecomAIBotMessageEvent):
            await event.send(None)
