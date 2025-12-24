"""
上下文管理器：实现V2多阶段处理流程
"""

from typing import TYPE_CHECKING, Any

from .context_compressor import DefaultCompressor, LLMSummaryCompressor
from .context_truncator import ContextTruncator
from .token_counter import TokenCounter

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider


class ContextManager:
    """
    统一的上下文压缩管理模块

    工作流程：
    1. Token初始统计 → 判断是否超过82%
    2. 如果超过82%，执行压缩/截断（Agent模式/普通模式）
    3. 最终处理：合并消息、清理Tool Calls、按数量截断
    """

    COMPRESSION_THRESHOLD = 0.82  # 压缩触发阈值

    def __init__(self, model_context_limit: int, provider: "Provider | None" = None):
        """
        初始化上下文管理器

        Args:
            model_context_limit: 模型上下文限制（Token数）
            provider: LLM提供商实例（用于Agent模式的智能摘要）
        """
        self.model_context_limit = model_context_limit
        self.threshold = self.COMPRESSION_THRESHOLD  # 82% 触发阈值

        self.token_counter = TokenCounter()
        self.truncator = ContextTruncator()

        # 总是使用Agent模式
        if provider:
            self.compressor = LLMSummaryCompressor(provider)
        else:
            self.compressor = DefaultCompressor()

    async def process(
        self, messages: list[dict[str, Any]], max_messages_to_keep: int = 20
    ) -> list[dict[str, Any]]:
        """
        主处理方法：执行完整的V2流程

        Args:
            messages: 原始消息列表
            max_messages_to_keep: 最终保留的最大消息数

        Returns:
            处理后的消息列表
        """
        if self.model_context_limit == -1:
            return messages

        # 阶段1：Token初始统计
        needs_compression, initial_token_count = await self._initial_token_check(
            messages
        )

        # 阶段2：压缩/截断（如果需要）
        messages = await self._run_compression(messages, needs_compression)

        # 阶段3：最终处理
        messages = await self._run_final_processing(messages, max_messages_to_keep)

        return messages

    async def _initial_token_check(
        self, messages: list[dict[str, Any]]
    ) -> tuple[bool, int | None]:
        """
        阶段1：Token初始统计与触发判断

        Returns:
            tuple: (是否需要压缩, 初始token数)
        """
        if not messages:
            return False, None

        total_tokens = self.token_counter.count_tokens(messages)
        usage_rate = total_tokens / self.model_context_limit

        needs_compression = usage_rate > self.threshold
        return needs_compression, total_tokens if needs_compression else None

    async def _run_compression(
        self, messages: list[dict[str, Any]], needs_compression: bool
    ) -> list[dict[str, Any]]:
        """
        阶段2：压缩/截断处理

        Args:
            messages: 消息列表
            needs_compression: 是否需要压缩

        Returns:
            压缩/截断后的消息列表
        """
        if not needs_compression:
            return messages

        # Agent模式：先摘要，再判断
        messages = await self._compress_by_summarization(messages)

        # 第二次Token统计
        tokens_after_summary = self.token_counter.count_tokens(messages)
        if tokens_after_summary / self.model_context_limit > self.threshold:
            # 仍然超过82%，执行对半砍
            messages = self._compress_by_halving(messages)

        return messages

    async def _compress_by_summarization(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        摘要压缩策略（为后续实现预留接口）

        当前实现：标记消息为已摘要，保留原始内容
        后续可扩展为：调用LLM生成摘要

        Args:
            messages: 原始消息列表

        Returns:
            摘要后的消息列表
        """
        return await self.compressor.compress(messages)

    def _compress_by_halving(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        对半砍策略：删除中间50%的消息

        Args:
            messages: 原始消息列表

        Returns:
            截断后的消息列表
        """
        return self.truncator.truncate_by_halving(messages)

    async def _run_final_processing(
        self, messages: list[dict[str, Any]], max_messages_to_keep: int
    ) -> list[dict[str, Any]]:
        """
        阶段3：最终处理

        - a. 合并连续的user消息和assistant消息
        - b. 清理不成对的Tool Calls
        - c. 按数量截断

        Args:
            messages: 压缩后的消息列表
            max_messages_to_keep: 最大保留消息数

        Returns:
            最终处理后的消息列表
        """
        # 3a. 合并连续消息
        messages = self._merge_consecutive_messages(messages)

        # 3b. 清理不成对的Tool Calls
        messages = self._cleanup_unpaired_tool_calls(messages)

        # 3c. 按数量截断
        messages = self.truncator.truncate_by_count(messages, max_messages_to_keep)

        return messages

    def _merge_consecutive_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        3a. 合并连续的user消息和assistant消息

        规则：
        - 连续的user消息合并为一条（内容用换行符连接）
        - 连续的assistant消息合并为一条
        - 系统消息不合并

        Args:
            messages: 原始消息列表

        Returns:
            合并后的消息列表
        """
        if not messages:
            return messages

        merged = []
        current_group = []
        current_role = None

        for msg in messages:
            role = msg.get("role")

            if role == current_role and role in ("user", "assistant"):
                # 同角色，继续累积
                current_group.append(msg)
            else:
                # 角色改变，合并前一组
                if current_group:
                    merged.append(self._merge_message_group(current_group))
                current_group = [msg]
                current_role = role

        # 处理最后一组
        if current_group:
            merged.append(self._merge_message_group(current_group))

        return merged

    def _merge_message_group(self, group: list[dict[str, Any]]) -> dict[str, Any]:
        """
        合并一组同角色的消息

        Args:
            group: 同角色的消息组

        Returns:
            合并后的单条消息
        """
        if len(group) == 1:
            return group[0]

        merged = group[0].copy()

        # 合并content
        contents = []
        for msg in group:
            if msg.get("content"):
                contents.append(msg["content"])

        if contents:
            merged["content"] = "\n".join(str(c) for c in contents)

        return merged

    def _cleanup_unpaired_tool_calls(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        3b. 清理不成对的Tool Calls

        规则：
        - 检查每个tool_call是否有对应的tool角色消息
        - 最后一次tool_call（当次请求的调用）应被忽略，不视为"不成对"
        - 删除不成对的tool_call记录

        Args:
            messages: 原始消息列表

        Returns:
            清理后的消息列表
        """
        if not messages:
            return messages

        # 收集所有tool_call的ID
        tool_call_ids = set()
        tool_response_ids = set()

        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    tool_call_ids.add(tc.get("id"))
            elif msg.get("role") == "tool":
                tool_response_ids.add(msg.get("tool_call_id"))

        # 最后一次tool_call不视为不成对
        last_tool_call_id = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                if msg["tool_calls"]:
                    last_tool_call_id = msg["tool_calls"][-1].get("id")
                break

        # 找出不成对的tool_call
        unpaired_ids = tool_call_ids - tool_response_ids
        if last_tool_call_id:
            unpaired_ids.discard(last_tool_call_id)

        # 删除不成对的tool_call
        result = []
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                msg = msg.copy()
                msg["tool_calls"] = [
                    tc for tc in msg["tool_calls"] if tc.get("id") not in unpaired_ids
                ]
            result.append(msg)

        return result
