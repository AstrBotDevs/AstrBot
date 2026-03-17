"""Action 基类定义 + ActionExecutor 执行器

动作是独立运行的协程，通过消息与主思考通信。
ActionExecutor 统一管理所有运行中的动作实例，支持同一动作多实例并发。
"""

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Callable

from astrbot.core import logger

from .messages import (
    ActionOutput,
    ActionSendMsg,
    ActionStopMsg,
    ActionState,
    ActionStateUpdate,
    MindMessage,
)


# ========== 预执行相关数据类 ==========


@dataclass
class TempPrompt:
    """临时提示词 - 在指定轮数和时间内附加到主思考提示词

    由动作添加（before_execute 或运行中），每轮思考消耗一次，
    remaining_rounds 降到 0 且超过 min_duration 后自动移除。

    Attributes:
        content: 提示词内容
        remaining_rounds: 剩余有效轮数
        min_duration: 最小保留时间（秒），默认 30 秒
        created_at: 创建时间戳
        source: 来源标识（如 "reply#1"、"wait#2"）
    """

    content: str
    remaining_rounds: int
    min_duration: float = 30.0  # 最小保留时间（秒）
    created_at: float = field(default_factory=time.time)
    source: str = ""  # 来源动作实例 ID


@dataclass
class PreExecuteResult:
    """动作预执行结果 - 在动作 run() 之前返回，影响主思考

    Attributes:
        temp_prompts: 临时提示词列表（N轮后自动消失）
        block: 是否阻塞主思考循环（等待中断）
        block_timeout: 阻塞超时（秒）
        block_reason: 阻塞原因描述（给日志用）
    """

    temp_prompts: list[TempPrompt] = field(default_factory=list)
    block: bool = False
    block_timeout: float = 60.0
    block_reason: str = ""


# ========== Action 基类 ==========


class Action(ABC):
    """动作基类

    动作是独立运行的协程，具有以下特性：
    1. 独立运行：作为 asyncio.Task 运行，不阻塞主思考
    2. 状态可见：state 随时可被主思考读取
    3. 双向通信：可以接收主思考消息，也可以发送产出
    4. 提示词贡献：可以贡献静态和动态提示词
    5. 预执行钩子：run() 之前可以影响主思考（临时提示词、阻塞等）

    子类需要实现：
    - run(): 核心逻辑
    - before_execute(): 可选，预执行钩子
    """

    # 类属性：动作元信息
    name: str = "base"  # 动作名称（类型标识，非实例标识）
    description: str = ""  # 动作描述（给主思考看的）
    usage_guide: str = ""  # 使用条件/指南
    fixed_prompt: str = ""  # 固定提示词贡献（静态）
    priority: int = 0  # 优先级（用于排序显示）

    def __init__(self):
        self.ctx: Any = None  # MindContext，由 mind_sim 注入
        self.llm: Any = None  # MindSimLLM，由 mind_sim 注入
        self.instance_id: str = ""  # 运行时分配的实例 ID（如 reply#1）
        self.inbox: asyncio.Queue[MindMessage] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._state: ActionState = ActionState(action_name=self.name)
        self._send_callback: Callable | None = None
        self._temp_prompt_callback: Callable | None = None
        self._executor: Any = None  # ActionExecutor 引用，由 executor 注入
        self._params: dict = {}  # 保存启动参数，用于 on_complete

    def bind_context(self, ctx: Any) -> "Action":
        """绑定上下文（由 ActionExecutor 调用）"""
        self.ctx = ctx
        return self

    def bind_llm(self, llm: Any) -> "Action":
        """绑定 LLM（由 ActionExecutor 调用）"""
        self.llm = llm
        return self

    @property
    def state(self) -> ActionState:
        """获取当前状态（主思考会读取）"""
        return self._state

    def update_state(
        self,
        status: str | None = None,
        progress: str | None = None,
        data: dict | None = None,
        prompt_contribution: str | None = ...,  # ... 表示未提供，None 表示清空
        can_receive: bool | None = None,
        error: str | None = None,
    ):
        """更新状态"""
        if status is not None:
            self._state.status = status
        if progress is not None:
            self._state.progress = progress
        if data is not None:
            self._state.data.update(data)
        if prompt_contribution is not ...:
            self._state.prompt_contribution = prompt_contribution
        if can_receive is not None:
            self._state.can_receive = can_receive
        if error is not None:
            self._state.error = error
        self._state.updated_at = time.time()

    def set_send_callback(self, callback: Callable):
        """设置发送回调（由 ActionExecutor 调用）"""
        self._send_callback = callback

    def set_temp_prompt_callback(self, callback: Callable):
        """设置临时提示词回调（由 ActionExecutor 调用）"""
        self._temp_prompt_callback = callback

    def add_temp_prompt(self, content: str, rounds: int = 5, min_duration: float = 30.0) -> None:
        """添加临时提示词（动作运行中调用）

        Args:
            content: 提示词内容
            rounds: 有效轮数（默认5轮）
            min_duration: 最小保留时间（秒），默认30秒
        """
        if hasattr(self, "_temp_prompt_callback") and self._temp_prompt_callback:
            self._temp_prompt_callback(
                TempPrompt(
                    content=content,
                    remaining_rounds=rounds,
                    min_duration=min_duration,
                    source=self.instance_id or self.name,
                )
            )

    async def send_to_main(self, output: ActionOutput):
        """发送产出给主思考"""
        if self._send_callback:
            state_update = ActionStateUpdate(
                action_name=self.instance_id or self.name,
                state=self._state,
            )
            await self._send_callback(state_update)
            await self._send_callback(output)

    async def receive(self, msg: MindMessage):
        """接收主思考发来的消息"""
        await self.inbox.put(msg)

    async def check_message(self, timeout: float = 0) -> MindMessage | None:
        """检查是否有来自主思考的消息

        Args:
            timeout: 超时时间（秒）。0 表示非阻塞检查。

        Returns:
            MindMessage 或 None
        """
        try:
            if timeout > 0:
                return await asyncio.wait_for(self.inbox.get(), timeout=timeout)
            elif self.inbox.empty():
                return None
            else:
                return self.inbox.get_nowait()
        except asyncio.QueueEmpty:
            return None
        except asyncio.TimeoutError:
            return None

    async def before_execute(self, params: dict) -> PreExecuteResult | None:
        """预执行钩子 - 在 run() 之前被主思考调用

        可以用来影响主思考，例如：
        - 给接下来 N 轮加上临时提示词（如 "你在 X 轮之前回复了"）
        - 阻塞主思考循环（等待用户消息或动作消息打断）

        Args:
            params: 启动参数（来自 START 决策的 JSON 参数）

        Returns:
            PreExecuteResult 或 None（无影响）
        """
        return None

    async def on_complete(self, params: dict) -> None:
        """完成钩子 - 在 run() 完成（正常完成、非停止）后调用

        可以用来添加临时提示词，例如：
        - "已回复 xxx"
        - "已等待 xxx 秒"

        Args:
            params: 启动参数（来自 START 决策的 JSON 参数）
        """
        pass

    def get_completion_output(self) -> ActionOutput | None:
        """获取完成后要发送的事件

        子类可以重写此方法来定义完成后的行为：
        - 返回 ActionOutput: 发送该事件（type="completed" 会触发重新思考）
        - 返回 None: 不发送任何事件，不触发重新思考

        默认行为：发送 type="completed" 的事件，触发主思考重新思考

        Returns:
            ActionOutput 或 None
        """
        return ActionOutput(
            action_name=self.instance_id or self.name,
            type="completed",
            content="",
        )

    @abstractmethod
    async def run(self, params: dict) -> AsyncGenerator[ActionOutput, None]:
        """运行动作（子类实现）

        Args:
            params: 启动参数（来自主思考的 START 决策）

        Yields:
            ActionOutput: 产出

        注意：
            - 应该定期 check_message() 检查主思考发来的消息
            - 收到 ActionStopMsg 应该清理并退出
            - 收到 ActionSendMsg 应该根据消息调整行为
        """
        ...

    async def start(self, params: dict) -> asyncio.Task:
        """启动动作（由 ActionExecutor 调用）"""
        self._state = ActionState(
            action_name=self.instance_id or self.name,
            status="running",
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._task = asyncio.create_task(self._run_wrapper(params))
        return self._task

    async def _run_wrapper(self, params: dict):
        """包装 run()，处理状态更新和异常"""
        self._params = params  # 保存参数供 on_complete 使用
        try:
            async for output in self.run(params):
                await self.send_to_main(output)
            self._state.status = "completed"
            self._state.prompt_contribution = None

            # 调用完成钩子（添加临时提示词等）
            await self.on_complete(params)

            # 获取子类定义的完成事件（可能为 None）
            completion_output = self.get_completion_output()
            if completion_output:
                await self.send_to_main(completion_output)
        except asyncio.CancelledError:
            self._state.status = "stopped"
            self._state.prompt_contribution = None
            raise
        except Exception as e:
            self._state.status = "error"
            self._state.error = str(e)
            self._state.prompt_contribution = None
            await self.send_to_main(
                ActionOutput(
                    action_name=self.instance_id or self.name,
                    type="error",
                    content=f"动作执行出错: {e}",
                    metadata={"error": str(e)},
                )
            )

    async def stop(self, reason: str = ""):
        """停止动作"""
        if self._task and not self._task.done():
            self._task.cancel()
            # 不 await task，避免等待阻塞中的 check_message 超时
        self._state.status = "stopped"
        self._state.progress = f"已停止: {reason}" if reason else "已停止"

    def is_running(self) -> bool:
        """是否正在运行"""
        return self._state.status == "running"

    def is_done(self) -> bool:
        """是否已完成（包括成功、停止、错误）"""
        return self._state.status in ("completed", "stopped", "error")

    def get_info(self) -> dict:
        """获取动作信息（给主思考看）"""
        return {
            "name": self.name,
            "description": self.description,
            "fixed_prompt": self.fixed_prompt,
            "priority": self.priority,
            "status": self._state.status,
        }


# ========== 运行中动作实例 ==========


@dataclass
class RunningAction:
    """正在运行的动作实例"""

    instance_id: str  # 唯一实例 ID（如 reply#1, reply#2）
    action_name: str  # 动作类名（如 reply）
    action: Action  # 动作实例
    task: asyncio.Task  # asyncio 任务
    started_at: float = field(default_factory=time.time)


# ========== ActionExecutor 动作执行器 ==========


class ActionExecutor:
    """动作执行器 - 统一管理正在运行的动作实例

    核心职责：
    1. 注册动作类（Action 子类），作为工厂按需创建实例
    2. 启动动作实例（同一动作可多次启动，通过 instance_id 区分）
    3. 向运行中的实例发送消息 / 停止实例
    4. 自动清理已完成的实例
    5. 管理临时提示词（由动作的 before_execute 添加）
    6. 提供运行中动作的状态摘要（给 prompts 用）

    instance_id 格式：<动作名>#<序号>，如 reply#1, reply#2, wait#1
    """

    def __init__(self, ctx: Any, send_callback: Callable, llm: Any = None):
        """初始化执行器

        Args:
            ctx: MindContext 会话上下文（绑定到每个新建的动作实例）
            send_callback: 动作产出回调（连接到 Brain 的事件队列）
            llm: MindSimLLM 实例，供动作调用 LLM
        """
        self._action_classes: dict[str, type[Action]] = {}
        self._running: dict[str, RunningAction] = {}
        self._counter: dict[str, int] = {}  # 动作名 → 累计计数
        self._ctx = ctx
        self._send_callback = send_callback
        self._llm = llm
        self._temp_prompts: list[TempPrompt] = []

    def _add_temp_prompt(self, temp_prompt: TempPrompt) -> None:
        """添加临时提示词（由 Action.add_temp_prompt 回调）"""
        self._temp_prompts.append(temp_prompt)
        logger.debug(
            f"[ActionExecutor] 添加临时提示词 (来源: {temp_prompt.source}, "
            f"剩余轮数: {temp_prompt.remaining_rounds}): {temp_prompt.content[:50]}..."
        )

    def register(self, action_cls: type[Action]):
        """注册动作类"""
        self._action_classes[action_cls.name] = action_cls
        logger.debug(f"[ActionExecutor] 注册动作类: {action_cls.name}")

    def get_action_class_names(self) -> list[str]:
        """获取所有已注册的动作类名"""
        return list(self._action_classes.keys())

    def get_action_infos(self) -> list[dict]:
        """获取所有动作类的元信息（给 prompts 用，展示可用动作列表）

        Returns:
            按 priority 降序排列的动作元信息列表
        """
        infos = []
        for name, cls in self._action_classes.items():
            # 统计该动作当前运行中的实例数
            running_count = sum(
                1
                for r in self._running.values()
                if r.action_name == name and r.action.is_running()
            )
            infos.append(
                {
                    "name": cls.name,
                    "description": cls.description or "",
                    "usage_guide": cls.usage_guide or "",
                    "fixed_prompt": cls.fixed_prompt or "",
                    "priority": cls.priority,
                    "running_count": running_count,
                }
            )
        return sorted(infos, key=lambda x: x["priority"], reverse=True)

    async def start(
        self, action_name: str, params: dict
    ) -> tuple[str, PreExecuteResult | None]:
        """启动动作实例

        Args:
            action_name: 动作类名（如 "reply"）
            params: 启动参数

        Returns:
            (instance_id, pre_execute_result)

        Raises:
            ValueError: 未知动作类名
        """
        cls = self._action_classes.get(action_name)
        if not cls:
            raise ValueError(f"未知动作: {action_name}")

        # 创建新实例
        instance = cls()
        instance.bind_context(self._ctx)
        instance.bind_llm(self._llm)
        instance.set_send_callback(self._send_callback)
        instance.set_temp_prompt_callback(self._add_temp_prompt)
        instance._executor = self

        # 生成唯一 instance_id
        count = self._counter.get(action_name, 0) + 1
        self._counter[action_name] = count
        instance_id = f"{action_name}#{count}"
        instance.instance_id = instance_id

        # 调用预执行钩子
        pre_result = await instance.before_execute(params)
        if pre_result and pre_result.temp_prompts:
            self._temp_prompts.extend(pre_result.temp_prompts)

        # 启动动作
        task = await instance.start(params)
        self._running[instance_id] = RunningAction(
            instance_id=instance_id,
            action_name=action_name,
            action=instance,
            task=task,
        )

        logger.info(f"[ActionExecutor] 启动动作实例: {instance_id}")
        return instance_id, pre_result

    async def send_to(self, instance_id: str, msg: MindMessage):
        """向指定实例发送消息"""
        running = self._running.get(instance_id)
        if running and running.action.is_running():
            await running.action.receive(msg)
        else:
            logger.warning(
                f"[ActionExecutor] 无法发送消息到 {instance_id}: 实例不存在或已停止"
            )

    async def stop_instance(self, instance_id: str, reason: str = ""):
        """停止指定实例"""
        running = self._running.get(instance_id)
        if running:
            await running.action.stop(reason)
            logger.info(f"[ActionExecutor] 停止实例: {instance_id}")
        else:
            logger.warning(f"[ActionExecutor] 无法停止 {instance_id}: 实例不存在")

    async def stop_by_name(self, action_name: str, reason: str = ""):
        """停止指定动作名的所有实例"""
        for iid, running in list(self._running.items()):
            if running.action_name == action_name and running.action.is_running():
                await running.action.stop(reason)
                logger.info(f"[ActionExecutor] 按名称停止实例: {iid}")

    async def cleanup_completed(self) -> list[str]:
        """清理已完成的动作实例

        Returns:
            被清理的 instance_id 列表
        """
        to_remove = [
            iid for iid, r in self._running.items() if r.action.is_done()
        ]
        for iid in to_remove:
            del self._running[iid]
        if to_remove:
            logger.debug(f"[ActionExecutor] 清理已完成实例: {to_remove}")
        return to_remove

    def get_running_states(self) -> list[dict]:
        """获取所有运行中动作的状态（给 prompts 用）

        Returns:
            运行中实例的状态列表，每项包含:
            - instance_id: 实例 ID
            - action_name: 动作类名
            - state: ActionState 对象
        """
        states = []
        for iid, running in self._running.items():
            if running.action.is_running():
                states.append(
                    {
                        "instance_id": iid,
                        "action_name": running.action_name,
                        "state": running.action.state,
                    }
                )
        return states

    def tick_temp_prompts(self, consume_rounds: bool = True) -> list[str]:
        """消耗一轮临时提示词

        返回本轮生效的临时提示词内容列表（带时间信息），
        同时将剩余轮数减 1，清除已过期的（轮数为0且超过最小保留时间）。

        格式："[距离现在Xs] 原始内容"

        Args:
            consume_rounds: 是否消耗轮数，默认 True

        Returns:
            本轮生效的临时提示词内容（带时间戳）
        """
        import time

        now = time.time()
        active = []
        remaining = []
        for tp in self._temp_prompts:
            elapsed = now - tp.created_at

            # 检查是否应该保留：轮数 > 0 或者未达到最小保留时间
            should_keep = tp.remaining_rounds > 0 or elapsed < tp.min_duration

            if should_keep:
                # 格式化时间显示
                elapsed_int = int(elapsed)
                if elapsed_int < 60:
                    time_str = f"{elapsed_int}秒"
                elif elapsed_int < 3600:
                    time_str = f"{elapsed_int // 60}分{elapsed_int % 60}秒"
                else:
                    time_str = f"{elapsed_int // 3600}小时{(elapsed_int % 3600) // 60}分"

                # 添加时间信息
                formatted = f"[{tp.source} 已完成，距离现在 {time_str}] {tp.content}"
                active.append(formatted)

                if consume_rounds:
                    tp.remaining_rounds -= 1
                    # 只有轮数 > 0 或未达到最小时间才保留
                    if tp.remaining_rounds > 0 or elapsed < tp.min_duration:
                        remaining.append(tp)
                else:
                    remaining.append(tp)

        if consume_rounds:
            self._temp_prompts = remaining
        return active

    def has_running(self) -> bool:
        """是否有动作正在运行"""
        return any(r.action.is_running() for r in self._running.values())

    async def stop_all(self, reason: str = ""):
        """停止所有动作"""
        for running in self._running.values():
            if running.action.is_running():
                await running.action.stop(reason)
        self._running.clear()
        logger.info("[ActionExecutor] 已停止所有动作")

    def resolve_instance_id(self, target: str) -> str | None:
        """解析目标标识为 instance_id

        支持两种输入：
        - 直接 instance_id: "reply#1" → "reply#1"
        - 动作名（取最新的运行中实例）: "reply" → "reply#2"

        Returns:
            instance_id 或 None
        """
        # 直接匹配
        if target in self._running:
            return target

        # 按动作名匹配（取最新的运行中实例）
        candidates = [
            (iid, r)
            for iid, r in self._running.items()
            if r.action_name == target and r.action.is_running()
        ]
        if candidates:
            candidates.sort(key=lambda x: x[1].started_at, reverse=True)
            return candidates[0][0]

        return None
