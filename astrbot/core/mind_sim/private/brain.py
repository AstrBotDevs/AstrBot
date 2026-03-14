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
import re
import time
from collections.abc import AsyncGenerator
from typing import Optional

from astrbot.core import logger
from astrbot.core.mind_sim.action import ActionExecutor, PreExecuteResult
from astrbot.core.mind_sim.context import MindContext
from astrbot.core.mind_sim.llm import MindSimLLM
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
    build_action_states_prompt,
    build_history_prompt,
    build_main_thinking_prompt,
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
        persona: Optional[dict] = None,
        llm: Optional[MindSimLLM] = None,
    ):
        self.ctx = ctx
        self.persona = persona or {}
        self.llm = llm

        # 动作执行器
        self.executor = ActionExecutor(ctx=ctx, send_callback=self._on_action_output)

        # 注册动作类
        for action_cls in get_available_actions():
            self.executor.register(action_cls)

        # 事件输出队列（供外部监听）
        self._event_queue: asyncio.Queue[MindEvent] = asyncio.Queue()

        # 思考状态
        self._thinking = False
        self._think_requested = False
        self._think_task: Optional[asyncio.Task] = None

        # 中断事件（用于阻塞时被用户消息或动作消息打断）
        self._interrupt_event: asyncio.Event = asyncio.Event()

        # 事件流状态
        self._stream_active = False

        # LLM 错误计数
        self._llm_error_count = 0

        logger.debug(
            f"[PrivateBrain] 初始化完成，动作类: {self.executor.get_action_class_names()}"
        )

    async def _on_action_output(self, output):
        """动作产出回调，将产出转为事件放入队列"""
        if isinstance(output, ActionOutput):
            # 根据输出类型转换为对应的 MindEvent
            if output.type == "reply":
                await self._event_queue.put(MindEvent.reply(output.content, output.metadata))
                self._interrupt_event.set()
            elif output.type == "typing":
                await self._event_queue.put(MindEvent.typing())
            elif output.type == "error":
                await self._event_queue.put(MindEvent.error(output.content, output.metadata))
            elif output.type == "completed":
                # 动作完成，触发重新思考
                logger.debug(f"[PrivateBrain] 动作 {output.action_name} 完成，触发重新思考")
                await self._schedule_think()
            elif output.type == "request_think":
                # 动作显式请求重新思考
                logger.debug(f"[PrivateBrain] 动作 {output.action_name} 请求重新思考")
                await self._schedule_think()

        elif isinstance(output, ActionStateUpdate):
            # 状态更新不需要放入事件队列，executor 内部已跟踪
            pass

    def set_llm(self, llm: MindSimLLM):
        """设置 LLM 实例"""
        self.llm = llm

    async def handle_message(
        self,
        message: str,
        sender_id: str,
        sender_name: str,
    ):
        """处理用户消息 - 主要入口之一"""
        # 添加到对话历史
        self.ctx.conversation_history.append(
            {
                "role": "user",
                "content": message,
                "sender_name": sender_name,
                "timestamp": time.time(),
            }
        )
        logger.debug(f"[PrivateBrain] 收到用户消息: {message[:50]}...")

        # 触发中断（打断阻塞等待）
        self._interrupt_event.set()

        # 触发思考
        await self._schedule_think()

    async def _schedule_think(self):
        """调度一次思考（防止并发）"""
        if self._thinking:
            # 正在思考中，标记需要再次思考
            self._think_requested = True
            logger.debug("[PrivateBrain] 思考中，标记待思考")
            return

        # 启动思考任务
        self._think_task = asyncio.create_task(self._do_think())

    async def _do_think(self):
        """执行思考（可能多轮）"""
        self._thinking = True
        try:
            while True:
                self._think_requested = False

                # 清理已完成的动作实例
                await self.executor.cleanup_completed()

                # 构建提示词
                prompt = self._build_prompt()
                logger.debug(f"[PrivateBrain] 思考提示词: {prompt}")

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
        if not self._thinking and not self.executor.has_running() and not self._think_requested:
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
                        logger.debug("[PrivateBrain] 收到 END 事件，关闭事件流")
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
        fast_response = await self.llm.call(prompt=prompt, role="fast")
        logger.debug(f"[PrivateBrain] 快速思考结果: {fast_response[:100]}...")

        need_role = self._parse_need_deeper(fast_response)

        if need_role == "fast":
            return fast_response

        logger.info(f"[PrivateBrain] 升级到 {need_role} 思考")
        response = await self.llm.call(prompt=prompt, role=need_role)
        logger.debug(f"[PrivateBrain] {need_role} 思考结果: {response[:100]}...")
        return response

    @staticmethod
    def _parse_need_deeper(fast_response: str) -> str:
        """从快速模型的输出中解析是否需要升级思考"""
        if not fast_response:
            return "fast"

        match = re.search(
            r"NEED_DEEPER:\s*(MEDIUM|DEEP)", fast_response, re.IGNORECASE
        )
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

    def _build_prompt(self) -> str:
        """构建提示词"""
        sections = []

        # 系统提示词
        system_prompt = build_main_thinking_prompt(
            persona=self.persona,
            ctx=self.ctx,
            action_infos=self.executor.get_action_infos(),
        )
        sections.append(system_prompt)

        # 当前运行的动作实例状态
        running_states = self.executor.get_running_states()
        if running_states:
            states_prompt = build_action_states_prompt(running_states)
            sections.append(states_prompt)

        # 临时提示词
        temp_contents = self.executor.tick_temp_prompts()
        if temp_contents:
            sections.append(build_temp_prompts_section(temp_contents))

        # 最近对话历史
        history_prompt = build_history_prompt(self.ctx.conversation_history)
        sections.append(history_prompt)

        # 决策格式
        sections.append(DECISION_FORMAT_PROMPT)

        return "\n\n---\n\n".join(sections)

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
