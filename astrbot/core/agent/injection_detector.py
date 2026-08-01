"""正则层注入检测——在消息进入 LLM 之前做硬阻断。

检测命中时返回固定安全提醒，不进 LLM。
未命中时交给 LLM 的 prompt 层做软检测。
"""

import re
from typing import NamedTuple


class DetectionResult(NamedTuple):
    detected: bool
    pattern_type: str
    matched_text: str


# 正则列表（中英文双覆盖）
_PATTERNS: list[tuple[str, str]] = [
    # 身份覆盖
    (
        "identity_override",
        r"忽略之前|忽略.?所有|ignore\s+all\s+previous|从现在开始|你的身份是|"
        r"你是(一个|一名|我的|新的|现在)|you\s+are\s+now\s+(a|an|my)",
    ),
    # 秘密索取
    (
        "secret_request",
        r"system.?prompt|safety.?rules|tool.?list|API.?key|"
        r"密码|工具列表|安全规则|你的.?规则",
    ),
    # 绕过试探
    (
        "bypass_attempt",
        r"假装你是|角色扮演|这(只|仅)是(一个|个)测试|为了测试|"
        r"pretend\s+you\s+are|for\s+testing|this\s+is\s+(a|only).?test",
    ),
    # 身份伪装
    (
        "role_impersonation",
        r"我是管理员|我是开发者|我是系统|"
        r"i\s+am\s+(admin|root|developer|system)",
    ),
]

_compiled = [
    (ptype, re.compile(pattern, re.IGNORECASE))
    for ptype, pattern in _PATTERNS
]


def detect(text: str) -> DetectionResult:
    """扫描输入文本，检测注入模式。

    Args:
        text: 用户输入的原始文本。

    Returns:
        DetectionResult: detected=False 表示未命中，detected=True 表示命中。
    """
    if not text or not text.strip():
        return DetectionResult(False, "", "")

    for ptype, pattern in _compiled:
        match = pattern.search(text)
        if match:
            return DetectionResult(True, ptype, match.group())

    return DetectionResult(False, "", "")
