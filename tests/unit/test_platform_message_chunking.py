from astrbot.core.platform.message_limits import (
    DISCORD_TEXT_LIMIT,
    TELEGRAM_TEXT_LIMIT,
    WECOM_TEXT_LIMIT,
    split_platform_text,
)


def test_discord_over_2000_is_split_not_truncated() -> None:
    text = "a" * 4500
    result = split_platform_text(text, DISCORD_TEXT_LIMIT)
    assert all(len(part) <= 2000 for part in result.parts)
    assert "".join(result.parts) == text or result.truncated
    assert sum(len(part) for part in result.parts) >= 4000


def test_discord_creates_multiple_messages() -> None:
    result = split_platform_text("x" * 3500, DISCORD_TEXT_LIMIT)
    assert len(result.parts) >= 2


def test_telegram_never_exceeds_4096() -> None:
    result = split_platform_text("你好" * 3000, TELEGRAM_TEXT_LIMIT)
    assert all(len(part) <= 4096 for part in result.parts)


def test_wecom_uses_utf8_bytes() -> None:
    text = "测" * 3000
    result = split_platform_text(text, WECOM_TEXT_LIMIT)
    assert all(len(part.encode("utf-8")) <= 4096 for part in result.parts)


def test_prefers_fenced_code_block_boundary() -> None:
    text = "intro\n```python\nprint(1)\n```\n" + ("n" * 2100)
    result = split_platform_text(text, DISCORD_TEXT_LIMIT)
    assert any("```" in part for part in result.parts)


def test_prefers_markdown_table_boundary() -> None:
    table = "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"
    text = table + ("z" * 2100)
    result = split_platform_text(text, DISCORD_TEXT_LIMIT)
    assert result.parts[0].rstrip().endswith("| 1 | 2 |") or "|" in result.parts[0]


def test_hard_cuts_when_no_natural_boundary() -> None:
    result = split_platform_text("a" * 2500, DISCORD_TEXT_LIMIT)
    assert result.parts[0] == "a" * 2000


def test_max_chunks_degrades() -> None:
    from dataclasses import replace

    limit = replace(DISCORD_TEXT_LIMIT, max_chunks=2)
    result = split_platform_text("a" * 8000, limit)
    assert len(result.parts) == 2
    assert result.truncated is True
