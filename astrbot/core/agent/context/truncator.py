from ..message import Message


class ContextTruncator:
    """Context truncator."""

    def fix_messages(self, messages: list[Message]) -> list[Message]:
        fixed_messages = []
        for message in messages:
            if message.role == "tool":
                # tool block 前面必须要有 user 和 assistant block
                if len(fixed_messages) < 2:
                    # 这种情况可能是上下文被截断导致的
                    # 我们直接将之前的上下文都清空
                    fixed_messages = []
                else:
                    fixed_messages.append(message)
            else:
                fixed_messages.append(message)
        return fixed_messages

    def truncate_by_turns(
        self,
        messages: list[Message],
        keep_most_recent_turns: int,
        dequeue_turns: int = 1,
    ) -> list[Message]:
        """截断上下文列表，确保不超过最大长度。
        一个 turn 包含一个 user 消息和一个 assistant 消息。
        这个方法会保证截断后的上下文列表符合 OpenAI 的上下文格式。

        Args:
            messages: 上下文列表
            keep_most_recent_turns: 保留最近的对话轮数
            dequeue_turns: 一次性丢弃的对话轮数

        Returns:
            截断后的上下文列表
        """
        if keep_most_recent_turns == -1:
            return messages
        if len(messages) <= keep_most_recent_turns:
            return messages
        if len(messages) // 2 <= keep_most_recent_turns:
            return messages

        system_message = None
        if messages[0].role == "system":
            system_message = messages[0]
            messages = messages[1:]

        truncated_contexts = messages[
            -(keep_most_recent_turns - dequeue_turns + 1) * 2 :
        ]
        # 找到第一个role 为 user 的索引，确保上下文格式正确
        index = next(
            (i for i, item in enumerate(truncated_contexts) if item.role == "user"),
            None,
        )
        if index is not None and index > 0:
            truncated_contexts = truncated_contexts[index:]

        if system_message is not None:
            truncated_contexts = [system_message] + truncated_contexts

        return self.fix_messages(truncated_contexts)

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

        messages_to_delete = (len(messages) - first_non_system) // 2

        result = messages[:first_non_system]
        result.extend(messages[first_non_system + messages_to_delete :])

        index = next(
            (i for i, item in enumerate(result) if item.role == "user"),
            None,
        )
        if index is not None:
            result = result[index:]

        return self.fix_messages(result)
