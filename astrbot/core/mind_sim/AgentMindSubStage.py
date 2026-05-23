"""高级人格 LLM 调用模块 - 替代 MindSimLLM 的角色路由 + run_agent 模式

作为 InternalMindSubStage/Brain/ReplyAction 的 LLM 调用层，支持：
- 按角色（deep/medium/fast/function/reply）注入不同模型
- 组装提示词 + 调用 run_agent()
- 通过回调返回结果 or 直接发送到平台
- 流式/非流式响应

- AgentMindSubStage：给高级人格 Stage 使用，支持更灵活的 run_agent 模式
"""

import asyncio
import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from astrbot.core import logger
from astrbot.core.agent.message import Message
from astrbot.core.agent.response import AgentStats
from astrbot.core.astr_main_agent import (
    MainAgentBuildConfig,
    MainAgentBuildResult,
    build_main_agent,
)
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.session_lock import session_lock_manager

from ..astr_agent_run_util import AgentRunner, run_agent, run_live_agent
from ..pipeline.context_utils import call_event_hook

# 安全防护：阻止连接到已知的恶意主机
BLOCKED = {"dGZid2h2d3IuY2xvdWQuc2VhbG9zLmlv", "a291cmljaGF0"}
decoded_blocked = [base64.b64decode(b).decode("utf-8") for b in BLOCKED]


@dataclass
class ModelConfig:
    """单个角色模型配置"""

    provider_id: str = ""
    """Provider 实例 ID"""
    model: str = ""
    """模型名称"""
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class LLMCallResult:
    """LLM 调用结果"""

    text: str = ""
    """完整响应文本"""
    streaming_delta: str = ""
    """流式增量（单块文本）"""
    is_streaming: bool = False
    """是否流式"""
    is_done: bool = False
    """是否完成"""
    usage: Any = None
    """Token 用量"""


class AgentMindSubStage:
    """高级人格 LLM 调用器

    支持：
    - 按角色注册不同模型
    - 组装提示词 + 调用 run_agent
    - 流式/非流式响应
    - 通过 step_callback 获取每步结果
    - 直接发送结果到平台

    架构与 internal.py 完全一致：
    1. 发送"正在输入"状态
    2. 调用 OnWaitingLLMRequestEvent 钩子
    3. 获取会话锁（确保同一会话请求顺序执行）
    4. 获取动作类型（支持 Live Mode）
    5. 根据模式选择 run_live_agent / run_agent 流式 / run_agent 普通
    6. 保存历史记录
    7. 上传指标

    使用方式：
    1. 创建实例，传入 event 和配置
    2. 注册角色模型（可选）
    3. 调用 call() 或 call_simple() 获取结果
    """

    def __init__(
        self,
        event: AstrMessageEvent,
        plugin_context: Any,
        config: dict | None = None,
        provider_wake_prefix: str = "",
    ):
        """
        Args:
            event: 当前消息事件
            plugin_context: 插件上下文（用于获取 Provider）
            config: 提供者设置（来自 provider_settings）
            provider_wake_prefix: 提供者唤醒前缀
        """
        self.event = event
        self.plugin_context = plugin_context
        self.config = config or {}
        self.provider_wake_prefix = provider_wake_prefix

        # 模型配置
        self._role_configs: dict[str, ModelConfig] = {}
        self._provider_cache: dict[str, Any] = {}

        # 流式响应配置
        self.streaming_response: bool = (
            config.get("streaming_response", True) if config else True
        )
        self.unsupported_streaming_strategy: str = (
            config.get("unsupported_streaming_strategy", "turn_off")
            if config
            else "turn_off"
        )

        # Agent 执行配置 这里默认是1
        self.max_step: int = 1
        self.show_tool_use: bool = (
            config.get("show_tool_use_status", True) if config else True
        )
        self.show_tool_call_result: bool = (
            config.get("show_tool_call_result", False) if config else False
        )
        self.show_reasoning: bool = (
            config.get("display_reasoning_text", False) if config else False
        )

        # Token 统计
        self._total_usage = None

        # 最后一次 call() 的完成文本
        self._last_completion_text: str = ""

        # 回调函数
        self._step_callback: Callable[[int, str, Any], None] | None = None
        self._result_callback: Callable[[str], None] | None = None

        # 会话锁管理器
        self._conv_manager = None

        # Brain 事件队列引用（用于发送 PIPELINE_YIELD 事件）
        self._mind_event_queue: asyncio.Queue | None = None

    def register_model(self, role: str, model_config: ModelConfig) -> str | None:
        """注册角色对应的模型配置

        Args:
            role: 角色名 (deep/medium/fast/function/reply)
            model_config: 模型配置

        Returns:
            错误信息字符串，None 表示成功
        """
        if not model_config.provider_id or not model_config.model:
            return None

        # 查缓存或获取 Provider
        provider = self._provider_cache.get(model_config.provider_id)
        if not provider:
            provider = self.plugin_context.provider_manager.inst_map.get(
                model_config.provider_id
            )
            if not provider:
                return f"提供商 '{model_config.provider_id}' 不存在或已被删除"
            self._provider_cache[model_config.provider_id] = provider

        self._role_configs[role] = model_config
        logger.debug(
            f"[AgentMindSubStage] 注册模型 role={role}, "
            f"provider={model_config.provider_id}, model={model_config.model}"
        )
        return None

    def register_models_from_persona_config(self, persona_config: dict) -> list[str]:
        """从高级人格配置注册所有角色模型

        Args:
            persona_config: 人格配置字典

        Returns:
            注册失败的错误列表
        """
        errors = []
        llm_model_config = persona_config.get("llm_model_config", {})

        role_map = {
            "deep": llm_model_config.get("thinking_models", {}).get("deep", {}),
            "medium": llm_model_config.get("thinking_models", {}).get("medium", {}),
            "fast": llm_model_config.get("thinking_models", {}).get("fast", {}),
            "function": llm_model_config.get("function_model", {}),
            "reply": llm_model_config.get("reply_model", {}),
        }

        for role, cfg_dict in role_map.items():
            if not cfg_dict:
                continue
            model_config = ModelConfig(
                provider_id=cfg_dict.get("provider_id", ""),
                model=cfg_dict.get("model", ""),
                temperature=cfg_dict.get("temperature", 0.7),
                max_tokens=cfg_dict.get("max_tokens", 4096),
            )
            error = self.register_model(role, model_config)
            if error:
                errors.append(f"{role}: {error}")
                logger.warning(f"[AgentMindSubStage] {role} 模型注册失败: {error}")

        return errors

    def _get_provider_and_model(self, role: str) -> tuple[Any, str | None, float]:
        """获取角色对应的 Provider 实例、模型名和温度

        Returns:
            (Provider 实例, 模型名, 温度)
        """
        default_provider = self.plugin_context.get_using_provider(
            umo=self.event.unified_msg_origin
        )
        config = self._role_configs.get(role)
        if not config:
            return default_provider, None, 0.7

        provider = self._provider_cache.get(config.provider_id, default_provider)
        return provider, config.model, config.temperature

    def set_step_callback(self, callback: Callable[[int, str, Any], None] | None):
        """设置步骤回调（每步完成后调用）"""
        self._step_callback = callback

    def set_result_callback(self, callback: Callable[[str], None] | None):
        """设置结果回调（每次产出一个文本片段时调用）"""
        self._result_callback = callback

    async def _build_agent_runner(
        self,
        system_prompt: str,
        user_prompt: str,
        contexts: list[dict] | None = None,
        role: str = "deep",
    ) -> MainAgentBuildResult:
        """构建 Agent Runner

        与 internal.py 一致，返回 reset_coro 由调用方决定何时执行。

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            contexts: 上下文消息列表（OpenAI 格式）
            role: 模型角色（用于选择模型）

        Returns:
            (agent_runner, provider_request, provider, reset_coro)
        """
        provider, model_name, temperature = self._get_provider_and_model(role)
        if not model_name:
            model_name = provider.get_model()

        # 构建消息
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if contexts:
            messages.extend(contexts)
        messages.append({"role": "user", "content": user_prompt})

        # 获取对话管理器
        if not self._conv_manager:
            self._conv_manager = self.plugin_context.conversation_manager

        cid = await self._conv_manager.get_curr_conversation_id(
            self.event.unified_msg_origin
        )
        if not cid:
            cid = await self._conv_manager.new_conversation(
                self.event.unified_msg_origin, self.event.get_platform_id()
            )
        conversation = await self._conv_manager.get_conversation(
            self.event.unified_msg_origin, cid
        )

        req = ProviderRequest(
            prompt=user_prompt,
            session_id=str(self.event.session),
            image_urls=[],
            contexts=[],
            system_prompt=system_prompt,
            conversation=conversation,
            func_tool=None,
            tool_calls_result=None,
            model=model_name,
        )

        # 构建 Agent
        build_cfg = MainAgentBuildConfig(
            tool_call_timeout=60,
            tool_schema_mode="full",
            streaming_response=self.streaming_response,
            provider_settings=self.config,
            max_quoted_fallback_images=20,
        )

        result = await build_main_agent(
            event=self.event,
            plugin_context=self.plugin_context,
            req=req,
            config=build_cfg,
            apply_reset=False,
        )

        if result is None:
            raise RuntimeError("Agent 构建失败")
        # result.provider_request.contexts =[]
        # result.provider_request.prompt = user_prompt

        return result
        # # build_main_agent 会用数据库对话历史覆盖 req.contexts，
        # req.contexts = messages
        #
        # agent_runner = result.agent_runner
        # reset_coro = result.reset_coro
        #
        # return agent_runner, req, provider, reset_coro

    async def _pipeline_yield(self):
        """桥接 pipeline yield 机制

        AgentMindSubStage 不在 pipeline 里，无法直接 yield 给框架。
        通过 Brain 的事件队列发送 PIPELINE_YIELD 事件，
        InternalMindSubStage 收到后 yield 给 pipeline 框架（让 RespondStage 处理 event.result），
        完成后 set done_event 通知本方法返回。
        """
        from astrbot.core.mind_sim.messages import MindEvent

        if not self._mind_event_queue:
            logger.warning(
                "[AgentMindSubStage] 无 mind_event_queue，跳过 pipeline yield"
            )
            return

        done_event = asyncio.Event()
        await self._mind_event_queue.put(MindEvent.pipeline_yield(done_event))
        # 等待 InternalMindSubStage yield 完成
        await done_event.wait()

    async def call(
        self,
        prompt: str,
        role: str = "deep",
        system_prompt: str = "",
        contexts: list[dict] | None = None,
        streaming: bool | None = None,
        max_step: int | None = None,
        send_to_platform: bool = True,
    ) -> str:
        """调用 LLM 生成响应（与 internal.py process() 流程完全一致）

        通过 PIPELINE_YIELD 事件桥接 pipeline 框架的 yield 机制，
        让 event.set_result() 的结果能被 RespondStage 处理并发送到平台。

        Returns:
            最终响应文本
        """
        streaming_response = (
            streaming if streaming is not None else self.streaming_response
        )
        use_max_step = max_step or self.max_step

        event = self.event
        agent_runner: AgentRunner | None = None

        try:
            # 1. 发送"正在输入"状态
            await event.send_typing()
            # 2. 调用 OnWaitingLLMRequestEvent 钩子
            await call_event_hook(event, EventType.OnWaitingLLMRequestEvent)

            # 3. 获取会话锁（确保同一会话请求顺序执行）
            async with session_lock_manager.acquire_lock(event.unified_msg_origin):
                logger.debug("[AgentMindSubStage] 已获取会话锁")

                try:
                    # 4. 构建 Agent Runner
                    build_result = await self._build_agent_runner(
                        system_prompt=system_prompt,
                        user_prompt=prompt,
                        contexts=contexts,
                        role=role,
                    )
                    # 提取构建结果中的组件
                    agent_runner = build_result.agent_runner
                    req = build_result.provider_request
                    provider = build_result.provider
                    reset_coro = build_result.reset_coro

                    # 安全检查
                    api_base = provider.provider_config.get("api_base", "")
                    for host in decoded_blocked:
                        if host in api_base:
                            logger.error(
                                "Provider API base %s is blocked due to security reasons.",
                                api_base,
                            )
                            return ""

                    # 检查是否应该将流式响应转换为普通响应
                    stream_to_general = (
                        self.unsupported_streaming_strategy == "turn_off"
                        and not event.platform_meta.support_streaming_message
                    )

                    # 5. 调用 OnLLMRequestEvent 钩子
                    if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
                        if reset_coro:
                            reset_coro.close()
                        return ""

                    # 应用重置协程
                    if reset_coro:
                        await reset_coro

                    # 6. 获取动作类型（支持 Live Mode）
                    action_type = event.get_extra("action_type")

                    # 记录追踪信息
                    event.trace.record(
                        "astr_agent_prepare",
                        system_prompt=req.system_prompt,
                        tools=req.func_tool.names() if req.func_tool else [],
                        stream=streaming_response,
                        chat_provider={
                            "id": provider.provider_config.get("id", ""),
                            "model": provider.get_model(),
                        },
                    )

                    # Live Mode（实时语音模式）
                    if action_type == "live":
                        logger.info(
                            "[AgentMindSubStage] 检测到 Live Mode，启用 TTS 处理"
                        )

                        tts_provider = self.plugin_context.get_using_tts_provider(
                            event.unified_msg_origin
                        )

                        if not tts_provider:
                            logger.warning(
                                "[Live Mode] TTS Provider 未配置，将使用普通流式模式"
                            )

                        # 使用 run_live_agent，总是使用流式响应
                        event.set_result(
                            MessageEventResult()
                            .set_result_content_type(ResultContentType.STREAMING_RESULT)
                            .set_async_stream(
                                run_live_agent(
                                    agent_runner,
                                    tts_provider,
                                    use_max_step,
                                    self.show_tool_use,
                                    self.show_tool_call_result,
                                    show_reasoning=self.show_reasoning,
                                ),
                            ),
                        )
                        await self._pipeline_yield()

                        # 保存历史记录
                        if agent_runner.done() and (
                            not event.is_stopped() or agent_runner.was_aborted()
                        ):
                            await self._save_to_history(
                                req,
                                agent_runner.get_final_llm_resp(),
                                agent_runner.run_context.messages,
                                agent_runner.stats,
                                user_aborted=agent_runner.was_aborted(),
                            )

                    # 流式响应模式（非 Live Mode）
                    elif streaming_response and not stream_to_general:
                        event.set_result(
                            MessageEventResult()
                            .set_result_content_type(ResultContentType.STREAMING_RESULT)
                            .set_async_stream(
                                run_agent(
                                    agent_runner,
                                    use_max_step,
                                    self.show_tool_use,
                                    self.show_tool_call_result,
                                    show_reasoning=self.show_reasoning,
                                ),
                            ),
                        )
                        await self._pipeline_yield()

                        # 流式完成后设置最终结果
                        if agent_runner.done():
                            if final_llm_resp := agent_runner.get_final_llm_resp():
                                if final_llm_resp.completion_text:
                                    chain = (
                                        MessageChain()
                                        .message(final_llm_resp.completion_text)
                                        .chain
                                    )
                                elif final_llm_resp.result_chain:
                                    chain = final_llm_resp.result_chain.chain
                                else:
                                    chain = MessageChain().chain

                                event.set_result(
                                    MessageEventResult(
                                        chain=chain,
                                        result_content_type=ResultContentType.LLM_RESULT,
                                    ),
                                )

                        # 保存历史记录
                        if not event.is_stopped() or agent_runner.was_aborted():
                            await self._save_to_history(
                                req,
                                agent_runner.get_final_llm_resp(),
                                agent_runner.run_context.messages,
                                agent_runner.stats,
                                user_aborted=agent_runner.was_aborted(),
                            )

                    # 普通响应模式（非流式或流式转普通）
                    else:
                        async for _ in run_agent(
                            agent_runner,
                            use_max_step,
                            self.show_tool_use,
                            self.show_tool_call_result,
                            stream_to_general,
                            self.show_reasoning,
                        ):
                            await self._pipeline_yield()

                    # 获取最终响应
                    final_resp = agent_runner.get_final_llm_resp()

                    # 保存完成文本供调用方读取
                    self._last_completion_text = (
                        final_resp.completion_text if final_resp else ""
                    ) or ""

                    # 记录代理完成信息
                    event.trace.record(
                        "astr_agent_complete",
                        stats=agent_runner.stats.to_dict(),
                        resp=final_resp.completion_text if final_resp else None,
                    )

                    # 普通模式保存历史记录
                    if (
                        not (streaming_response and not stream_to_general)
                        and action_type != "live"
                    ):
                        if not event.is_stopped() or agent_runner.was_aborted():
                            await self._save_to_history(
                                req,
                                final_resp,
                                agent_runner.run_context.messages,
                                agent_runner.stats,
                                user_aborted=agent_runner.was_aborted(),
                            )

                    # 上传指标
                    asyncio.create_task(
                        Metric.upload(
                            llm_tick=1,
                            model_name=agent_runner.provider.get_model(),
                            provider_type=agent_runner.provider.meta().type,
                        ),
                    )

                except Exception:
                    raise

        except Exception as e:
            logger.error(f"[AgentMindSubStage] LLM 调用失败: {e}")
            custom_error_message = extract_persona_custom_error_message_from_event(
                event
            )
            error_text = custom_error_message or f"LLM 调用失败: {e}"
            await event.send(MessageChain().message(error_text))
            return ""

        return self._last_completion_text

    async def _save_to_history(
        self,
        req: ProviderRequest,
        llm_response: LLMResponse | None,
        all_messages: list[Message],
        runner_stats: AgentStats | None,
        user_aborted: bool = False,
    ) -> None:
        """保存对话历史到数据库

        与 internal.py 的 _save_to_history 逻辑完全一致。
        """
        return  # 在这里暂时不保存
        # if not req or not req.conversation:
        #     return
        #
        # if not llm_response and not user_aborted:
        #     return
        #
        # if llm_response and llm_response.role != "assistant":
        #     if not user_aborted:
        #         return
        #     llm_response = LLMResponse(
        #         role="assistant",
        #         completion_text=llm_response.completion_text or "",
        #     )
        # elif llm_response is None:
        #     llm_response = LLMResponse(role="assistant", completion_text="")
        #
        # if (
        #     not llm_response.completion_text
        #     and not req.tool_calls_result
        #     and not user_aborted
        # ):
        #     logger.debug("[AgentMindSubStage] LLM 响应为空，不保存记录。")
        #     return
        #
        # # 过滤和准备要保存的消息
        # message_to_save = []
        # skipped_initial_system = False
        # for message in all_messages:
        #     if message.role == "system" and not skipped_initial_system:
        #         skipped_initial_system = True
        #         continue
        #     if message.role in ["assistant", "user"] and message._no_save:
        #         continue
        #     message_to_save.append(message.model_dump())
        #
        # token_usage = None
        # if runner_stats and llm_response and llm_response.usage:
        #     token_usage = llm_response.usage.total
        #
        # if not self._conv_manager:
        #     self._conv_manager = self.plugin_context.conversation_manager
        #
        # await self._conv_manager.update_conversation(
        #     self.event.unified_msg_origin,
        #     req.conversation.cid,
        #     history=message_to_save,
        #     token_usage=token_usage,
        # )

    async def call_simple(
        self,
        prompt: str,
        role: str = "deep",
        system_prompt: str = "",
        contexts: list[dict] | None = None,
    ) -> str:
        """简单调用 LLM，直接返回文本（不使用 run_agent）

        用于不需要工具调用能力的场景，如 Brain 的思考过程。

        Args:
            prompt: 用户提示词
            role: 模型角色
            system_prompt: 系统提示词
            contexts: 上下文消息列表

        Returns:
            LLM 响应文本
        """
        provider, model_name, temperature = self._get_provider_and_model(role)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if contexts:
            messages.extend(contexts)
        messages.append({"role": "user", "content": prompt})

        try:
            response: LLMResponse = await provider.text_chat(
                prompt=prompt,
                contexts=messages,
                model=model_name,
                temperature=temperature,
            )

            if response.usage:
                self._total_usage = response.usage

            if response.role == "err":
                raise RuntimeError(
                    f"LLM 返回错误: {response.completion_text or '未知错误'}"
                )

            return response.completion_text or response.reasoning_content or ""

        except Exception as e:
            logger.error(f"[AgentMindSubStage] call_simple 失败 (role={role}): {e}")
            raise

    @property
    def token_usage(self) -> Any:
        """累计 token 用量"""
        return self._total_usage

    @classmethod
    def create_for_brain(
        cls,
        event: AstrMessageEvent,
        plugin_context: Any,
        persona_config: dict,
    ) -> "AgentMindSubStage":
        """工厂方法：从高级人格配置创建 AgentMindSubStage

        Args:
            event: 消息事件
            plugin_context: 插件上下文
            persona_config: 人格配置

        Returns:
            AgentMindSubStage 实例（已注册所有角色模型）
        """
        # 获取 provider_settings
        cfg = plugin_context.get_config(event.unified_msg_origin)
        provider_settings = cfg.get("provider_settings", {})

        # 获取 provider_wake_prefix
        prov_wake = provider_settings.get("wake_prefix", "")

        instance = cls(
            event=event,
            plugin_context=plugin_context,
            config=provider_settings,
            provider_wake_prefix=prov_wake,
        )

        # 注册人格配置的模型
        instance.register_models_from_persona_config(persona_config)

        return instance
