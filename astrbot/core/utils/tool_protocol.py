"""Validate the tool pairing in a final Chat Completions request."""

from collections.abc import Mapping


class ToolMessageProtocolError(ValueError):
    """A local pairing failure that cannot be repaired by changing providers."""

    def __init__(self, reason: str, message_index: int, pending_count: int = 0):
        """Describe a structural failure without exposing message contents.

        Args:
            reason: A fixed diagnostic code.
            message_index: The position where validation failed.
            pending_count: Number of calls still awaiting a result.
        """
        self.reason = reason
        self.message_index = message_index
        self.pending_count = pending_count
        super().__init__(
            f"tool_message_protocol reason={reason} "
            f"index={message_index} pending_count={pending_count}"
        )


def validate_tool_message_sequence(messages: object) -> None:
    """Require exactly one contiguous result per declared tool call.

    Results may arrive in any order within a call group. IDs can be reused in
    later, fully answered groups. This validates the final request without
    changing it or inventing tool output; upstream history repair is separate.

    Args:
        messages: The effective messages after request overrides are merged.

    Raises:
        ToolMessageProtocolError: If the final sequence has invalid pairing.
    """
    if not isinstance(messages, list):
        raise ToolMessageProtocolError("messages_not_list", -1)
    pending: set[str] = set()
    answered: set[str] = set()
    for index, message in enumerate(messages):
        if not isinstance(message, Mapping):
            raise ToolMessageProtocolError("message_not_object", index, len(pending))
        role = message.get("role")
        calls = message.get("tool_calls")
        if pending and role != "tool":
            raise ToolMessageProtocolError("missing_tool_response", index, len(pending))
        if calls is not None and role != "assistant":
            raise ToolMessageProtocolError("calls_on_non_assistant", index)
        if role != "tool" and message.get("tool_call_id") is not None:
            raise ToolMessageProtocolError("response_id_on_non_tool", index)
        if role == "assistant" and calls is not None:
            if not isinstance(calls, list):
                raise ToolMessageProtocolError("calls_not_list", index)
            answered = set()
            for call in calls:
                call_id = call.get("id") if isinstance(call, Mapping) else None
                if not isinstance(call_id, str) or not call_id.strip():
                    raise ToolMessageProtocolError("invalid_call_id", index)
                if call_id in pending:
                    raise ToolMessageProtocolError("duplicate_call_id", index)
                pending.add(call_id)
        if role == "tool":
            call_id = message.get("tool_call_id")
            if not isinstance(call_id, str) or not call_id.strip():
                raise ToolMessageProtocolError("invalid_response_id", index)
            if call_id in answered:
                raise ToolMessageProtocolError("duplicate_tool_response", index)
            if call_id not in pending:
                raise ToolMessageProtocolError("orphan_tool_response", index)
            pending.remove(call_id)
            answered.add(call_id)
    if pending:
        raise ToolMessageProtocolError(
            "missing_tool_response", len(messages), len(pending)
        )
