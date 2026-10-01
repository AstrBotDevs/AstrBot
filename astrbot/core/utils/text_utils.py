import re


def calculate_word_count(text: str) -> int:
    """
    将不同语言分开计算
    - 中文/日语: 按字数计算
    - 其他语言: 按空格分割计算
    """
    # \u4e00-\u9fff : CJK Unified Ideographs (Chinese Hanzi & Japanese Kanji)
    # \u3040-\u309f : Japanese Hiragana
    # \u30a0-\u30ff : Japanese Katakana
    no_space_pattern = r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]"

    char_count = len(re.findall(no_space_pattern, text))

    text_remaining = re.sub(no_space_pattern, " ", text)

    spaced_words = len(text_remaining.split())

    return char_count + spaced_words
