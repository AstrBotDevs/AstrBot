from __future__ import annotations

from collections.abc import Iterable


def _normalize_text_items(items: Iterable[object] | None) -> list[str]:
    normalized: list[str] = []
    if not items:
        return normalized
    for item in items:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _render_long_term_facts_block(facts: list[str]) -> str:
    if not facts:
        return ""
    lines = [
        "<long_term_facts>",
        "Use these retrieved long-term facts when relevant:",
    ]
    for idx, fact in enumerate(facts, start=1):
        lines.append(f"{idx}. {fact}")
    lines.append("</long_term_facts>")
    return "\n".join(lines)


def _render_summarized_history_block(summary: str) -> str:
    text = str(summary or "").strip()
    if not text:
        return ""
    return "\n".join(
        [
            "<summarized_history>",
            text,
            "</summarized_history>",
        ]
    )


def assemble_system_prompt(
    *,
    base_system_prompt: str,
    retrieved_long_term_facts: Iterable[object] | None = None,
    summarized_history: str = "",
    pinned_memory_block: str = "",
) -> str:
    """Assemble final system prompt with stable section ordering.

    Section order:
    1) Base system prompt
    2) Retrieved long-term facts
    3) Summarized history
    4) Pinned top-level memory
    """
    sections: list[str] = []
    base = str(base_system_prompt or "").strip()
    if base:
        sections.append(base)

    facts_block = _render_long_term_facts_block(
        _normalize_text_items(retrieved_long_term_facts)
    )
    if facts_block:
        sections.append(facts_block)

    summary_block = _render_summarized_history_block(summarized_history)
    if summary_block:
        sections.append(summary_block)

    pinned = str(pinned_memory_block or "").strip()
    if pinned:
        sections.append(pinned)

    return "\n\n".join(sections).strip()
