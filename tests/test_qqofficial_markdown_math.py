import re

import pytest
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

from astrbot.core.platform.sources.qqofficial.qq_markdown_math import (
    QQMarkdownMathState,
    normalize_qq_list_math,
)

FORMULA = r"E_p = 4mgL = \frac{1}{2} I \omega^2 = \frac{4g}{3L}"
REPORTED = (
    "1. **Find angular speed:**\n"
    f"   $${FORMULA}$$\n\n"
    "2. **Compute the force:**\n"
    "   * Apply Newton's law:\n"
    r"     $$F - 3mg = 3m \frac{16}{9}g$$"
    "\n"
    r"     $$F = \frac{25}{3}mg$$"
    "\n"
)


def math_blocks(text):
    return [
        token
        for token in MarkdownIt("commonmark").use(dollarmath_plugin).parse(text)
        if token.type == "math_block"
    ]


def outline(text):
    """(list depth, text) for each paragraph, ignoring display math."""
    depth = 0
    result = []
    tokens = MarkdownIt("commonmark").use(dollarmath_plugin).parse(text)
    for index, token in enumerate(tokens):
        if token.type in {"bullet_list_open", "ordered_list_open"}:
            depth += 1
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            depth -= 1
        elif token.type == "inline" and tokens[index - 1].type == "paragraph_open":
            result.append((depth, token.content))
    return result


@pytest.mark.parametrize("marker", ["*", "-", "+", "1.", "123.", "2)"])
def test_list_math_is_root_block_and_formula_is_unchanged(marker):
    indent = " " * (len(marker) + 1)
    source = f"{marker} Equation:\n{indent}$${FORMULA}$$\n"
    result = normalize_qq_list_math(source)
    blocks = math_blocks(result)
    assert len(blocks) == 1
    assert blocks[0].level == 0
    assert blocks[0].content == FORMULA
    assert source.splitlines()[0] in result


def test_nested_lists_and_adjacent_equations():
    result = normalize_qq_list_math(REPORTED)
    blocks = math_blocks(result)
    assert len(blocks) == 3
    assert all(block.level == 0 for block in blocks)
    assert re.findall(r"\$\$(.*?)\$\$", result, re.S) == re.findall(
        r"\$\$(.*?)\$\$", REPORTED, re.S
    )
    assert "2. **Compute the force:**" in result
    assert normalize_qq_list_math(result) == result


def test_paragraph_and_code_after_lifted_math_keep_their_meaning():
    source = (
        "123. Example:\n"
        "     $$x = 1$$\n"
        "     The result is positive.\n\n"
        "     ```python\n"
        "     if value:\n"
        "         print(value)\n"
        "     ```\n\n"
        "     1. Follow-up item\n"
        "        with a continuation.\n"
    )
    result = normalize_qq_list_math(source)
    parser = MarkdownIt("commonmark")
    before = next(t for t in parser.parse(source) if t.type == "fence")
    after = next(t for t in parser.parse(result) if t.type == "fence")
    assert before.content == after.content
    assert not any(t.type == "code_block" for t in parser.parse(result))
    assert math_blocks(result)[0].level == 0
    # The paragraph, fence and nested list stay inside the (reopened) item.
    assert outline(result) == [
        (1, "Example:"),
        (1, "The result is positive."),
        (2, "Follow-up item\nwith a continuation."),
    ]


@pytest.mark.parametrize(
    "source",
    [
        "Ordinary text with a URL https://example.com/a?b=c and no math.\n",
        "1. First\n2. Second\n",
        "Text.\n\n$$x = 1$$\n",
        "```markdown\n- Example:\n  $$literal$$\n```\n",
        "~~~markdown\n- Example:\n  $$literal$$\n~~~\n",
        "1. Code:\n\n       $$literal$$\n",
        "- Use `$$literal$$` here.\n",
        "- `a\n  $$literal$$\n  b`\n",
        "- Incomplete:\n  $$x + y\n",
        "- Text:\n  $$x$$ followed by prose\n",
        "<pre>\n- $$literal$$\n</pre>\n",
    ],
)
def test_unrelated_or_ambiguous_content_is_unchanged(source):
    assert normalize_qq_list_math(source) == source


def test_math_as_the_entire_list_item():
    result = normalize_qq_list_math("- $$x = 1$$\n- Next\n")
    assert result == "$$x = 1$$\n\n- Next\n"
    assert math_blocks(result)[0].level == 0


def test_multiline_equation_preserves_interior_whitespace():
    source = "1. Equation:\n   $$\n   a + b\n   = c\n   $$\n"
    result = normalize_qq_list_math(source)
    assert re.findall(r"\$\$(.*?)\$\$", source, re.S) == re.findall(
        r"\$\$(.*?)\$\$", result, re.S
    )
    assert len(math_blocks(result)) == 1
    assert math_blocks(result)[0].level == 0


def test_bracket_delimited_math():
    source = "- Equation:\n  \\[a + b = c\\]\n- Next\n"
    assert normalize_qq_list_math(source) == (
        "- Equation:\n\n\\[a + b = c\\]\n\n- Next\n"
    )


def test_crlf_is_preserved():
    result = normalize_qq_list_math("- Equation:\r\n  $$x = 1$$\r\n")
    assert "\r\n\r\n$$x = 1$$\r\n" in result
    assert re.search(r"(?<!\r)\n", result) is None


@pytest.mark.parametrize("boundary", range(1, len(REPORTED)))
def test_every_stream_boundary_preserves_deltas_and_final_content(boundary):
    state = QQMarkdownMathState()
    prefix, suffix = REPORTED[:boundary], REPORTED[boundary:]
    first = {"state": 1, "index": 0, "reset": False}
    first_content, first_stream = state.prepare(prefix, first)
    assert first_content == prefix
    assert first_stream is first
    final = {"state": 10, "index": 1, "id": "test-stream", "reset": False}
    final_content, final_stream = state.prepare(suffix, final)
    displayed = final_content if final_stream["reset"] else prefix + final_content
    assert displayed == normalize_qq_list_math(REPORTED)
    assert final["reset"] is False
    assert final_stream["state"] == 10
    assert final_stream["id"] == "test-stream"


def test_empty_final_frame_and_independent_next_stream():
    state = QQMarkdownMathState()
    state.prepare(REPORTED, {"state": 1, "index": 0})
    content, stream = state.prepare("\n", {"state": 10, "index": 1, "id": "first"})
    assert stream["reset"] is True
    assert content == normalize_qq_list_math(REPORTED + "\n")
    state.prepare("Next ", {"state": 1, "index": 0})
    final = {"state": 10, "index": 1, "id": "second", "reset": False}
    assert state.prepare("response.\n", final) == ("response.\n", final)


def test_unknown_stream_prefix_is_not_overwritten():
    state = QQMarkdownMathState()
    frame = {"state": 10, "index": 8, "id": "unknown", "reset": False}
    assert state.prepare(REPORTED, frame) == (REPORTED, frame)


def test_snapshot_restarts_index_after_multiple_deltas():
    state = QQMarkdownMathState()
    chunks = [REPORTED[:12], REPORTED[12:70], REPORTED[70:]]
    for index, chunk in enumerate(chunks):
        frame = {"state": 1, "index": index, "reset": False}
        if index:
            frame["id"] = "same-card"
        assert state.prepare(chunk, frame) == (chunk, frame)
    final = {"state": 10, "index": 3, "id": "same-card", "reset": False}
    content, stream = state.prepare("\n", final)
    assert stream == {"state": 10, "index": 1, "id": "same-card", "reset": True}
    assert final["index"] == 3
    assert content == normalize_qq_list_math(REPORTED + "\n")


def test_first_and_final_frame_needs_no_reset():
    state = QQMarkdownMathState()
    content, stream = state.prepare(REPORTED, {"state": 10, "index": 0})
    assert content == normalize_qq_list_math(REPORTED)
    assert not stream.get("reset")


def test_nonstream_send_clears_previous_stream_state():
    state = QQMarkdownMathState()
    state.prepare("Old prefix", {"state": 1, "index": 0})
    assert state.prepare(REPORTED, None) == (normalize_qq_list_math(REPORTED), None)
    final = {"state": 10, "index": 1, "id": "unknown"}
    assert state.prepare("Tail", final) == ("Tail", final)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "1. Item:\n   - Sub:\n     $$x$$\n     after\n     - child\n"
            "   - sibling\n2. Next\n",
            [
                (1, "Item:"),
                (2, "Sub:"),
                (2, "after"),
                (3, "child"),
                (2, "sibling"),
                (1, "Next"),
            ],
        ),
        (
            "- A\n  $$x$$\n  para\n  - nested\n    more\n- B\n",
            [(1, "A"), (1, "para"), (2, "nested\nmore"), (1, "B")],
        ),
        (
            "* Outer\n  1) Inner\n     $$x$$\n\n     tail\n  2) Second\n* Last\n",
            [(1, "Outer"), (2, "Inner"), (2, "tail"), (2, "Second"), (1, "Last")],
        ),
    ],
)
def test_content_after_lifted_math_keeps_its_nesting_depth(source, expected):
    result = normalize_qq_list_math(source)
    assert len(math_blocks(result)) == 1
    assert math_blocks(result)[0].level == 0
    assert outline(result) == expected
    assert normalize_qq_list_math(result) == result


@pytest.mark.parametrize("quote", ["> ", ">", "> > "])
def test_list_math_inside_blockquote_is_lifted(quote):
    source = "".join(
        quote + line for line in ["- Equation:\n", f"  $${FORMULA}$$\n", "- Next\n"]
    )
    result = normalize_qq_list_math(source)
    tokens = MarkdownIt("commonmark").use(dollarmath_plugin).parse(result)
    block = next(t for t in tokens if t.type == "math_block")
    assert block.content == FORMULA
    # Only the blockquote containers remain around the equation, no list.
    assert block.level == quote.count(">")
    assert sum(t.type == "blockquote_open" for t in tokens) == quote.count(">")
    assert outline(result) == [(1, "Equation:"), (1, "Next")]
