"""执行任务动作 - 使用 Agent 执行复杂任务

工作流程：
1. 启动时创建 AgentRunner，执行指定任务
2. 每执行一轮后，触发主思考，让主思考决定下一步
3. 支持通过 SEND 追加新消息/指令
4. 支持通过 STOP 停止任务
5. 任务完成后自动触发重新思考

参数：
- task: 要执行的任务描述（必填）
- max_steps: 最大执行轮数，默认 10
"""

import asyncio
import json
from typing import Any, AsyncGenerator

from astrbot.core import logger
from astrbot.core.astr_main_agent import (
    MainAgentBuildConfig,
    build_main_agent,
)
from astrbot.core.astr_agent_run_util import AgentRunner, run_agent
from astrbot.core.mind_sim import Action, ActionOutput, ActionSendMsg, ActionStopMsg
from astrbot.core.mind_sim.context import MindContext


TOOL_ASSISTANT_PROMPT = """你是一个工具助手。你的任务是根据用户的指令，使用各种工具来完成任务。

## 重要规则
1. 仔细理解用户给你的任务要求
2. 合理选择和使用可用的工具
3. 每使用完一个工具后，根据返回结果决定下一步
4. 如果任务完成或无法继续，及时汇报结果
5. 如果需要更多输入或信息，明确告诉用户

## 与主控制者的交互方式
每执行完一步后，主控制者会决定你的下一步。你可能会收到以下指令：

**追加指令（通过 SEND 发送）：**
主控制者会通过 SEND 给你发送新的指令或信息，例如：
- "继续执行下一个步骤"
- "停止当前操作，改为执行其他任务"
- "给你看看目前的进度"
- "补充更多信息：xxx"

收到追加指令后，你应该：
1. 理解新指令的含义
2. 根据新指令继续执行或调整任务
3. 如果指令让你继续，就继续使用工具完成任务
4. 如果指令让你停止或改变方向，按新指令执行

**停止指令（通过 STOP 发送）：**
如果主控制者发送 STOP，意味着任务被终止，你应该：
1. 立即停止当前操作
2. 总结已完成的工作
3. 告知用户任务已被终止

## 输出格式
- 使用工具时，说明你要做什么
- 每步执行完后，等待主控制者的下一步指令
- 任务完成后或被终止时，总结你做了什么
- 遇到问题时，说明遇到了什么困难

现在开始执行任务："""


class RunTaskAction(Action):
    """执行任务动作 - 使用 Agent 执行复杂任务

    适用于：
    - 需要执行复杂的多步骤任务
    - 需要使用各种工具来完成任务
    - 任务需要多轮交互才能完成

    **每执行完一轮会自动触发主思考，让主思考决定是否继续**
    """

    name = "run_task"
    description = """执行任务动作 - 使用 Agent 执行任务
是解决不了的问题都可以调用这个动作试试看,这是你的手

**重要：每执行完一轮会自动触发主思考**

适用于：
- 执行复杂的多步骤任务
- 需要使用工具查询信息
- 任务需要多轮交互才能完成
- 操作电脑，执行程序，查看电脑上的东西调用控制台等，

工作流程：
1. 你指定任务目标和参数，启动动作
2. 动作执行过程中，每完成一步会触发重新思考
3. 你可以通过 SEND 追加新的指令或信息
4. 你可以通过 STOP 停止任务

参数:
{"task": "任务描述"(不能为空，传递给Agent的指令), "max_steps": 10}
"""
    fixed_prompt = "执行任务中"
    priority = 10  # 高优先级，任务通常比较重要

    usage_guide = """
    - 当需要执行复杂任务时使用
    - 当需要使用工具查询信息时使用
    - 任务会自动执行，每轮结束后会询问你
    - 你可以随时通过 SEND 追加指令或 STOP 停止
    """

    # 存储 AgentRunner 实例
    _agent_runner: AgentRunner | None = None
    _current_step: int = 0
    _max_steps: int = 10
    _task_description: str = ""
    _task_completed: bool = False
    _reply_to_platform: bool = False  # 是否直接回复到平台，默认关闭

    # 存储每步的回复内容，供主思考使用
    _step_responses: list[dict] = []
    _pending_think_reason: str | None = None  # 待触发的思考原因
    _final_result_responses: str = ""

    async def run(self, params: dict) -> AsyncGenerator[ActionOutput, None]:
        """执行任务"""
        self._task_description = params.get("task", "")
        self._max_steps = params.get("max_steps", 10)
        self._reply_to_platform = params.get("reply_to_platform", False)  # 从参数获取开关
        self._step_responses = []  # 重置

        if not self._task_description:
            yield ActionOutput(
                action_name=self.instance_id or self.name,
                type="error",
                content="任务描述不能为空",
            )
            return

        self.update_state(
            progress=f"执行任务中: {self._task_description[:30]}...",
            prompt_contribution=f"正在执行任务: {self._task_description}",
            data={
                "task": self._task_description,
                "max_steps": self._max_steps,
            },
        )

        logger.info(f"[RunTask] 开始执行任务: {self._task_description}")

        try:
            # 构建 AgentRunner（使用和 internal.py 完全相同的配置）
            self._agent_runner = await self._build_agent_runner()

            if not self._agent_runner:
                yield ActionOutput(
                    action_name=self.instance_id or self.name,
                    type="error",
                    content="无法创建 Agent，请检查配置",
                )
                return

            # 执行任务循环（async generator 需要直接迭代）
            async for output in self._run_task_loop():
                yield output

        except Exception as e:
            logger.error(f"[RunTask] 执行出错: {e}")
            yield ActionOutput(
                action_name=self.instance_id or self.name,
                type="error",
                content=f"执行出错: {str(e)}",
            )

    async def _build_agent_runner(self) -> AgentRunner | None:
        """构建 AgentRunner（使用和 internal.py 完全相同的配置）"""
        # 从上下文中获取必要的信息
        ctx = self.ctx
        if not ctx:
            logger.error("[RunTask] 上下文为空")
            return None

        # 获取 event 和 plugin_context
        event = ctx.event
        plugin_context = ctx.plugin_context

        if not event or not plugin_context:
            logger.error("[RunTask] event 或 plugin_context 为空")
            return None

        # 获取配置
        conf = plugin_context.get_config()
        settings = conf.get("provider_settings", {})

        # 构建主代理配置
        main_agent_cfg = MainAgentBuildConfig(
            tool_call_timeout=settings.get("tool_call_timeout", 60),
            streaming_response=False,  # 禁用流式响应
            tool_schema_mode=settings.get("tool_schema_mode", "full"),
            sanitize_context_by_modalities=settings.get("sanitize_context_by_modalities", False),
            kb_agentic_mode=conf.get("kb_agentic_mode", False),
            file_extract_enabled=settings.get("file_extract", {}).get("enable", False),
            context_limit_reached_strategy=settings.get("context_limit_reached_strategy", "truncate_by_turns"),
            llm_compress_instruction=settings.get("llm_compress_instruction", ""),
            llm_compress_keep_recent=settings.get("llm_compress_keep_recent", 4),
            max_context_length=settings.get("max_context_length", 128000),
            dequeue_context_length=settings.get("dequeue_context_length", 20),
            llm_safety_mode=settings.get("llm_safety_mode", True),
            safety_mode_strategy=settings.get("safety_mode_strategy", "system_prompt"),
            computer_use_runtime=settings.get("computer_use_runtime"),
            sandbox_cfg=settings.get("sandbox", {}),
            add_cron_tools=settings.get("proactive_capability", {}).get("add_cron_tools", True),
            provider_settings=settings,
            subagent_orchestrator=conf.get("subagent_orchestrator", {}),
            timezone=conf.get("timezone"),
            max_quoted_fallback_images=settings.get("max_quoted_fallback_images", 20),
        )

        # 构建 AgentRunner
        # 不传 req，让 build_main_agent 自己构建，之后覆盖 system_prompt
        build_result = await build_main_agent(
            event=event,
            plugin_context=plugin_context,
            config=main_agent_cfg,
            apply_reset=False,
        )

        if build_result:
            # 强制覆盖 system_prompt，只使用工具助手提示词，不使用人格配置
            build_result.provider_request.system_prompt = TOOL_ASSISTANT_PROMPT

            # 如果 apply_reset=False，需要手动调用 reset
            if build_result.reset_coro:
                await build_result.reset_coro

            # 覆盖 agent_runner 内部的 req
            build_result.agent_runner.req.system_prompt = TOOL_ASSISTANT_PROMPT
            return build_result.agent_runner

        return None

    def _on_agent_step(self, step_idx: int, resp_type: str, resp_data: Any) -> None:
        """run_agent 的回调，处理每步的消息"""
        if resp_type == "tool_call":
            # 工具调用
            msg_chain = resp_data.get("chain")
            tool_name = "unknown"
            if msg_chain:
                for comp in msg_chain.chain:
                    if hasattr(comp, "data") and isinstance(comp.data, dict):
                        tool_name = comp.data.get("name", "unknown")
                        break
            self._append_prompt_contribution(f"[使用工具: {tool_name}]")
            self._pending_think_reason = f"Agent使用了工具 {tool_name}"

        elif resp_type == "tool_call_result":
            # 工具结果
            msg_chain = resp_data.get("chain")
            result = msg_chain.get_plain_text() if msg_chain else ""
            self._append_prompt_contribution(f"[工具返回结果]{result}")
            self._pending_think_reason = f"工具返回了结果{result}"

        elif resp_type == "llm_result":
            # LLM 回复
            msg_chain = resp_data.get("chain")
            content = msg_chain.get_plain_text() if msg_chain else ""
            if content:
                self._append_prompt_contribution(f"[Agent回复: {content}]")
                # 存储到列表
                self._step_responses.append({
                    "step": step_idx,
                    "type": "reply",
                    "content": content,
                })
                self._pending_think_reason = f"Agent回复了: {content}..."

        elif resp_type == "done":
            # 任务完成
            self._task_completed = True
            final_resp = self._agent_runner.get_final_llm_resp()
            if final_resp and final_resp.completion_text:
                self._final_result_responses = final_resp.completion_text
                self._append_prompt_contribution(
                    f"[任务完成，最终回复: {final_resp.completion_text}...]"
                )
            else:
                self._append_prompt_contribution("[任务已完成]")
            self._pending_think_reason = "任务已完成"
    async def _run_task_loop(self) -> AsyncGenerator[ActionOutput, None]:
        """执行任务循环

        直接调用 run_agent 一次，内部会循环执行 max_step 步：
        - 通过回调 _on_agent_step 收集每步的消息
        - 消息追加到 prompt_contribution
        - 完成后触发主思考
        """
        if not self._agent_runner:
            return

        self._current_step = 0

        logger.info(f"[RunTask] 开始执行任务，最大 {self._max_steps} 步")

        self.update_state(
            progress=f"执行任务中: {self._task_description[:30]}...",
            data={
                "task": self._task_description,
                "max_steps": self._max_steps,
            },
        )

        try:
            # 直接调用 run_agent 执行所有步
            async for _ in run_agent(
                self._agent_runner,
                max_step=self._max_steps,
                show_tool_use=False,
                show_tool_call_result=False,
                stream_to_general=True,  # 忽略流式内容
                step_callback=self._on_agent_step,
            ):
                # 检查是否有待触发的思考
                if self._pending_think_reason:
                    reason = self._pending_think_reason
                    self._pending_think_reason = None  # 清空
                    yield ActionOutput(
                        action_name=self.instance_id or self.name,
                        type="request_think",
                        content=reason,
                        prompt=reason,  # 传给 Brain 的原因
                    )

            # 检查是否完成
            if self._agent_runner.done():
                logger.info("[RunTask] 任务完成")
            else:
                logger.info("[RunTask] 任务未完成")

        except Exception as e:
            logger.error(f"[RunTask] 执行出错: {e}")
            self._append_prompt_contribution(f"[执行出错: {str(e)}]")
            yield ActionOutput(
                action_name=self.instance_id or self.name,
                type="error",
                content=f"执行出错: {str(e)}",
            )
            return

        # 任务完成，触发主思考
        yield ActionOutput(
            action_name=self.instance_id or self.name,
            type="completed",
            content=f"任务执行完成: {self._task_description}",
            metadata={
                "max_steps": self._max_steps,
                "completed": self._task_completed,
            },
        )

    def _append_prompt_contribution(self, suffix: str) -> None:
        """追加 prompt_contribution（而不是覆盖）"""
        current = self._state.prompt_contribution or ""
        if current:
            self.update_state(prompt_contribution=f"{current} {suffix}")
        else:
            self.update_state(prompt_contribution=f"可以在合适的时候向聊天对象汇报进度:执行任务中： {self._task_description} {suffix}")

    async def on_complete(self, params: dict) -> None:
        """完成后添加临时提示词（仅正常完成时调用）"""
        # 构建任务执行摘要
        summary_parts = [f"任务: {self._task_description}"]

        # 2. 每次 Agent 回复
        if self._step_responses:
            summary_parts.append(f"\nAgent 执行过程（共 {len(self._step_responses)} 轮）:")
            for i, response in enumerate(self._step_responses, 1):
                # 截取前200字符避免过长
                content = str(response)[:200] + "..." if len(str(response)) > 200 else str(response)
                summary_parts.append(f"  第{i}轮: {content}")

        # 3. 最终结果
        final_result = self._final_result_responses

        if final_result:
            result_preview = final_result
            summary_parts.append(f"\n最终结果: {result_preview}")

        # 4. 完成状态
        if self._task_completed:
            summary_parts.append("\n状态: 任务已完成")
        else:
            summary_parts.append(f"\n状态: 已执行 {len(self._step_responses)} 轮，未完全完成")

        # 将摘要添加为临时提示词（保留5轮思考）
        summary = "\n".join(summary_parts)
        self.add_temp_prompt(f"run_task 执行结果:\n{summary}", rounds=5)

    def on_message(self, msg: ActionSendMsg) -> None:
        """处理接收到的消息"""
        logger.info(f"[RunTask] 收到消息: {msg.message[:50]}...")

    async def on_stop(self) -> None:
        """停止时清理资源"""
        if self._agent_runner:
            try:
                self._agent_runner.request_stop()
            except Exception as e:
                logger.error(f"[RunTask] 停止时出错: {e}")
