"""MindSim 私聊主思考模块 - 事件驱动架构

负责私聊场景下的思考：
1. 收集所有动作的状态和提示词贡献
2. 用快速模型评估场景复杂度，选择思考等级
3. 根据思考等级调用对应模型获取决策
4. 执行决策（启动/发送/停止动作）
5. 处理动作产出并发送到消息平台

架构特点：
- 事件驱动：无主循环，通过 think_once() 触发思考
- 多入口：用户消息、动作完成、等待结束都可触发思考
- 动作完成自动触发下一轮思考
"""

import asyncio
import json
import random
import re
import time
from collections.abc import AsyncGenerator
from typing import Any, Optional

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent


from astrbot.core import logger
from astrbot.core.mind_sim.action import ActionExecutor
from astrbot.core.mind_sim.AgentMindSubStage import AgentMindSubStage
from astrbot.core.mind_sim.context import MindContext
from astrbot.core.mind_sim.messages import (
    ActionOutput,
    ActionSendMsg,
    ActionStateUpdate,
    MindEvent,
    MindEventType,
)

from .actions import get_available_actions
from .prompts import (
    DECISION_FORMAT_PROMPT,
    STUCK_PROMPT,
    UPGRADE_THINKING_PROMPT,
    build_action_states_prompt,
    build_history_prompt,
    build_main_thinking_prompt,
    build_prompt_sections,
    build_temp_prompts_section,
)


def parse_decision(llm_output: str) -> list[dict]:
    """解析 LLM 输出为决策列表

    统一使用动作格式：
    - START <动作名> <JSON参数>
    - SEND <动作名或实例ID> <消息内容>
    - STOP <动作名或实例ID>

    实例 ID 格式：<动作名>#<序号>，如 reply#1, wait#2
    """
    decisions = []

    patterns = {
        "START": re.compile(r"^START\s+([\w]+)\s*(\{.*\})?\s*$", re.IGNORECASE),
        "SEND": re.compile(r"^SEND\s+([\w#]+)\s+(.+)$", re.IGNORECASE),
        "STOP": re.compile(r"^STOP\s+([\w#]+)\s*$", re.IGNORECASE),
    }

    for line in llm_output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        if not any(line.upper().startswith(cmd) for cmd in patterns):
            continue

        for action_type, pattern in patterns.items():
            match = pattern.match(line)
            if match:
                decision = {"action": action_type}
                groups = match.groups()

                if action_type == "START":
                    decision["target"] = groups[0]
                    decision["params"] = {}
                    if groups[1]:
                        try:
                            decision["params"] = json.loads(groups[1])
                        except json.JSONDecodeError:
                            pass
                elif action_type == "SEND":
                    decision["target"] = groups[0]
                    decision["message"] = groups[1].strip().strip("\"'")
                elif action_type == "STOP":
                    decision["target"] = groups[0]

                decisions.append(decision)
                break

    return decisions


MAX_LLM_ERROR_COUNT = 3


class PrivateBrain:
    """私聊主思考模块 - 事件驱动架构

    通过 ActionExecutor 统一管理动作实例，支持同一动作多实例并发。
    无主循环，通过 think_once() 触发思考，动作完成自动触发下一轮。
    """

    def __init__(
        self,
        ctx: MindContext,
        persona: dict | None = None,
    ):
        self.ctx = ctx
        self.persona = persona or {}
        self.llm: AgentMindSubStage | None = None

        # 动作执行器
        self.executor = ActionExecutor(
            ctx=ctx, send_callback=self._on_action_output, llm=None
        )

        # 注册动作类
        for action_cls in get_available_actions():
            self.executor.register(action_cls)

        # 事件输出队列（供外部监听）
        self._event_queue: asyncio.Queue[MindEvent] = asyncio.Queue()

        # 思考状态
        self._thinking = False
        self._think_requested = False
        self._think_task: asyncio.Task | None = None

        # 思考节流机制（1秒内只触发一次思考，累积提示词）
        self._last_think_time: float = 0
        self._think_cooldown: float = 1.0  # 思考冷却时间（秒）
        self._pending_think_timer: asyncio.Task | None = None  # 延迟思考定时器

        # 是否有需要打断 wait 的事件待处理
        self._interrupt_wait_pending: bool = False

        # 中断事件（用于阻塞时被用户消息或动作消息打断）
        self._interrupt_event: asyncio.Event = asyncio.Event()

        # 事件流状态
        self._stream_active = False

        # LLM 错误计数
        self._llm_error_count = 0

        # 连续等待计数（用于检测是否卡住）
        self._consecutive_wait_count: int = 0
        self._consecutive_wait_threshold: int = 3  # 连续等待3次后认为可能卡住
        self._first_wait_time: float = 0  # 第一次等待的时间戳
        self._stuck_min_duration: float = 60.0  # 卡住判断的最小时间（秒）

        # 思考传入提示词
        self._think_prompt_queue: asyncio.Queue[str] = asyncio.Queue()

        # 初始化心情（从高级人格配置中根据权重随机选择）
        self._init_mood()

        logger.debug(
            f"[PrivateBrain] 初始化完成，动作类: {self.executor.get_action_class_names()}"
        )

    def _init_mood(self):
        """根据心情标签权重随机选择心情"""
        # 从 persona 中获取心情标签配置
        personality_config = self.persona.get("personality_config", {})
        mood_tags = personality_config.get("mood_tags", [])

        if not mood_tags:
            # 默认心情
            self.ctx.memory["current_mood"] = "平静"
            return

        # 根据权重随机选择
        total_weight = sum(tag.get("weight", 0) for tag in mood_tags)
        if total_weight <= 0:
            self.ctx.memory["current_mood"] = "平静"
            return

        rand_val = random.random() * total_weight
        cumulative = 0
        selected_mood = "平静"

        for tag in mood_tags:
            cumulative += tag.get("weight", 0)
            if rand_val <= cumulative:
                selected_mood = tag.get("name", "平静")
                break

        self.ctx.memory["current_mood"] = selected_mood
        logger.debug(f"[PrivateBrain] 初始心情: {selected_mood}")

    async def _on_action_output(self, output):
        """动作产出回调，将产出转为事件放入队列"""
        if output is None:
            logger.warning("Received None output")
            return

        reason = output.prompt if hasattr(output, 'prompt') else ""

        if isinstance(output, ActionOutput):
            # 根据输出类型转换为对应的 MindEvent
            if output.type == "reply":
                await self._event_queue.put(
                    MindEvent.reply(output.content, output.metadata)
                )
                # 检查是否标记了不触发重新思考（如 EndConversation 的回复）
                if not (output.metadata and output.metadata.get("no_think")):
                    self._interrupt_event.set()
                    # reply 发出后打断 wait，让主思考决定下一步
                    self._interrupt_wait_pending = True
                    await self._schedule_think(
                        f"动作 {output.action_name} 发出了回复{reason}"
                    )
            elif output.type == "typing":
                await self._event_queue.put(MindEvent.typing())
            elif output.type == "error":
                await self._event_queue.put(
                    MindEvent.error(output.content, output.metadata)
                )
            elif output.type == "completed":
                # 动作完成，触发重新思考
                logger.debug(
                    f"[PrivateBrain] 动作 {output.action_name} 完成，触发重新思考{reason}"
                )
                await self._schedule_think(
                    f"这次是动作{output.action_name} 完成的自动触发思考{reason}"
                )
            elif output.type == "completed_no_think":
                # 动作完成但不触发重新思考
                logger.debug(
                    f"[PrivateBrain] 动作 {output.action_name} 完成（不触发重新思考）"
                )
            elif output.type == "end":
                # 动作请求结束对话
                logger.info(
                    f"[PrivateBrain] 动作 {output.action_name} 请求结束对话: {output.content}"
                )
                # 先停止所有其他正在运行的动作
                await self.executor.stop_all("结束对话，停止所有动作")
                await self._event_queue.put(MindEvent.end(output.content))
            elif output.type == "request_think":
                # 动作显式请求重新思考，打断 wait
                logger.debug(
                    f"[PrivateBrain] 动作 {output.action_name} 请求重新思考: {reason}"
                )
                self._interrupt_wait_pending = True
                if reason:
                    await self._schedule_think(
                        f"这次是动作{output.action_name}由于原因是{reason}请求重新思考触发思考"
                    )
                else:
                    await self._schedule_think(
                        f"这次是动作{output.action_name}请求重新思考触发思考"
                    )
            elif output.type == "noop":
                logger.info(
                    f"[PrivateBrain] 动作 {output.action_name} 什么都没做{reason}"
                )
        elif isinstance(output, ActionStateUpdate):
            pass

    def init_llm(
        self,
        event: AstrMessageEvent,
        plugin_context: Any,
        persona: dict,
    ):
        """初始化 LLM 实例"""
        try:
            self.llm = AgentMindSubStage.create_for_brain(
                event=event,
                plugin_context=plugin_context,
                persona_config=persona,
            )
            # 注入 Brain 的事件队列，让 call() 能发送 PIPELINE_YIELD
            self.llm._mind_event_queue = self._event_queue
            # 同步给 executor，让动作实例能拿到 llm
            self.executor._llm = self.llm
        except Exception as e:
            logger.error(f"[PrivateBrain] 创建 AgentMindSubStage 失败: {e}")
            self.llm = None

    async def handle_message(
        self,
        message: str,
        sender_id: str,
        sender_name: str,
    ):
        """处理用户消息 - 主要入口之一"""
        logger.debug(f"[PrivateBrain] 收到用户消息: {message[:50]}...")

        # 触发中断（打断阻塞等待）
        self._interrupt_event.set()

        # 标记本次思考由用户消息触发（需要打断 wait）
        self._interrupt_wait_pending = True

        # 触发思考
        await self._schedule_think(f"以下是这一轮思考的新的用户消息: {message}")

    async def _schedule_think(self, prompt: str | None = None):
        """调度一次思考（节流机制：1秒内只触发一次，累积提示词）"""
        # 1. 将提示词加入队列（无论是否立即思考）
        if prompt:
            await self._think_prompt_queue.put(prompt)
            logger.debug(f"[PrivateBrain] 收到思考提示词，已加入队列: {prompt[:50]}...")

        # 2. 如果正在思考中，标记需要再次思考
        if self._thinking:
            self._think_requested = True
            logger.debug("[PrivateBrain] 思考中，标记待思考")
            return

        # 3. 检查冷却时间
        current_time = time.time()
        time_since_last_think = current_time - self._last_think_time

        if time_since_last_think < self._think_cooldown:
            # 在冷却期内，延迟思考
            remaining_cooldown = self._think_cooldown - time_since_last_think

            # 如果已经有延迟定时器，不需要重复创建
            if self._pending_think_timer and not self._pending_think_timer.done():
                logger.debug(
                    f"[PrivateBrain] 冷却中，提示词已累积，等待 {remaining_cooldown:.2f}秒后统一思考"
                )
                return

            # 创建延迟思考定时器
            logger.debug(
                f"[PrivateBrain] 冷却中，延迟 {remaining_cooldown:.2f}秒后思考"
            )
            self._pending_think_timer = asyncio.create_task(
                self._delayed_think(remaining_cooldown)
            )
            return

        # 4. 冷却完成，立即启动思考
        self._last_think_time = current_time
        self._think_task = asyncio.create_task(self._do_think())

    async def _delayed_think(self, delay: float):
        """延迟思考（等待冷却时间后触发）"""
        try:
            await asyncio.sleep(delay)

            # 冷却完成，启动思考
            if not self._thinking:
                self._last_think_time = time.time()
                self._think_task = asyncio.create_task(self._do_think())
                logger.debug("[PrivateBrain] 冷却完成，启动延迟思考")
        except asyncio.CancelledError:
            logger.debug("[PrivateBrain] 延迟思考被取消")
        except Exception as e:
            logger.error(f"[PrivateBrain] 延迟思考异常: {e}")

    async def _do_think(self):
        """执行思考（可能多轮）"""
        self._thinking = True
        try:
            while True:
                self._think_requested = False

                # 进入思考时，检查是否需要打断 wait
                if self._interrupt_wait_pending:
                    await self.executor.stop_by_name("wait", "有新事件到达，打断等待")
                    self._interrupt_wait_pending = False

                # 清理已完成的动作实例
                await self.executor.cleanup_completed()

                # 构建提示词
                prompt = await self._build_prompt()
                ORANGE = "\033[38;5;214m"
                RESET = "\033[0m"
                logger.debug(f"{ORANGE}[PrivateBrain] 思考提示词: {prompt}{RESET}")

                try:
                    if self.llm:
                        llm_response = await self._think(prompt)
                        decisions = parse_decision(llm_response or "")
                        logger.debug(
                            f"[PrivateBrain] LLM 决策: {[d.get('action') for d in decisions]}"
                        )

                        # 调用成功，重置错误计数
                        self._llm_error_count = 0
                    else:
                        decisions = []
                except Exception as e:
                    logger.error(f"[PrivateBrain] LLM 调用失败: {e}")
                    self._llm_error_count += 1

                    if self._llm_error_count >= MAX_LLM_ERROR_COUNT:
                        error_msg = (
                            f"模型配置错误，已连续失败 {self._llm_error_count} 次。"
                            f"\n请检查高级人格的 LLM 模型配置是否正确。"
                        )
                        logger.error(f"[PrivateBrain] {error_msg}")
                        await self._event_queue.put(MindEvent.error(error_msg))
                        break

                    await asyncio.sleep(1)
                    continue

                # 执行决策
                if decisions:
                    for decision in decisions:
                        await self._execute_decision(decision)
                    await asyncio.sleep(0.1)

                # 检查是否需要再次思考
                if not self._think_requested:
                    break

                # 检测是否只有 wait 动作在运行（连续等待）
                running_states = self.executor.get_running_states()
                is_only_wait = (
                    len(running_states) == 1
                    and running_states[0]["action_name"] == "wait"
                )

                if is_only_wait:
                    # 第一次等待，记录时间
                    if self._consecutive_wait_count == 0:
                        self._first_wait_time = time.time()

                    self._consecutive_wait_count += 1
                    logger.debug(
                        f"[PrivateBrain] 检测到连续等待，当前次数: {self._consecutive_wait_count}"
                    )
                else:
                    # 有其他动作运行，重置计数和时间
                    self._consecutive_wait_count = 0
                    self._first_wait_time = 0

                # 超过阈值时，检查时间条件
                stuck_hint = ""
                if self._consecutive_wait_count >= self._consecutive_wait_threshold:
                    # 计算从第一次等待到现在的时间
                    elapsed_time = (
                        time.time() - self._first_wait_time
                        if self._first_wait_time > 0
                        else 0
                    )

                    # 只有当连续等待次数达标且时间超过阈值时才提示
                    if elapsed_time >= self._stuck_min_duration:
                        stuck_hint = STUCK_PROMPT
                        logger.debug(
                            f"[PrivateBrain] 连续等待 {self._consecutive_wait_count} 次，"
                            f"持续 {int(elapsed_time)} 秒，添加结束提示"
                        )

                # 将结束提示加入队列
                if stuck_hint:
                    await self._think_prompt_queue.put(stuck_hint)

        except asyncio.CancelledError:
            logger.info("[PrivateBrain] 思考被取消")
        except Exception as e:
            logger.error(f"[PrivateBrain] 思考异常: {e}")
        finally:
            self._thinking = False
            # 检查是否应该发送 END 事件
            self._maybe_emit_end()

    def _maybe_emit_end(self):
        """检查是否应该发送 END 事件（无动作运行且无待思考）"""
        if (
            not self._thinking
            and not self.executor.has_running()
            and not self._think_requested
        ):
            logger.debug("[PrivateBrain] 思考完成，发送 END 事件")
            asyncio.create_task(self._event_queue.put(MindEvent.end("思考完成")))

    async def get_event_stream(self) -> AsyncGenerator[MindEvent, None]:
        """获取输出事件流

        外部（如 internal_mind.py）通过这个方法获取 MindSim 的输出事件。
        事件流在收到 END 事件后结束。
        """
        self._stream_active = True
        try:
            while True:
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=5)

                    if event.type == MindEventType.END:
                        logger.debug(
                            "[PrivateBrain] 收到 END 事件，关闭事件流"
                        )  # todo这里还要检查是否由运行中的动作，思考，确保结束时候这个类是干净的
                        yield event
                        break

                    yield event

                except asyncio.TimeoutError:
                    # 超时检查：如果无动作运行且无思考，发送 END
                    if not self._thinking and not self.executor.has_running():
                        logger.debug("[PrivateBrain] 超时且空闲，发送 END 事件")
                        yield MindEvent.end(reason="思考超时")
                        break
        finally:
            self._stream_active = False

    async def _think(self, prompt: str) -> str:
        """统一的思考入口：先快速模型评估，按需升级"""
        # 快速模型调用（包含升级思考模块）
        # 使用 call_simple 直接获取文本响应
        fast_response = await self.llm.call_simple(
            prompt=prompt,
            role="fast",
        )
        logger.debug(f"[PrivateBrain] 快速思考结果: {fast_response}")

        need_role = self._parse_need_deeper(fast_response)

        if need_role == "fast":
            return fast_response

        logger.info(f"[PrivateBrain] 升级到 {need_role} 思考")

        # 升级思考时不传入升级模块（避免循环升级）
        upgraded_prompt = await self._build_prompt(include_upgrade=False)
        response = await self.llm.call_simple(
            prompt=upgraded_prompt,
            role=need_role,
        )
        logger.debug(f"[PrivateBrain] {need_role} 思考结果: {response}")
        return response

    @staticmethod
    def _parse_need_deeper(fast_response: str) -> str:
        """从快速模型的输出中解析是否需要升级思考"""
        if not fast_response:
            return "fast"

        match = re.search(r"NEED_DEEPER:\s*(MEDIUM|DEEP)", fast_response, re.IGNORECASE)
        if not match:
            return "fast"

        level_str = match.group(1).upper()
        if level_str == "DEEP":
            return "deep"
        elif level_str == "MEDIUM":
            return "medium"
        return "fast"

    async def _wait_for_interrupt(self, timeout: float) -> str:
        """阻塞主思考，等待中断

        被以下事件打断：
        - 用户消息到达（handle_message 设置 _interrupt_event）
        - 动作产出到达（_on_action_output 设置 _interrupt_event）
        - 超时
        """
        self._interrupt_event.clear()
        try:
            await asyncio.wait_for(self._interrupt_event.wait(), timeout=timeout)
            return "interrupted"
        except asyncio.TimeoutError:
            return "timeout"

    async def _build_prompt(self, include_upgrade: bool = True) -> str:
        """构建思考提示词

        Args:
            include_upgrade: 是否包含升级思考模块（快速模型需要，升级后的模型不需要）
        """
        # 系统提示词
        system_prompt = build_main_thinking_prompt(
            persona=self.persona,
            ctx=self.ctx,
            action_infos=self.executor.get_action_infos(),
        )

        # 当前运行的动作实例状态
        running_states = self.executor.get_running_states()
        states_prompt = (
            build_action_states_prompt(running_states) if running_states else ""
        )

        # 临时提示词
        if include_upgrade:
            temp_contents = self.executor.tick_temp_prompts(consume_rounds=False)
        else:
            temp_contents = self.executor.tick_temp_prompts(consume_rounds=True)

        temp_prompt = build_temp_prompts_section(temp_contents) if temp_contents else ""

        # 最近对话历史（从数据库读取）
        history = []
        if self.ctx.conv_manager and self.ctx.conversation_id:
            conversation = await self.ctx.conv_manager.get_conversation(
                self.ctx.unified_msg_origin, self.ctx.conversation_id
            )
            if conversation and conversation.history:
                history = json.loads(conversation.history)

        # 从聊天配置中获取消息条数，默认为 10
        chat_config = self.ctx.chat_config or {}
        message_length = chat_config.get("message_length", 10)
        if not isinstance(message_length, int) or message_length < 1:
            message_length = 10

        history_prompt = build_history_prompt(history, max_turns=message_length)

        # 决策格式（可选升级思考模块）
        decision_section = DECISION_FORMAT_PROMPT
        if include_upgrade:
            decision_section += UPGRADE_THINKING_PROMPT

        # 传入思考的提示词
        queue_prompts = []
        while not self._think_prompt_queue.empty():
            try:
                prompt = self._think_prompt_queue.get_nowait()
                queue_prompts.append(prompt)
                self._think_prompt_queue.task_done()
            except asyncio.QueueEmpty:
                break
        queue_section = ""
        if queue_prompts:
            queue_section = "【额外思考提示】\n"
            for i, prompt in enumerate(queue_prompts, 1):
                queue_section += f"{i}. {prompt}\n"

        # 使用灵活组装器
        return build_prompt_sections(
            system_prompt,
            states_prompt,
            temp_prompt,
            history_prompt,
            decision_section,
            queue_section,
        )

    async def _execute_decision(self, decision: dict):
        """执行决策"""
        action_type = decision.get("action")

        try:
            if action_type == "START":
                await self._exec_start(decision)
            elif action_type == "SEND":
                await self._exec_send(decision)
            elif action_type == "STOP":
                await self._exec_stop(decision)
        except Exception as e:
            logger.error(f"[PrivateBrain] 执行决策失败: {e}")

    async def _exec_start(self, decision: dict):
        """执行 START 决策"""
        action_name = decision.get("target")
        params = decision.get("params", {})

        if action_name not in self.executor.get_action_class_names():
            logger.warning(f"[PrivateBrain] 未知动作: {action_name}")
            return

        logger.info(f"[PrivateBrain] 启动动作: {action_name}")

        # 通过 executor 启动
        instance_id, pre_result = await self.executor.start(action_name, params)

        # 处理预执行结果
        if pre_result and pre_result.block:
            logger.info(
                f"[PrivateBrain] 动作 {instance_id} 请求阻塞主思考: "
                f"{pre_result.block_reason} (超时 {pre_result.block_timeout}s)"
            )
            result = await self._wait_for_interrupt(pre_result.block_timeout)
            logger.info(f"[PrivateBrain] 阻塞结束: {result}")

    async def _exec_send(self, decision: dict):
        """执行 SEND 决策"""
        target = decision.get("target", "")
        message = decision.get("message", "")

        instance_id = self.executor.resolve_instance_id(target)
        if not instance_id:
            logger.warning(f"[PrivateBrain] 无法解析目标: {target}")
            return

        logger.debug(f"[PrivateBrain] 向实例 {instance_id} 发送消息")
        await self.executor.send_to(
            instance_id,
            ActionSendMsg(
                action_name=instance_id,
                message=message,
            ),
        )

    async def _exec_stop(self, decision: dict):
        """执行 STOP 决策"""
        target = decision.get("target", "")

        instance_id = self.executor.resolve_instance_id(target)
        if not instance_id:
            if target in self.executor.get_action_class_names():
                await self.executor.stop_by_name(target, "主思考决策停止")
            else:
                logger.warning(f"[PrivateBrain] 无法解析目标: {target}")
            return

        logger.info(f"[PrivateBrain] 停止实例: {instance_id}")
        await self.executor.stop_instance(instance_id, "主思考决策停止")
