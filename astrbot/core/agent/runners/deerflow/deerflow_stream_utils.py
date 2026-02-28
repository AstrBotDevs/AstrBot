import typing as T
from collections.abc import Iterable


def extract_text(content: T.Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if "content" in content:
            return extract_text(content.get("content"))
        if "kwargs" in content and isinstance(content["kwargs"], dict):
            return extract_text(content["kwargs"].get("content"))
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif "content" in item:
                    parts.append(str(item["content"]))
        return "\n".join([p for p in parts if p]).strip()
    return str(content) if content is not None else ""


def extract_messages_from_values_data(data: T.Any) -> list[T.Any]:
    """Extract messages list from possible values event payload shapes."""
    candidates: list[T.Any] = []
    if isinstance(data, dict):
        candidates.append(data)
        if isinstance(data.get("values"), dict):
            candidates.append(data["values"])
    elif isinstance(data, list):
        candidates.extend([x for x in data if isinstance(x, dict)])

    for item in candidates:
        messages = item.get("messages")
        if isinstance(messages, list):
            return messages
    return []


def is_ai_message(message: dict[str, T.Any]) -> bool:
    role = str(message.get("role", "")).lower()
    if role in {"assistant", "ai"}:
        return True

    msg_type = str(message.get("type", "")).lower()
    if msg_type in {"ai", "assistant", "aimessage", "aimessagechunk"}:
        return True
    if "ai" in msg_type and all(
        token not in msg_type for token in ("human", "tool", "system")
    ):
        return True
    return False


def extract_latest_ai_text(messages: Iterable[T.Any]) -> str:
    # Scan backwards to get the latest assistant/ai message text.
    if isinstance(messages, (list, tuple)):
        iterable = reversed(messages)
    else:
        # Fallback for generic iterables (e.g. generators).
        iterable = reversed(list(messages))

    for msg in iterable:
        if not isinstance(msg, dict):
            continue
        if is_ai_message(msg):
            text = extract_text(msg.get("content"))
            if text:
                return text
    return ""


def is_clarification_tool_message(message: dict[str, T.Any]) -> bool:
    msg_type = str(message.get("type", "")).lower()
    tool_name = str(message.get("name", "")).lower()
    return msg_type == "tool" and tool_name == "ask_clarification"


def extract_latest_clarification_text(messages: Iterable[T.Any]) -> str:
    if isinstance(messages, (list, tuple)):
        iterable = reversed(messages)
    else:
        iterable = reversed(list(messages))

    for msg in iterable:
        if not isinstance(msg, dict):
            continue
        if is_clarification_tool_message(msg):
            text = extract_text(msg.get("content"))
            if text:
                return text
    return ""


def get_message_id(message: T.Any) -> str:
    if not isinstance(message, dict):
        return ""
    msg_id = message.get("id")
    return msg_id if isinstance(msg_id, str) else ""


def extract_event_message_obj(data: T.Any) -> dict[str, T.Any] | None:
    msg_obj = data
    if isinstance(data, (list, tuple)) and data:
        msg_obj = data[0]
    if isinstance(msg_obj, dict) and isinstance(msg_obj.get("data"), dict):
        # Some servers wrap message body in {"data": {...}}
        msg_obj = msg_obj["data"]
    return msg_obj if isinstance(msg_obj, dict) else None


def extract_ai_delta_from_event_data(data: T.Any) -> str:
    # LangGraph messages-tuple events usually carry either:
    # - {"type": "ai", "content": "..."}
    # - [message_obj, metadata]
    msg_obj = extract_event_message_obj(data)
    if not msg_obj:
        return ""
    if is_ai_message(msg_obj):
        return extract_text(msg_obj.get("content"))
    return ""


def extract_clarification_from_event_data(data: T.Any) -> str:
    msg_obj = extract_event_message_obj(data)
    if not msg_obj:
        return ""
    if is_clarification_tool_message(msg_obj):
        return extract_text(msg_obj.get("content"))
    return ""


def _iter_custom_event_items(data: T.Any) -> list[dict[str, T.Any]]:
    items: list[dict[str, T.Any]] = []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                items.append(item)
            elif isinstance(item, (list, tuple)):
                for nested in item:
                    if isinstance(nested, dict):
                        items.append(nested)
    return items


def extract_task_failures_from_custom_event(data: T.Any) -> list[str]:
    failures: list[str] = []
    for item in _iter_custom_event_items(data):
        event_type = str(item.get("type", "")).lower()
        if event_type not in {"task_failed", "task_timed_out"}:
            continue

        task_id = str(item.get("task_id", "")).strip()
        error_text = extract_text(item.get("error")).strip()
        if task_id and error_text:
            failures.append(f"{task_id}: {error_text}")
        elif error_text:
            failures.append(error_text)
        elif task_id:
            failures.append(f"{task_id}: unknown error")
        else:
            failures.append("unknown task failure")
    return failures


def build_task_failure_summary(failures: list[str]) -> str:
    if not failures:
        return ""
    deduped: list[str] = []
    seen: set[str] = set()
    for failure in failures:
        if failure not in seen:
            seen.add(failure)
            deduped.append(failure)
    if len(deduped) == 1:
        return f"DeerFlow subtask failed: {deduped[0]}"
    joined = "\n".join([f"- {item}" for item in deduped[:5]])
    return f"DeerFlow subtasks failed:\n{joined}"
