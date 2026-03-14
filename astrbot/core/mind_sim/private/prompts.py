"""MindSim 提示词模块 - 动作决策和思考相关提示词

包含：
- 决策格式提示词（支持 instance_id）
- 可用动作描述提示词（从 Action 元信息动态生成）
- 主思考系统提示词（从 Personality 配置读取）
- 动作实例状态提示词（基于 instance_id）
- 临时提示词渲染
- 对话历史提示词（带日期时间）
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.db.po import Personality
    from astrbot.core.mind_sim.context import MindContext


# ========== 决策格式提示词 ==========

DECISION_FORMAT_PROMPT = """
## 决策输出格式

你需要在回复中做出决策来控制你的行为。每行一个决策，格式如下：
JSON参数由动作描述决定
```
START <动作名> <JSON参数>            # 启动新动作实例
SEND <动作名或实例ID> <消息内容>      # 向运行中的动作发消息
STOP <动作名或实例ID>                 # 停止动作
```

### 实例 ID
每个启动的动作会被分配一个唯一的实例 ID，格式为 `<动作名>#<序号>`。
例如启动两次 reply，会分别得到 `reply#1` 和 `reply#2`。
SEND 和 STOP 可以用实例 ID 精确控制某个特定实例，也可以用动作名控制最新的实例。

### 示例
```
START reply {"text": "你好！"}
START reply {"text": "让我想想..."}
SEND reply#1 追加一些内容
STOP reply#2
START wait {"duration": 30}
```

### 升级思考
如果你觉得当前场景太复杂（正在执行的动作过多、动作之间有冲突或依赖、需要更深入的推理），
你可以在输出中加一行请求升级思考，系统会用更强的模型重新思考：
```
NEED_DEEPER: MEDIUM    # 请求中度思考（中等复杂度）
NEED_DEEPER: DEEP      # 请求深度思考（高复杂度）
```
注意：如果你输出了 NEED_DEEPER，当前这次的决策会被丢弃，由更强模型重新决策。
所以只在你确实觉得自己处理不好的时候才请求升级。

### 注意事项
1. 同一动作可以多次启动，互不阻塞（如同时发多条回复）
2. 用 SEND 可以影响正在运行的动作，引导其行为
3. 动作的状态会在下一轮思考时显示给你
4. 动作执行完成后会自动结束，不需要手动 STOP
5. 当不知道做什么时，可以使用 START wait {"duration": 60} 等待
"""


# ========== 主思考系统提示词模板 ==========

MAIN_THINKING_SYSTEM_PROMPT = """你是{bot_name}，一个具有自主思考能力的 AI 助手。

## 你的特点
{personality_traits}
## 表达风格
{expression_style}
## 当前状态
- 当前时间：{current_time}
- 聊天对象：{chat_target}
- 私聊/群聊：{chat_type}
## 核心能力
你可以通过启动不同的动作来增强你的能力。
**重要：同一动作可以多次启动并行运行**，系统会用实例 ID 区分（如 reply#1, reply#2）。
你可以同时启动多个不同的动作，它们会并行执行，互不阻塞。
## 决策原则
1. **优先使用动作**来获取信息或执行任务
2. **可以同时启动多个动作**，例如同时发送多条回复、同时执行多个任务
3. 如果动作正在进行中，可以通过 SEND 来引导其行为
4. 适时使用 wait 动作来等待对方回复或收集更多信息
5. reply 动作用于直接回复用户
6. 保持自然、有趣的对话风格
{action_options}
{decision_format}
"""


def build_main_thinking_prompt(
    persona: "Personality",
    ctx: "MindContext",
    action_infos: list[dict],
) -> str:
    """构建主思考系统提示词

    直接从 Personality 高级人格配置和 MindContext 读取所有参数，
    动作选项从 ActionExecutor.get_action_infos() 动态生成。

    Args:
        persona: Personality 人格配置
        ctx: MindContext 会话上下文
        action_infos: 动作元信息列表（来自 executor.get_action_infos()）

    Returns:
        完整的系统提示词
    """
    # 从 personality_config 提取人格特质和表达风格
    personality_config = persona.get("personality_config") or {}
    traits = personality_config.get("traits", "")
    expression_style = personality_config.get("expression_style", "")

    # 从 robot_config 提取机器人名称
    robot_config = persona.get("robot_config") or {}
    bot_name = robot_config.get("name") or persona.get("name", "助手")

    # 从上下文获取聊天信息
    chat_target = ctx.user_name or "用户"
    chat_type = "私聊" if ctx.is_private else "群聊"
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 动态构建动作选项
    action_options = build_action_options_prompt(action_infos)

    return MAIN_THINKING_SYSTEM_PROMPT.format(
        bot_name=bot_name,
        personality_traits=traits or "善良、智能、有趣",
        expression_style=expression_style or "自然、友好",
        current_time=current_time,
        chat_target=chat_target,
        chat_type=chat_type,
        action_options=action_options,
        decision_format=DECISION_FORMAT_PROMPT,
    )


# ========== 动作选项提示词 ==========

ACTION_OPTIONS_TEMPLATE = """
## 可用动作
{actions_description}
"""


def build_action_options_prompt(action_infos: list[dict]) -> str:
    """从动作元信息列表动态构建可用动作提示词

    按 priority 降序排列，拼接 description 和 usage_guide。

    Args:
        action_infos: 动作元信息列表（来自 executor.get_action_infos()）

    Returns:
        动作选项提示词
    """
    if not action_infos:
        return "暂无可用动作"

    # 已按 priority 降序排列（executor.get_action_infos 已排序）
    lines = []
    for info in action_infos:
        name = info["name"]
        running_count = info.get("running_count", 0)
        status = f"（{running_count} 个实例运行中）" if running_count > 0 else ""

        lines.append(f"### {name} {status}")
        if info["description"]:
            lines.append(f"{info['description']}")
        if info["usage_guide"]:
            lines.append(f"使用指南：{info['usage_guide']}")
        if info["fixed_prompt"] and running_count > 0:
            lines.append(f"运行时提示：{info['fixed_prompt']}")
        lines.append("")

    return ACTION_OPTIONS_TEMPLATE.format(actions_description="\n".join(lines))


# ========== 动作实例状态提示词 ==========

ACTION_STATES_TEMPLATE = """
## 当前运行的动作实例
{running_instances}
"""


def build_action_states_prompt(running_states: list[dict]) -> str:
    """构建当前动作实例状态提示词

    基于 instance_id 展示每个运行中实例的状态。

    Args:
        running_states: 运行中实例状态列表（来自 executor.get_running_states()）
            每项包含: instance_id, action_name, state (ActionState)

    Returns:
        动作实例状态提示词
    """
    if not running_states:
        return ""

    lines = []
    for item in running_states:
        instance_id = item["instance_id"]
        state = item["state"]

        lines.append(f"### {instance_id}")

        # 支持 ActionState 对象和 dict 两种格式
        if isinstance(state, dict):
            status = state.get("status", "")
            if status != "running":
                continue
            lines.append(f"状态：{status}")
            progress = state.get("progress")
            if progress:
                lines.append(f"进度：{progress}")
            prompt_contribution = state.get("prompt_contribution")
            if prompt_contribution:
                lines.append(f"详情：{prompt_contribution}")
            data = state.get("data", {})
            if data:
                key_data = {
                    k: v for k, v in data.items() if not k.startswith("_")
                }
                if key_data:
                    lines.append(f"数据：{key_data}")
        else:
            # ActionState 对象
            if state.status != "running":
                continue
            lines.append(f"状态：{state.status}")
            if state.progress:
                lines.append(f"进度：{state.progress}")
            if state.prompt_contribution:
                lines.append(f"详情：{state.prompt_contribution}")
            if state.data:
                key_data = {
                    k: v for k, v in state.data.items() if not k.startswith("_")
                }
                if key_data:
                    lines.append(f"数据：{key_data}")

        lines.append("")

    if not lines:
        return ""

    return ACTION_STATES_TEMPLATE.format(running_instances="\n".join(lines))


# ========== 临时提示词 ==========

TEMP_PROMPTS_TEMPLATE = """
## 临时提醒
{prompts}
"""


def build_temp_prompts_section(temp_contents: list[str]) -> str:
    """构建临时提示词段落

    Args:
        temp_contents: 临时提示词内容列表（来自 executor.tick_temp_prompts()）

    Returns:
        临时提示词段落
    """
    if not temp_contents:
        return ""

    prompts = "\n".join(f"- {p}" for p in temp_contents)
    return TEMP_PROMPTS_TEMPLATE.format(prompts=prompts)


# ========== 对话历史提示词 ==========

HISTORY_TEMPLATE = """
## 最近对话
{chat_history}
"""


def build_history_prompt(
    conversation_history: list[dict],
    max_turns: int = 10,
) -> str:
    """构建对话历史提示词（带日期时间）

    Args:
        conversation_history: 对话历史列表
        max_turns: 最大轮数

    Returns:
        对话历史提示词
    """
    if not conversation_history:
        return "暂无对话历史"

    history = conversation_history[-max_turns:]

    lines = []
    for msg in history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        sender = msg.get("sender_name", "")
        timestamp = msg.get("timestamp")

        # 格式化时间
        time_str = ""
        if timestamp:
            try:
                if isinstance(timestamp, (int, float)):
                    dt = datetime.fromtimestamp(timestamp)
                elif isinstance(timestamp, str):
                    dt = datetime.fromisoformat(timestamp)
                else:
                    dt = None
                if dt:
                    time_str = f"[{dt.strftime('%Y-%m-%d %H:%M:%S')}] "
            except (ValueError, OSError):
                pass

        if role == "user":
            prefix = f"{sender}: " if sender else "用户: "
        elif role == "assistant":
            prefix = "你: "
        else:
            prefix = f"{role}: "

        lines.append(f"{time_str}{prefix}{content}")

    return HISTORY_TEMPLATE.format(chat_history="\n".join(lines))
