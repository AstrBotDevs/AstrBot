"""
Prompt Assembly data models.

This module defines the three-channel prompt assembly structures used by
``assembly.py``, ``renderer.py`` and ``tracing.py``.

The core types exported via ``astrbot.core.prompt`` are part of the extension
surface for prompt assembly integrations. Internal wiring around those types
may still evolve without separate notice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from astrbot.core.agent.message import ContentPart

# ---------------------------------------------------------------------------
# system_blocks 排序常量 — 控制 system prompt 内各区块的渲染顺序
#
# 数值为整数，按升序排列。只在 system_blocks 通道内排序，不影响其他通道。
# 间隔为 100，便于未来在两个现有区块之间插入新区块（如 order=350 或 650）
# 而无需重新编号。
# ---------------------------------------------------------------------------

# LLM 安全模式提示（防注入、内容策略等）。prepend=True，强制置于 system_prompt 最前面
SYSTEM_BLOCK_ORDER_SAFETY = 100
# 人格/角色设定指令 — 定义 AI 的身份、语气、行为规则
SYSTEM_BLOCK_ORDER_PERSONA = 200
# 技能（Skills）提示词 — 描述可用技能的触发条件和行为
SYSTEM_BLOCK_ORDER_SKILLS = 300
# 知识库检索结果（非 agentic 模式）— 将 RAG 检索到的相关片段注入 system prompt
SYSTEM_BLOCK_ORDER_KB = 400
# Sub-agent 路由器提示 — 多 Agent 编排场景下，指导 LLM 选择合适的子 Agent
SYSTEM_BLOCK_ORDER_ROUTER = 500
# 运行时环境提示 — sandbox 或 local 模式下的环境说明和约束
SYSTEM_BLOCK_ORDER_RUNTIME = 600
# 工具调用格式说明 — 指导 LLM 如何使用注册的工具（function calling 格式等）
SYSTEM_BLOCK_ORDER_TOOL_USE = 700
# Live 模式提示 — 实时交互模式下的特殊行为指令
SYSTEM_BLOCK_ORDER_LIVE_MODE = 800

# ---------------------------------------------------------------------------
# user_append_parts 排序常量 — 控制追加到用户消息中各内容的顺序
#
# 这些内容最终写入 req.extra_user_content_parts，作为用户消息的一部分发送，
# 而非进入 system prompt，避免干扰模型的指令遵循能力。
# ---------------------------------------------------------------------------

# 附件/图片描述通知 — 告知 LLM 用户上传了哪些文件或图片及其摘要
USER_APPEND_ORDER_ATTACHMENTS = 100
# 引用消息内容 — 用户引用/回复的历史消息文本及图片说明
USER_APPEND_ORDER_QUOTED = 200
# 系统提醒 — 用户 ID、昵称、群组名称、当前日期时间等元信息
USER_APPEND_ORDER_SYSTEM_REMINDER = 300

# ---------------------------------------------------------------------------
# context_contributions 排序常量 — 控制插入到对话历史（req.contexts）前后的消息顺序
#
# position="prefix" 的消息插到历史最前面（如预设对话示例），
# position="suffix" 的消息追加到历史末尾（如文件提取合成消息）。
# ---------------------------------------------------------------------------

# 人格预设对话示例 — persona 中配置的 begin_dialogs，作为 few-shot 示例引导 LLM 行为
CONTEXT_ORDER_PERSONA_BEGIN_DIALOGS = 100
# 文件提取合成消息 — 从上传文件中提取的文本内容，包装为 system 角色的合成历史消息
CONTEXT_ORDER_FILE_EXTRACT = 100

# context 贡献的插入位置：prefix 插到历史最前面，suffix 追加到历史末尾
ContextPosition = Literal["prefix", "suffix"]


# ---------------------------------------------------------------------------
# 数据类定义
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SystemBlock:
    """system prompt 中的一个结构化区块。

    Attributes:
        source:           来源标识（如 "persona", "router", "sandbox"），
                          用于 trace 调试时快速定位区块来源
        order:            通道内排序权重，值越小越靠前
        content:          区块的文本内容
        prepend:          是否插入到 system_prompt 最前面（而非追加到末尾）。
                          目前仅 SAFETY 区块使用 True，确保安全规则始终在最前面
        visible_in_trace: 是否在结构化 trace 快照中可见，用于控制敏感内容的可见性
    """

    source: str
    order: int
    content: str
    prepend: bool = False
    visible_in_trace: bool = True


@dataclass(slots=True)
class UserAppendPart:
    """追加到用户消息中的一个内容片段。

    Attributes:
        source:           来源标识（如 "attachment", "quoted_message", "system_reminder"）
        order:            通道内排序权重
        part:             实际内容，支持 TextPart、ImagePart 等多种类型
        visible_in_trace: 是否在 trace 快照中可见
    """

    source: str
    order: int
    part: ContentPart
    visible_in_trace: bool = True


@dataclass(slots=True)
class ContextContribution:
    """插入到对话历史（req.contexts）中的一组合成消息。

    Attributes:
        source:           来源标识（如 "persona_begin_dialogs", "file_extract"）
        order:            通道内排序权重
        messages:         OpenAI 格式的消息列表，如 [{"role": "user", "content": "..."}]
        position:         插入位置："prefix" 插到历史最前，"suffix" 追加到历史末尾
        visible_in_trace: 是否在 trace 快照中可见
    """

    source: str
    order: int
    messages: list[dict]
    position: ContextPosition
    visible_in_trace: bool = True


@dataclass(slots=True)
class PromptAssembly:
    """请求级别的 prompt 组装容器。

    在 build_main_agent() 中创建，各 core helper 向其中注册区块，
    最终由 renderer 一次性渲染回 ProviderRequest。生命周期仅限于单次请求。

    Attributes:
        system_blocks:         所有 system prompt 区块
        user_append_parts:     所有追加到用户消息的内容片段
        context_contributions: 所有插入到对话历史前后的合成消息
        metadata:              附加元数据，可用于记录请求级别的调试信息
        rendered:              是否已完成渲染，防止重复渲染
    """

    system_blocks: list[SystemBlock] = field(default_factory=list)
    user_append_parts: list[UserAppendPart] = field(default_factory=list)
    context_contributions: list[ContextContribution] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    rendered: bool = False
