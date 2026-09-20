"""提示词注入检测。

检测用户输入里试图劫持指令、套取系统提示词、越狱、伪造分隔符
或做编码混淆的内容。检测结果按策略处理：拦截 / 清洗 / 警告 / 仅记录。
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

__all__ = [
    "DEFAULT_RULES",
    "STRATEGY_BLOCK",
    "STRATEGY_LOG",
    "STRATEGY_SANITIZE",
    "STRATEGY_WARN",
    "VALID_STRATEGIES",
    "InjectionGuardResult",
    "InjectionMatch",
    "PromptInjectionGuard",
]

STRATEGY_BLOCK = "block"
STRATEGY_SANITIZE = "sanitize"
STRATEGY_WARN = "warn"
STRATEGY_LOG = "log"

VALID_STRATEGIES = (STRATEGY_BLOCK, STRATEGY_SANITIZE, STRATEGY_WARN, STRATEGY_LOG)


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    severity: str = "medium"
    description: str = ""


def _rule(name: str, pattern: str, severity: str, description: str) -> Rule:
    return Rule(
        name=name,
        pattern=re.compile(pattern, re.IGNORECASE | re.MULTILINE),
        severity=severity,
        description=description,
    )


DEFAULT_RULES: tuple[Rule, ...] = (
    _rule(
        "pi_ignore_instructions",
        r"(忽略|无视|忘记|抛弃|不要理会|请忽略|请无视)[^。\n]{0,12}"
        r"(以上|上面|之前|前面|所有|全部|先前)[^。\n]{0,12}"
        r"(指令|指示|命令|要求|设定|规则|提示|prompt|instruction)",
        "high",
        "中文：要求忽略之前的指令",
    ),
    _rule(
        "pi_ignore_instructions_en",
        r"\b(ignore|disregard|forget|override|discard)\b[^.!?\n]{0,30}"
        r"\b(previous|prior|above|earlier|all|any)\b[^.!?\n]{0,20}"
        r"\b(instruction|prompt|rule|command|direction)s?\b",
        "high",
        "英文：要求忽略之前的指令",
    ),
    _rule(
        "pi_reveal_system_prompt",
        r"(重复|复述|输出|打印|告诉我|显示|展示|说出)[^。\n]{0,12}"
        r"(你的|你的所有|系统|初始|原始|上面|前面)[^。\n]{0,8}"
        r"(提示词|设定|指令|规则|prompt|system\s*prompt|设定词)",
        "high",
        "中文：试图套取系统提示词",
    ),
    _rule(
        "pi_reveal_system_prompt_en",
        r"\b(repeat|print|show|reveal|output|tell me|display|dump)\b[^.!?\n]{0,25}"
        r"\b(your|the)\b[^.!?\n]{0,15}"
        r"\b(system\s*prompt|initial\s*prompt|instructions?|rules?|prompt)\b",
        "high",
        "英文：试图套取系统提示词",
    ),
    _rule(
        "pi_role_hijack",
        r"(从现在起|现在开始|接下来|之后)[^。\n]{0,10}(你|你要|请你)?[^。\n]{0,6}"
        r"(扮演|充当|假装|成为|是)[^。\n]{0,20}",
        "medium",
        "中文：要求改变角色身份",
    ),
    _rule(
        "pi_role_hijack_en",
        r"\b(from now on|starting now|henceforth)\b[^.!?\n]{0,30}"
        r"\b(you are|act as|pretend|behave as|become)\b",
        "medium",
        "英文：要求改变角色身份",
    ),
    _rule(
        "pi_jailbreak_keyword",
        r"(DAN\s*mode|DAN模式|do\s*anything\s*now|developer\s*mode|god\s*mode|"
        r"jailbreak|unrestricted\s*mode|no\s*restrictions?\s*mode)",
        "high",
        "已知越狱模式关键词",
    ),
    _rule(
        "pi_jailbreak_cn",
        r"(开发者模式|上帝模式|无限制模式|无任何限制|不受任何限制|"
        r"解除(所有)?限制|绕过(所有)?(限制|审查|过滤)|越狱模式)",
        "high",
        "中文越狱关键词",
    ),
    _rule(
        "pi_fake_delimiter",
        r"(<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|user\|>|<\|assistant\|>|"
        r"\[/?INST\]|<<SYS>>|\[/?SYS\])",
        "high",
        "伪造对话模板分隔符",
    ),
    _rule(
        "pi_fake_role_marker",
        r"^\s*#{2,4}\s*(system|assistant|用户|系统|助手)\s*[:：]",
        "medium",
        "伪造角色分隔（Markdown 标题形式）",
    ),
    _rule(
        "pi_override_safety",
        r"(忽略|无视|关闭|取消|禁用|绕过)[^。\n]{0,10}"
        r"(安全|审查|限制|过滤|规则|策略|规范)",
        "high",
        "中文：试图关闭安全限制",
    ),
    _rule(
        "pi_override_safety_en",
        r"\b(ignore|bypass|disable|turn off|remove)\b[^.!?\n]{0,25}"
        r"\b(safety|security|filter|restriction|policy|guideline|guardrail)s?\b",
        "high",
        "英文：试图关闭安全限制",
    ),
)


@dataclass
class InjectionMatch:
    rule: str
    severity: str
    description: str
    matched_text: str
    start: int = -1
    end: int = -1


@dataclass
class InjectionGuardResult:
    detected: bool = False
    matches: list[InjectionMatch] = field(default_factory=list)
    text: str = ""
    action: str = "none"

    @property
    def max_severity(self) -> str:
        order = {"low": 0, "medium": 1, "high": 2}
        if not self.matches:
            return "none"
        return max((m.severity for m in self.matches), key=lambda s: order.get(s, 0))

    def summary(self) -> str:
        if not self.detected:
            return "no injection detected"
        names = ", ".join(sorted({m.rule for m in self.matches}))
        return f"{len(self.matches)} match(es) [{self.max_severity}]: {names}"


_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
_BASE64_BLOB = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")


def _strip_zero_width(text: str) -> tuple[str, bool]:
    had = bool(_ZERO_WIDTH.search(text))
    return _ZERO_WIDTH.sub("", text), had


def _looks_like_base64_payload(text: str) -> bool:
    for blob in _BASE64_BLOB.findall(text):
        try:
            decoded = base64.b64decode(blob, validate=True)
        except (binascii.Error, ValueError):
            continue
        printable = sum(1 for b in decoded if 32 <= b < 127) / max(len(decoded), 1)
        if printable > 0.85 and len(decoded) >= 30:
            return True
    return False


class PromptInjectionGuard:
    def __init__(
        self,
        *,
        extra_patterns: Iterable[str] | None = None,
        ignore_rules: Iterable[str] | None = None,
        enable_encoding_check: bool = True,
    ) -> None:
        ignored = set(ignore_rules or ())
        self.rules: list[Rule] = [r for r in DEFAULT_RULES if r.name not in ignored]

        for idx, pat in enumerate(extra_patterns or ()):
            try:
                self.rules.append(
                    _rule(f"pi_custom_{idx}", pat, "medium", "用户自定义规则")
                )
            except re.error:
                continue

        self.enable_encoding_check = enable_encoding_check

    def check(
        self, text: str, *, strategy: str = STRATEGY_WARN
    ) -> InjectionGuardResult:
        result = InjectionGuardResult(text=text)
        if not text:
            return result

        normalized = unicodedata.normalize("NFKC", text)

        if self.enable_encoding_check:
            cleaned, had_zero = _strip_zero_width(normalized)
            if had_zero:
                result.matches.append(
                    InjectionMatch(
                        rule="pi_zero_width",
                        severity="high",
                        description="输入含零宽字符（常用于绕过关键词过滤）",
                        matched_text="<zero-width chars>",
                    )
                )
                normalized = cleaned

            if _looks_like_base64_payload(normalized):
                result.matches.append(
                    InjectionMatch(
                        rule="pi_base64_payload",
                        severity="medium",
                        description="输入含疑似 base64 编码载荷",
                        matched_text="<base64 blob>",
                    )
                )

        for rule in self.rules:
            for m in rule.pattern.finditer(normalized):
                result.matches.append(
                    InjectionMatch(
                        rule=rule.name,
                        severity=rule.severity,
                        description=rule.description,
                        matched_text=m.group(0)[:120],
                        start=m.start(),
                        end=m.end(),
                    )
                )

        if not result.matches:
            return result

        result.detected = True
        chosen = strategy if strategy in VALID_STRATEGIES else STRATEGY_WARN

        if chosen == STRATEGY_BLOCK:
            result.action = "blocked"
            result.text = ""
        elif chosen == STRATEGY_SANITIZE:
            result.action = "sanitized"
            result.text = self.sanitize(text)
        elif chosen == STRATEGY_LOG:
            result.action = "logged"
            result.text = text
        else:
            result.action = "warned"
            result.text = text

        return result

    def sanitize(self, text: str) -> str:
        out = text
        for rule in self.rules:
            out = rule.pattern.sub("[已移除可疑内容]", out)
        if self.enable_encoding_check:
            out = _ZERO_WIDTH.sub("", out)
        return out

    def rule_names(self) -> list[str]:
        return [r.name for r in self.rules]
