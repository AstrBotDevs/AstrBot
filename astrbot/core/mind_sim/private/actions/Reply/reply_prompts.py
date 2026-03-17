"""MindSim 回复动作提示词模块

根据 reply_type 类型选择不同的提示词模板，支持：
- normal: 正常回复
- append: 追加回复（补充自己之前的发言）
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.mind_sim.context import MindContext


# ========== 正常回复提示词 ==========

NORMAL_REPLY_PROMPT = """
你是{bot_name}，正在和人聊天。

临时提醒
{temp_prompts}

当前运行的动作实例
{running_actions}
当前状态 当前时间：{current_time} 聊天：{chat_group_name}

以上为系统状态
你现在是 {system_prompt} 这个人格，保持你的特质： {personality_traits}

当前心情
{mood}

用这样的表达风格
{expression_style}

最近对话
{dialogue_history}

你是{bot_name}，正在和人聊天。
你现在应该就以下指导的话题进行回复：
{reply_guidance}
请不要输出违法违规内容，不要输出色情，暴力，政治相关内容，如有敏感内容，请规避。

请注意不要输出多余内容(包括不必要的前后缀，冒号，括号，表情包，at或 @等 )，只输出发言内容就好。

现在请你读读之前的聊天记录，然后给出日常且口语化的回复
尽量简短一些。{keywords_reaction_prompt}请注意把握聊天内容，不要回复的太有条理，给出日常的回复，可以有个性
免得啰嗦或者回复内容太乱。

现在，你说：
"""


# ========== 追加回复提示词 ==========

APPEND_REPLY_PROMPT = """你是{bot_name}，正在和人聊天。

临时提醒
{temp_prompts}

当前运行的动作实例
{running_actions}
当前状态 当前时间：{current_time} 聊天：{chat_group_name}

以上为系统状态
你现在是 {system_prompt} 这个人格，保持你的特质： {personality_traits}

当前心情
{mood}

用这样的表达风格
{expression_style}

最近对话
{dialogue_history}

你是{bot_name}，正在和人聊天。

你是{bot_name}，正在和人聊天。
你现在想补充说明你刚刚自己的发言内容：{target}，原因是{reason}
请你根据聊天内容，组织一条新回复。注意，{target} 是刚刚你自己的发言，你要在这基础上进一步发言，请按照你自己的角度来继续进行回复。注意保持上下文的连贯性。
{reply_guidance}
请不要输出违法违规内容，不要输出色情，暴力，政治相关内容，如有敏感内容，请规避。

请注意不要输出多余内容(包括不必要的前后缀，冒号，括号，表情包，at或 @等 )，只输出发言内容就好。

尽量简短一些。{keywords_reaction_prompt}请注意把握聊天内容，不要回复的太有条理，可以有个性。

现在，你说：
"""


# ========== 提示词组装器 ==========

REPLY_TYPE_PROMPTS = {
    "normal": NORMAL_REPLY_PROMPT,
    "append": APPEND_REPLY_PROMPT,
}


def build_reply_prompt(
    reply_type: str,
    reply_guidance: str,
    ctx: "MindContext",
    dialogue_history: str,
    *,
    target: str = "",
    reason: str = "",
    temp_prompts: str = "",
    running_actions: str = "",
) -> str:
    """构建回复提示词

    Args:
        reply_type: 回复类型 (normal/append)
        reply_guidance: 主思考给的指导
        ctx: MindContext 上下文
        dialogue_history: 对话历史（已由 prompts.build_history_prompt 格式化）
        target: 追加回复时，要补充的原发言内容
        reason: 追加回复时，补充的原因
        temp_prompts: 临时提醒（已由 prompts.build_temp_prompts_section 格式化）
        running_actions: 动作实例状态（已由 prompts.build_action_states_prompt 格式化）

    Returns:
        完整提示词
    """
    # 获取提示词模板
    template = REPLY_TYPE_PROMPTS.get(reply_type, NORMAL_REPLY_PROMPT)

    # 获取人格配置
    personality_config = ctx.personality_config or {}
    traits = personality_config.get("traits", "善良、智能、有趣")
    expression_style = personality_config.get("expression_style", "自然、友好")

    # 获取系统提示词
    system_prompt = ctx.system_prompt or "你是一个助手"

    # 获取心情（从上下文内存中获取，当前思考周期的心情）
    mood = ctx.memory.get("current_mood", "平静")

    # 获取机器人名称
    robot_config = ctx.robot_config or {}
    bot_name = robot_config.get("nickname", "助手")

    # 当前时间
    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 聊天名称（从 unified_msg_origin 提取）
    chat_group_name = ctx.unified_msg_origin or "群聊"

    return template.format(
        bot_name=bot_name,
        current_time=current_time,
        chat_group_name=chat_group_name,
        system_prompt=system_prompt,
        personality_traits=traits,
        mood=mood,
        expression_style=expression_style,
        running_actions=running_actions or "无",
        dialogue_history=dialogue_history or "暂无",
        reply_guidance=reply_guidance or "根据聊天内容自然回复",
        keywords_reaction_prompt="",
        temp_prompts=temp_prompts or "无",
        target=target,
        reason=reason,
    )
