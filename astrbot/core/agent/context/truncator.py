from ..message import Message


class ContextTruncator:
    """Context truncator."""

    def _has_tool_calls(self, message: Message) -> bool:
        """Check if a message contains tool calls."""
        return (
            message.role == "assistant"
            and message.tool_calls is not None
            and len(message.tool_calls) > 0
        )

    def fix_messages(self, messages: list[Message]) -> list[Message]:
        """修复消息列表，确保 tool call 和 tool response 的配对关系有效。

        此方法确保：
        1. 每个 `tool` 消息前面都有一个包含 tool_calls 的 `assistant` 消息
        2. 每个包含 tool_calls 的 `assistant` 消息后面都有对应的 `tool` 响应

        这是 OpenAI Chat Completions API 规范的要求（Gemini 对此执行严格检查）。
        """
        if not messages:
            return messages

        fixed_messages: list[Message] = []
        pending_assistant: Message | None = None
        pending_tools: list[Message] = []

        def flush_pending_if_valid() -> None:
            nonlocal pending_assistant, pending_tools
            if pending_assistant is not None and pending_tools:
                fixed_messages.append(pending_assistant)
                fixed_messages.extend(pending_tools)
            pending_assistant = None
            pending_tools = []

        for msg in messages:
            if msg.role == "tool":
                # 只有在有挂起的 assistant(tool_calls) 时才记录 tool 响应
                if pending_assistant is not None:
                    pending_tools.append(msg)
                # else: 孤立的 tool 消息，直接忽略
                continue

            if self._has_tool_calls(msg):
                # 遇到新的 assistant(tool_calls) 前，先处理旧的 pending 链
                flush_pending_if_valid()
                pending_assistant = msg
                continue

            # 非 tool，且不含 tool_calls 的消息
            # 先结束任何 pending 链，再正常追加
            flush_pending_if_valid()
            fixed_messages.append(msg)

        # 结束时处理最后一个 pending 链
        flush_pending_if_valid()

        return fixed_messages

    def truncate_by_turns(
        self,
        messages: list[Message],
        keep_most_recent_turns: int,
        drop_turns: int = 1,
    ) -> list[Message]:
        """截断上下文列表，确保不超过最大长度。
        一个 turn 包含一个 user 消息和一个 assistant 消息。
        这个方法会保证截断后的上下文列表符合 OpenAI 的上下文格式。

        Args:
            messages: 上下文列表
            keep_most_recent_turns: 保留最近的对话轮数
            drop_turns: 一次性丢弃的对话轮数

        Returns:
            截断后的上下文列表
        """
        if keep_most_recent_turns == -1:
            return messages

        first_non_system = 0
        for i, msg in enumerate(messages):
            if msg.role != "system":
                first_non_system = i
                break

        system_messages = messages[:first_non_system]
        non_system_messages = messages[first_non_system:]

        if len(non_system_messages) // 2 <= keep_most_recent_turns:
            return messages

        num_to_keep = keep_most_recent_turns - drop_turns + 1
        if num_to_keep <= 0:
            truncated_contexts = []
        else:
            truncated_contexts = non_system_messages[-num_to_keep * 2 :]

        # 找到第一个 role 为 user 的索引，确保上下文格式正确
        index = next(
            (i for i, item in enumerate(truncated_contexts) if item.role == "user"),
            None,
        )
        if index is not None and index > 0:
            truncated_contexts = truncated_contexts[index:]

        result = system_messages + truncated_contexts

        return self.fix_messages(result)

    def truncate_by_dropping_oldest_turns(
        self,
        messages: list[Message],
        drop_turns: int = 1,
    ) -> list[Message]:
        """丢弃最旧的 N 个对话轮次。"""
        if drop_turns <= 0:
            return messages

        first_non_system = 0
        for i, msg in enumerate(messages):
            if msg.role != "system":
                first_non_system = i
                break

        system_messages = messages[:first_non_system]
        non_system_messages = messages[first_non_system:]

        if len(non_system_messages) // 2 <= drop_turns:
            truncated_non_system = []
        else:
            truncated_non_system = non_system_messages[drop_turns * 2 :]

        index = next(
            (i for i, item in enumerate(truncated_non_system) if item.role == "user"),
            None,
        )
        if index is not None:
            truncated_non_system = truncated_non_system[index:]
        elif truncated_non_system:
            truncated_non_system = []

        result = system_messages + truncated_non_system

        return self.fix_messages(result)

    def truncate_by_halving(
        self,
        messages: list[Message],
    ) -> list[Message]:
        """对半砍策略，删除 50% 的消息"""
        if len(messages) <= 2:
            return messages

        first_non_system = 0
        for i, msg in enumerate(messages):
            if msg.role != "system":
                first_non_system = i
                break

        system_messages = messages[:first_non_system]
        non_system_messages = messages[first_non_system:]

        messages_to_delete = len(non_system_messages) // 2
        if messages_to_delete == 0:
            return messages

        truncated_non_system = non_system_messages[messages_to_delete:]

        index = next(
            (i for i, item in enumerate(truncated_non_system) if item.role == "user"),
            None,
        )
        if index is not None:
            truncated_non_system = truncated_non_system[index:]

        result = system_messages + truncated_non_system

        return self.fix_messages(result)
