"""
Prompt Assembly 追踪快照 — 生成结构化的 prompt 组装过程调试信息。

与现有的 astr_agent_prepare 原始 trace 互补：
  - 现有 trace: 记录最终渲染后的完整 system_prompt 字符串（不可逆）
  - 结构化 trace: 记录每个区块的来源、排序和摘要信息（可追溯到具体模块）

结构化 trace 快照在插件 hook 运行之前采集，因此仅包含 core 拥有的区块，
不包含插件 hook 后的修改。插件修改仍然通过现有的原始 trace 观察。
"""

from __future__ import annotations

import copy

from astrbot.core.agent.message import (
    AudioURLPart,
    ContentPart,
    ImageURLPart,
    TextPart,
    ThinkPart,
)
from astrbot.core.provider.entities import ProviderRequest

from .models import PromptAssembly


def summarize_provider_request_base(req: ProviderRequest) -> dict:
    return {
        "system_prompt_chars": len(req.system_prompt or ""),
        "context_count": len(req.contexts),
        "extra_user_part_count": len(req.extra_user_content_parts),
        "image_count": len(req.image_urls),
        "has_prompt": bool(req.prompt and req.prompt.strip()),
    }


def build_prompt_trace_snapshot(assembly: PromptAssembly) -> dict:
    """Build a redacted structured trace snapshot from a PromptAssembly.

    返回格式：
      {
          "system_blocks": [
              {"source": "safety", "order": 100, "prepend": True, "char_count": 120},
              {"source": "persona", "order": 200, "prepend": False, "char_count": 80},
              ...
          ],
          "user_append_parts": [
              {"source": "system_reminder", "order": 300, "part": {...}},
              ...
          ],
          "context_prefix": [
              {"source": "persona_begin_dialogs", "order": 100, "messages": [...]},
          ],
          "context_suffix": [
              {"source": "file_extract", "order": 100, "messages": [...]},
          ],
          "metadata": {...},
      }

    所有内容按 order 排序，且仅包含 visible_in_trace=True 的区块。
    快照默认只记录摘要信息（如字符数、消息数、角色），不直接记录原文内容。

    Args:
        assembly: PromptAssembly to summarize.

    Returns:
        Serializable dict for traces and debugging.
    """
    return {
        "system_blocks": [
            {
                "source": block.source,
                "order": block.order,
                "prepend": block.prepend,
                "char_count": len(block.content),
            }
            for block in sorted(assembly.system_blocks, key=lambda item: item.order)
            if block.visible_in_trace
        ],
        "user_append_parts": [
            {
                "source": item.source,
                "order": item.order,
                "part": _summarize_content_part(item.part),
            }
            for item in sorted(assembly.user_append_parts, key=lambda part: part.order)
            if item.visible_in_trace
        ],
        "context_prefix": [
            {
                "source": item.source,
                "order": item.order,
                **_summarize_messages(item.messages),
            }
            for item in sorted(
                (
                    contribution
                    for contribution in assembly.context_contributions
                    if contribution.position == "prefix"
                ),
                key=lambda contribution: contribution.order,
            )
            if item.visible_in_trace
        ],
        "context_suffix": [
            {
                "source": item.source,
                "order": item.order,
                **_summarize_messages(item.messages),
            }
            for item in sorted(
                (
                    contribution
                    for contribution in assembly.context_contributions
                    if contribution.position == "suffix"
                ),
                key=lambda contribution: contribution.order,
            )
            if item.visible_in_trace
        ],
        "metadata": copy.deepcopy(assembly.metadata),
    }


def _summarize_content_part(part: ContentPart) -> dict:
    summary: dict[str, object] = {"type": part.type}
    if isinstance(part, TextPart):
        summary["char_count"] = len(part.text)
    elif isinstance(part, ThinkPart):
        summary["char_count"] = len(part.think)
        summary["has_encrypted"] = bool(part.encrypted)
    elif isinstance(part, ImageURLPart):
        summary["has_id"] = bool(part.image_url.id)
    elif isinstance(part, AudioURLPart):
        summary["has_id"] = bool(part.audio_url.id)
    return summary


def _summarize_messages(messages: list[dict]) -> dict:
    roles: list[str] = []
    text_char_count = 0
    non_text_part_count = 0
    for message in messages:
        roles.append(str(message.get("role", "unknown")))
        content = message.get("content")
        if isinstance(content, str):
            text_char_count += len(content)
            continue
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_char_count += len(str(part.get("text", "")))
                else:
                    non_text_part_count += 1
    return {
        "message_count": len(messages),
        "roles": roles,
        "text_char_count": text_char_count,
        "non_text_part_count": non_text_part_count,
    }
