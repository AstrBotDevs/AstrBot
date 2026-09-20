"""Round-based utilities shared by LTM compaction and LLMSummaryCompressor."""

import json
from collections.abc import Sequence
from typing import Any

from ..message import ContentPart, Message, ToolCall

RoundSegment = dict[str, Any] | Message


def _segment_role(seg: RoundSegment) -> str:
    if isinstance(seg, Message):
        return seg.role
    return str(seg.get("role", "?"))


def split_into_rounds(
    contexts: Sequence[RoundSegment],
) -> list[list[RoundSegment]]:
    """Split a flat contexts list into logical rounds.

    A round begins at a ``user`` segment and includes all subsequent
    ``assistant`` / ``tool`` segments until the next ``user`` segment.
    """
    rounds: list[list[RoundSegment]] = []
    current: list[RoundSegment] = []
    for seg in contexts:
        if _segment_role(seg) == "user" and current:
            rounds.append(current)
            current = []
        current.append(seg)
    if current:
        rounds.append(current)
    return rounds


def _content_to_text(content: Any) -> str:
    if isinstance(content, list):
        normalized = [
            part.model_dump_for_context() if isinstance(part, ContentPart) else part
            for part in content
        ]
        return json.dumps(normalized, ensure_ascii=False)
    if isinstance(content, ContentPart):
        return json.dumps(content.model_dump_for_context(), ensure_ascii=False)
    return str(content or "")


def _segment_content(seg: RoundSegment) -> Any:
    if isinstance(seg, Message):
        if seg.content is not None:
            return seg.content
        if seg.tool_calls:
            return [
                tc.model_dump() if isinstance(tc, ToolCall) else tc
                for tc in seg.tool_calls
            ]
        return ""
    return seg.get("content") or seg.get("tool_calls") or ""


def rounds_to_text(rounds: list[list[RoundSegment]]) -> str:
    """Render rounds into a plain-text string for LLM summarisation."""
    lines: list[str] = []
    for i, rnd in enumerate(rounds, 1):
        lines.append(f"--- Round {i} ---")
        for seg in rnd:
            role = _segment_role(seg)
            content = _content_to_text(_segment_content(seg))
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)
