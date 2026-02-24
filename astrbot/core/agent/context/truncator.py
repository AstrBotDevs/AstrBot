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

        # First pass: identify which assistant(tool_calls) have valid tool responses
        # Build a set of indices for assistant messages that have valid tool responses
        valid_tool_call_indices: set[int] = set()
        i = 0
        while i < len(messages):
            msg = messages[i]
            if self._has_tool_calls(msg):
                # Check if next message(s) are tool responses
                j = i + 1
                has_tool_response = False
                while j < len(messages) and messages[j].role == "tool":
                    has_tool_response = True
                    j += 1
                if has_tool_response:
                    valid_tool_call_indices.add(i)
            i += 1

        # Second pass: build fixed message list
        fixed_messages: list[Message] = []
        in_valid_tool_chain = False  # 是否处于有效的 tool call 链中

        for i, msg in enumerate(messages):
            if msg.role == "tool":
                # tool 消息：只有在有效的 tool call 链中才保留
                if in_valid_tool_chain:
                    fixed_messages.append(msg)
                # else: 孤立的 tool 消息，跳过
            elif self._has_tool_calls(msg):
                # assistant(tool_calls)：只保留有效的（后面有 tool response 的）
                if i in valid_tool_call_indices:
                    fixed_messages.append(msg)
                    in_valid_tool_chain = True  # 进入有效的 tool call 链
                else:
                    in_valid_tool_chain = False  # 孤立的 tool_calls，跳过并重置状态
            else:
                # system, user, 或不含 tool_calls 的 assistant
                fixed_messages.append(msg)
                in_valid_tool_chain = False  # 退出 tool call 链

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
