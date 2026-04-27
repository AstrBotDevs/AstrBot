"""
Prompt Assembly renderer.

This is the final step of prompt assembly: core helpers register structured
blocks into a request-scoped PromptAssembly, then render_prompt_assembly()
writes the three channels back into the request fields once.
"""

from __future__ import annotations

import copy

from astrbot.core.provider.entities import ProviderRequest

from .models import PromptAssembly


def render_prompt_assembly(
    req: ProviderRequest,
    assembly: PromptAssembly,
) -> ProviderRequest:
    """将 PromptAssembly 渲染回 ProviderRequest。

    渲染逻辑：
      - system_blocks 中 prepend=True 的块按 order 排序后拼到 system_prompt 最前面，
        prepend=False 的块按 order 排序后追加到末尾
      - user_append_parts 按 order 排序后依次追加到 extra_user_content_parts
      - context_contributions 按 position 分为 prefix/suffix，
        分别插到 contexts 的最前面和最末尾

    Args:
        req:      待渲染的目标 ProviderRequest
        assembly: 已完成注册的 PromptAssembly

    Returns:
        渲染后的同一个 req 对象（原地修改，返回引用便于链式调用）
    """
    if assembly.rendered:
        return req

    # TODO: Remove this compatibility shim after all helper entrypoints are
    # tightened to accept only fully initialized ProviderRequest instances.
    # Some legacy unit tests and helper-only call paths still pass lightweight
    # request-like objects that only provide the fields they mutate.
    if (
        not hasattr(req, "extra_user_content_parts")
        or req.extra_user_content_parts is None
    ):
        req.extra_user_content_parts = []
    if not hasattr(req, "contexts") or req.contexts is None:
        req.contexts = []

    # --- system_blocks → req.system_prompt ---
    # 将 prepend 块和 append 块分离，分别拼到原始 system_prompt 的前面和后面
    prepend_parts: list[str] = []
    append_parts: list[str] = []
    for block in sorted(assembly.system_blocks, key=lambda item: item.order):
        if block.prepend:
            prepend_parts.append(block.content)
        else:
            append_parts.append(block.content)
    prepend_prompt = "".join(prepend_parts)
    append_prompt = "".join(append_parts)
    system_prompt = f"{prepend_prompt}{req.system_prompt or ''}{append_prompt}"
    req.system_prompt = system_prompt

    # --- user_append_parts → req.extra_user_content_parts ---
    # 按 order 排序后依次追加，保持用户消息中各片段的有序性
    for item in sorted(assembly.user_append_parts, key=lambda part: part.order):
        req.extra_user_content_parts.append(item.part)

    # --- context_contributions → req.contexts ---
    # 分离 prefix 和 suffix，最终组合为 prefix + 原始历史 + suffix
    prefix_messages: list[dict] = []
    suffix_messages: list[dict] = []
    for contribution in sorted(
        assembly.context_contributions, key=lambda item: item.order
    ):
        target = (
            prefix_messages if contribution.position == "prefix" else suffix_messages
        )
        target.extend(copy.deepcopy(contribution.messages))

    req.contexts = prefix_messages + list(req.contexts) + suffix_messages
    assembly.rendered = True
    return req
