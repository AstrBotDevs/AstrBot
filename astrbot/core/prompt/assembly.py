"""
Prompt Assembly 注册方法 — 向 PromptAssembly 中添加各通道内容的便捷 API。

每个函数对应一个通道，负责创建对应的数据对象并追加到 assembly 中。
所有函数都会跳过空内容（空字符串、空消息列表），避免产生无意义的区块。
"""

from __future__ import annotations

import copy

from astrbot.core import logger
from astrbot.core.agent.message import ContentPart, TextPart

from .models import (
    ContextContribution,
    ContextPosition,
    PromptAssembly,
    SystemBlock,
    UserAppendPart,
)


class PromptMutation:
    """Restricted facade exposed to prompt assembly hooks."""

    __slots__ = (
        "_assembly",
        "_warned_context_prefix_sources",
        "_warned_plugin_orders",
    )

    def __init__(self, assembly: PromptAssembly) -> None:
        self._assembly = assembly
        self._warned_context_prefix_sources: set[str] = set()
        self._warned_plugin_orders: set[tuple[str, int]] = set()

    def add_system(
        self,
        text: str,
        source: str,
        order: int,
        *,
        visible_in_trace: bool = True,
    ) -> None:
        self._warn_if_reserved_order(source, order)
        add_system_block(
            self._assembly,
            source=source,
            order=order,
            content=text,
            visible_in_trace=visible_in_trace,
        )

    def add_user_text(
        self,
        text: str,
        source: str,
        order: int,
        *,
        visible_in_trace: bool = True,
    ) -> None:
        self._warn_if_reserved_order(source, order)
        add_user_text(
            self._assembly,
            source=source,
            order=order,
            text=text,
            visible_in_trace=visible_in_trace,
        )

    def add_context_prefix(
        self,
        messages: list[dict],
        source: str,
        order: int,
        *,
        visible_in_trace: bool = True,
    ) -> None:
        # order 警告：插件开发者应避免使用过低的 order 值（如 <900），以免与核心保留的提示块发生排序冲突。
        self._warn_if_reserved_order(source, order)
        # Context prefix 插在历史最前，最有可能影响 KV cache 效率，发出警告提示插件开发者确认是否真的需要使用 context prefix
        self._warn_if_context_prefix_affects_cache(source, messages)
        add_context_prefix(
            self._assembly,
            source=source,
            order=order,
            messages=messages,
            visible_in_trace=visible_in_trace,
        )

    def add_context_suffix(
        self,
        messages: list[dict],
        source: str,
        order: int,
        *,
        visible_in_trace: bool = True,
    ) -> None:
        self._warn_if_reserved_order(source, order)
        add_context_suffix(
            self._assembly,
            source=source,
            order=order,
            messages=messages,
            visible_in_trace=visible_in_trace,
        )

    def _warn_if_reserved_order(self, source: str, order: int) -> None:
        if order >= 900:
            return
        warn_key = (source, order)
        if warn_key in self._warned_plugin_orders:
            return
        self._warned_plugin_orders.add(warn_key)
        logger.warning(
            "Prompt assembly plugin order %s for source %s overlaps the core-reserved range. "
            "Prefer plugin orders >= 900.",
            order,
            source,
        )

    def _warn_if_context_prefix_affects_cache(
        self,
        source: str,
        messages: list[dict],
    ) -> None:
        if not messages or source in self._warned_context_prefix_sources:
            return
        self._warned_context_prefix_sources.add(source)
        logger.warning(
            "Prompt assembly context prefix from source %s is prepended to the message history "
            "and may reduce provider-side KV cache prefix reuse. Prefer add_system() for static "
            "policy text, and reserve add_context_prefix() for few-shot examples or synthetic "
            "history that must appear before the conversation.",
            source,
        )


def add_system_block(
    assembly: PromptAssembly,
    *,
    source: str,
    order: int,
    content: str,
    prepend: bool = False,
    visible_in_trace: bool = True,
) -> None:
    """向 assembly 注册一个 system prompt 区块。

    Args:
        assembly:          目标 assembly 容器
        source:            来源标识，如 "persona", "safety", "kb"
        order:             通道内排序权重，使用 models.py 中的常量
        content:           区块文本内容，为空时静默跳过
        prepend:           True 则插到 system_prompt 最前面（仅 SAFETY 使用）
        visible_in_trace:  是否在 trace 快照中可见
    """
    if not content:
        return
    assembly.system_blocks.append(
        SystemBlock(
            source=source,
            order=order,
            content=content,
            prepend=prepend,
            visible_in_trace=visible_in_trace,
        )
    )


def add_user_part(
    assembly: PromptAssembly,
    *,
    source: str,
    order: int,
    part: ContentPart,
    visible_in_trace: bool = True,
) -> None:
    """向 assembly 注册一个用户消息追加片段（通用版，接受任意 ContentPart）。

    Args:
        assembly:          目标 assembly 容器
        source:            来源标识，如 "attachment", "quoted_message"
        order:             通道内排序权重
        part:              内容片段（TextPart、ImagePart 等）
        visible_in_trace:  是否在 trace 快照中可见
    """
    assembly.user_append_parts.append(
        UserAppendPart(
            source=source,
            order=order,
            part=part,
            visible_in_trace=visible_in_trace,
        )
    )


def add_user_text(
    assembly: PromptAssembly,
    *,
    source: str,
    order: int,
    text: str,
    visible_in_trace: bool = True,
) -> None:
    """向 assembly 注册一段纯文本追加到用户消息（add_user_part 的文本快捷方式）。

    Args:
        assembly:          目标 assembly 容器
        source:            来源标识
        order:             通道内排序权重
        text:              纯文本内容，为空时静默跳过
        visible_in_trace:  是否在 trace 快照中可见
    """
    if not text:
        return
    add_user_part(
        assembly,
        source=source,
        order=order,
        part=TextPart(text=text),
        visible_in_trace=visible_in_trace,
    )


def add_context_prefix(
    assembly: PromptAssembly,
    *,
    source: str,
    order: int,
    messages: list[dict],
    visible_in_trace: bool = True,
) -> None:
    """向 assembly 注册一组前缀消息（插到对话历史最前面）。

    典型用途：人格预设对话示例（persona begin_dialogs）。

    Args:
        assembly:          目标 assembly 容器
        source:            来源标识，如 "persona_begin_dialogs"
        order:             通道内排序权重
        messages:          OpenAI 格式消息列表，为空时静默跳过
        visible_in_trace:  是否在 trace 快照中可见
    """
    _add_context_contribution(
        assembly,
        source=source,
        order=order,
        messages=messages,
        position="prefix",
        visible_in_trace=visible_in_trace,
    )


def add_context_suffix(
    assembly: PromptAssembly,
    *,
    source: str,
    order: int,
    messages: list[dict],
    visible_in_trace: bool = True,
) -> None:
    """向 assembly 注册一组后缀消息（追加到对话历史末尾）。

    典型用途：文件提取合成消息（file extract results）。

    Args:
        assembly:          目标 assembly 容器
        source:            来源标识，如 "file_extract"
        order:             通道内排序权重
        messages:          OpenAI 格式消息列表，为空时静默跳过
        visible_in_trace:  是否在 trace 快照中可见
    """
    _add_context_contribution(
        assembly,
        source=source,
        order=order,
        messages=messages,
        position="suffix",
        visible_in_trace=visible_in_trace,
    )


def _add_context_contribution(
    assembly: PromptAssembly,
    *,
    source: str,
    order: int,
    messages: list[dict],
    position: ContextPosition,
    visible_in_trace: bool = True,
) -> None:
    """context 贡献的内部实现，被 add_context_prefix / add_context_suffix 调用。"""
    if not messages:
        return
    assembly.context_contributions.append(
        ContextContribution(
            source=source,
            order=order,
            messages=copy.deepcopy(messages),
            visible_in_trace=visible_in_trace,
            position=position,
        )
    )
