"""分段回复（segmented reply）共享工具。

ResultDecorateStage 与 send_message_to_user 等绕过 pipeline 直接发送消息的
路径共用这里的分段逻辑，保证两条路径的分段行为一致。
See https://github.com/AstrBotDevs/AstrBot/issues/8325
"""

import math
import random
import re
import traceback

from astrbot.core import logger

# 这些平台不支持主动分段发送（只能被动回复），与 pipeline 各阶段保持一致。
SEGMENTED_REPLY_UNSUPPORTED_PLATFORMS = (
    "qq_official_webhook",
    "weixin_official_account",
    "dingtalk",
)

DEFAULT_SPLIT_REGEX = r".*?[。？！~…]+|.+$"
DEFAULT_SPLIT_WORDS = ["。", "？", "！", "~", "…"]
DEFAULT_INTERVAL_RANGE = (1.5, 3.5)


def _normalize_split_words(split_words: list[str]) -> list[str]:
    if not isinstance(split_words, (list, tuple)):
        return []
    result = []
    for word in split_words:
        if word is None:
            continue
        word = str(word)
        if word:
            result.append(word)
    return result


def _normalize_regex_segments(segments) -> list[str]:
    result = []
    for seg in segments:
        if isinstance(seg, tuple):
            seg = "".join(part for part in seg if isinstance(part, str))
        elif not isinstance(seg, str):
            seg = str(seg)
        result.append(seg)
    return result


def compile_split_words_pattern(split_words: list[str]) -> re.Pattern | None:
    """编译分段词列表对应的正则。split_words 为空时返回 None。"""
    split_words = _normalize_split_words(split_words)
    if not split_words:
        return None
    escaped_words = sorted(
        [re.escape(word) for word in split_words], key=len, reverse=True
    )
    return re.compile(f"(.*?({'|'.join(escaped_words)})|.+$)", re.DOTALL)


def split_text_by_words(
    text: str,
    split_words: list[str],
    split_words_pattern: re.Pattern | None,
) -> list[str]:
    """使用分段词列表分段文本"""
    if not split_words_pattern:
        return [text]

    split_words = _normalize_split_words(split_words)
    segments = split_words_pattern.findall(text)
    result = []
    for seg in segments:
        if isinstance(seg, tuple):
            content = seg[0]
            if not isinstance(content, str):
                continue
            for word in split_words:
                if content.endswith(word):
                    content = content[: -len(word)]
                    break
            if content.strip():
                result.append(content)
        elif seg and seg.strip():
            result.append(seg)
    return result if result else [text]


def split_text_by_regex(text: str, regex: str) -> list[str]:
    """使用正则表达式分段文本，正则非法时回退到默认分段正则。"""
    if not isinstance(regex, str):
        logger.error(f"分段回复正则表达式类型错误，使用默认分段方式: {type(regex)}")
        regex = DEFAULT_SPLIT_REGEX
    try:
        return _normalize_regex_segments(
            re.findall(regex, text, re.DOTALL | re.MULTILINE),
        )
    except Exception:
        logger.error(
            f"分段回复正则表达式错误，使用默认分段方式: {traceback.format_exc()}",
        )
        return _normalize_regex_segments(
            re.findall(DEFAULT_SPLIT_REGEX, text, re.DOTALL | re.MULTILINE),
        )


def cleanup_segments(segments: list[str], content_cleanup_rule: str) -> list[str]:
    """对分段结果应用内容过滤正则并去除空白段。"""
    result = []
    for seg in segments:
        if content_cleanup_rule:
            seg = re.sub(content_cleanup_rule, "", seg)
        seg = seg.strip()
        if seg:
            result.append(seg)
    return result


def parse_interval_range(interval: str) -> tuple[float, float]:
    """解析 "最小值,最大值" 形式的间隔配置，非法时回退默认值。"""
    try:
        parts = [float(t) for t in interval.replace(" ", "").split(",") if t]
        if len(parts) >= 2:
            return parts[0], parts[1]
        if len(parts) == 1:
            return parts[0], parts[0]
        raise ValueError(f"invalid interval: {interval!r}")
    except (TypeError, ValueError, AttributeError) as e:
        logger.error(f"解析分段回复的间隔时间失败。{e}")
        return DEFAULT_INTERVAL_RANGE


def count_words(text: str) -> int:
    """分段回复 统计字数"""
    if all(ord(c) < 128 for c in text):
        word_count = len(text.split())
    else:
        word_count = len([c for c in text if c.isalnum()])
    return word_count


def calc_segment_interval(
    text: str | None,
    interval_method: str,
    interval_range: tuple[float, float],
    log_base: float,
) -> float:
    """计算一段消息发送前的间隔时间。text 为 None 表示非纯文本消息段。"""
    if interval_method == "log":
        if text is not None:
            wc = count_words(text)
            safe_log_base = (
                log_base
                if isinstance(log_base, (int, float)) and log_base > 1.0
                else 2.6
            )
            try:
                i = math.log(wc + 1, safe_log_base)
                interval = random.uniform(i, i + 0.5)
            except Exception:
                interval = random.uniform(1, 1.75)
            return max(0.0, interval)
        return max(0.0, random.uniform(1, 1.75))
    # random
    low = max(0.0, float(interval_range[0]))
    high = max(0.0, float(interval_range[1]))
    return max(0.0, random.uniform(low, high))
