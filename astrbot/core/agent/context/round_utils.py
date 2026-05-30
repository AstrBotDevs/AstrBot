"""Round-based utilities shared by LTM compaction and LLMSummaryCompressor."""

import json
from typing import Any


def split_into_rounds(
    contexts: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Split a flat contexts list into logical rounds.

    A round begins at a ``user`` segment and includes all subsequent
    ``assistant`` / ``tool`` segments until the next ``user`` segment.
    """
    rounds: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for seg in contexts:
        if seg.get("role") == "user" and current:
            rounds.append(current)
            current = []
        current.append(seg)
    if current:
        rounds.append(current)
    return rounds


def rounds_to_text(rounds: list[list[dict[str, Any]]]) -> str:
    """Render rounds into a plain-text string for LLM summarisation."""
    lines: list[str] = []
    for i, rnd in enumerate(rounds, 1):
        lines.append(f"--- Round {i} ---")
        for seg in rnd:
            role = seg.get("role", "?")
            content = seg.get("content") or seg.get("tool_calls") or ""
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)
