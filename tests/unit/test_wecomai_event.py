"""测试企业微信智能机器人消息事件处理。

主要测试 _extract_plain_text_from_chain 方法在流式和非流式场景下的行为，
确保流式输出时换行符等格式字符能够正确保留。
"""

import pytest

from astrbot.core.message.components import At, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_event import (
    WecomAIBotMessageEvent,
)

# ============================================================
# _extract_plain_text_from_chain 基础测试
# ============================================================


def test_extract_plain_text_empty_chain():
    """空消息链应返回空字符串"""
    assert WecomAIBotMessageEvent._extract_plain_text_from_chain(None) == ""
    assert WecomAIBotMessageEvent._extract_plain_text_from_chain(MessageChain([])) == ""


def test_extract_plain_text_single_plain():
    """单个 Plain 组件应正确提取文本"""
    chain = MessageChain([Plain("你好世界")])
    assert WecomAIBotMessageEvent._extract_plain_text_from_chain(chain) == "你好世界"


def test_extract_plain_text_multiple_plains():
    """多个 Plain 组件应正确拼接"""
    chain = MessageChain([Plain("第一段"), Plain("第二段"), Plain("第三段")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain)
    assert result == "第一段第二段第三段"


def test_extract_plain_text_with_at():
    """At 组件应被转换为 @name 形式"""
    chain = MessageChain([At(qq="123", name="用户A"), Plain("你好")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain)
    assert result == "@用户A 你好"


# ============================================================
# strip_result=True（默认，非流式）测试
# ============================================================


def test_strip_result_default_strips_whitespace():
    """默认 strip_result=True 应去除首尾空白"""
    chain = MessageChain([Plain("  前后有空格  ")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain)
    assert result == "前后有空格"


def test_strip_result_default_strips_newlines():
    """默认 strip_result=True 应去除首尾换行符"""
    chain = MessageChain([Plain("\n\n多行\n文本\n\n")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain)
    assert result == "多行\n文本"


def test_strip_result_default_strips_only_newline_chunk():
    """纯换行符的 chunk 在 strip 后变为空字符串"""
    chain = MessageChain([Plain("\n")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain)
    assert result == ""


def test_strip_result_default_preserves_internal_newlines():
    """默认模式保留文本中间的换行符"""
    chain = MessageChain([Plain("第一行\n第二行\n第三行")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain)
    assert result == "第一行\n第二行\n第三行"


# ============================================================
# strip_result=False（流式输出）测试
# ============================================================


def test_no_strip_preserves_leading_whitespace():
    """strip_result=False 应保留前导空白"""
    chain = MessageChain([Plain("  前导空格文本")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(
        chain, strip_result=False
    )
    assert result == "  前导空格文本"


def test_no_strip_preserves_trailing_whitespace():
    """strip_result=False 应保留尾随空白"""
    chain = MessageChain([Plain("尾随空格文本  ")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(
        chain, strip_result=False
    )
    assert result == "尾随空格文本  "


def test_no_strip_preserves_newline_only_chunk():
    """纯换行符的 chunk 在 strip_result=False 时应被保留（流式关键场景）"""
    chain = MessageChain([Plain("\n")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(
        chain, strip_result=False
    )
    assert result == "\n"


def test_no_strip_preserves_multiline_text():
    """strip_result=False 应保留多行文本的所有格式"""
    text = "第一行\n\n第二行\n第三行\n"
    chain = MessageChain([Plain(text)])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(
        chain, strip_result=False
    )
    # 流式模式不 strip，完整保留原文本
    assert result == text


def test_no_strip_preserves_leading_newline():
    """strip_result=False 应保留文本开头的换行符"""
    chain = MessageChain([Plain("\n开头换行")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(
        chain, strip_result=False
    )
    assert result == "\n开头换行"


def test_no_strip_preserves_tab_characters():
    """strip_result=False 应保留制表符 \t（与 \n 同理）"""
    chain = MessageChain([Plain("\t缩进文本")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(
        chain, strip_result=False
    )
    assert result == "\t缩进文本"


def test_no_strip_preserves_tab_only_chunk():
    """纯制表符的 chunk 在 strip_result=False 时应被保留"""
    chain = MessageChain([Plain("\t")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(
        chain, strip_result=False
    )
    assert result == "\t"


def test_strip_result_default_strips_tab_chunk():
    """对比：strip_result=True（默认）时纯 \t 也会变空字符串"""
    chain = MessageChain([Plain("\t")])
    result = WecomAIBotMessageEvent._extract_plain_text_from_chain(
        chain, strip_result=True
    )
    assert result == ""


# ============================================================
# 流式场景模拟测试：模拟 LLM 分 chunk 输出
# ============================================================


def simulate_streaming(plain_chunks: list[str], strip_result: bool) -> str:
    """模拟流式输出：将多个 chunk 依次传递给 _extract_plain_text_from_chain 并拼接"""
    accumulated = ""
    for chunk_text in plain_chunks:
        chain = MessageChain([Plain(chunk_text)])
        extracted = WecomAIBotMessageEvent._extract_plain_text_from_chain(
            chain, strip_result=strip_result
        )
        if extracted:
            accumulated += extracted
    return accumulated


def test_streaming_simulation_preserves_newlines():
    """模拟 LLM 流式输出，验证 strip_result=False 时换行被保留"""
    # 模拟 LLM 分 chunk 返回带换行的内容
    chunks = ["第一行", "\n", "第二行", "\n\n", "第三行"]
    result = simulate_streaming(chunks, strip_result=False)
    assert result == "第一行\n第二行\n\n第三行"


def test_streaming_simulation_strips_newlines_with_default():
    """对比：strip_result=True（默认）时换行被丢弃（Bug 复现）"""
    chunks = ["第一行", "\n", "第二行", "\n\n", "第三行"]
    result = simulate_streaming(chunks, strip_result=True)
    # 纯换行 chunk 被 strip 为空字符串并跳过，多 chunk 拼接时换行丢失
    assert result == "第一行第二行第三行"
    # 注意：这就是 Bug #8474 的根因 — 流式输出中换行全部丢失


def test_streaming_simulation_markdown_formatting():
    """模拟 LLM 返回 Markdown 格式内容，验证格式保留"""
    chunks = [
        "**标题**",
        "\n",
        "- 项目1",
        "\n",
        "- 项目2",
        "\n",
        "\n",
        "正文内容。",
    ]
    result = simulate_streaming(chunks, strip_result=False)
    assert result == "**标题**\n- 项目1\n- 项目2\n\n正文内容。"


def test_streaming_simulation_code_block():
    """模拟 LLM 返回代码块，验证格式保留"""
    chunks = [
        "```python",
        "\n",
        "print('hello')",
        "\n",
        "print('world')",
        "\n",
        "```",
    ]
    result = simulate_streaming(chunks, strip_result=False)
    assert result == "```python\nprint('hello')\nprint('world')\n```"


def test_streaming_simulation_preserves_tabs():
    """模拟 LLM 分 chunk 输出含 \t 的内容，验证制表符被保留"""
    chunks = ["项目", "\t", "描述", "\t", "备注"]
    result = simulate_streaming(chunks, strip_result=False)
    assert result == "项目\t描述\t备注"


def test_streaming_simulation_strips_tabs_with_default():
    """对比：strip_result=True（默认）时 \t chunk 被丢弃（同样会发生）"""
    chunks = ["项目", "\t", "描述", "\t", "备注"]
    result = simulate_streaming(chunks, strip_result=True)
    assert result == "项目描述备注"


# ============================================================
# strip_result 参数类型安全测试
# ============================================================


def test_strip_result_param_is_explicit():
    """strip_result 是显式关键字参数，不影响位置参数调用"""
    chain = MessageChain([Plain("测试")])
    # 不传 strip_result，使用默认值 True
    result1 = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain)
    # 显式传 strip_result=True
    result2 = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain, True)
    assert result1 == result2 == "测试"


def test_strip_result_false_prevents_whitespace_loss():
    """验证 strip_result 参数机制：False 时保留空白，True 时去除"""
    text = "  内容  "
    chain = MessageChain([Plain(text)])

    stripped = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain, True)
    notStripped = WecomAIBotMessageEvent._extract_plain_text_from_chain(chain, False)

    assert stripped == "内容"
    assert notStripped == "  内容  "
    assert stripped != notStripped
