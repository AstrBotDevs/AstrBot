"""人格 / 语言锚定。

在工具调用、处理结构化数据或上下文压缩之后，模型容易跳出角色、
自称 AI 助手，或中英文混排。本模块生成几段提示文本用于抑制这些现象。
"""

from __future__ import annotations

import re

__all__ = [
    "DEFAULT_ANCHOR_TEMPLATE",
    "DEFAULT_HARDENING_LINE",
    "DEFAULT_LANGUAGE_RULE",
    "LANGUAGE_NAMES",
    "build_language_rule",
    "build_persona_anchor",
    "build_persona_hardening",
    "detect_mixed_language",
    "normalize_language",
]

DEFAULT_ANCHOR_TEMPLATE = (
    "<persona_anchor>\n"
    "请继续以「{persona}」的身份与语气回应。\n"
    "- 不要自称 AI、语言模型、助手或机器人。\n"
    "- 不要描述你正在「执行任务」或「调用工具」。\n"
    "- 即使刚刚获取了外部数据，也请用符合角色设定的口吻转述。\n"
    "</persona_anchor>"
)

DEFAULT_HARDENING_LINE = (
    "无论你正在进行何种操作（包括查询资料、调用工具、处理结构化数据），"
    "都必须始终以以上身份设定回应；"
    "不要跳出角色，也不要自称 AI 或语言模型。"
)

DEFAULT_LANGUAGE_RULE = (
    "<language_rule>\n"
    "始终使用{lang}回复，除非用户明确要求换语言。\n"
    "- 不要在中文句子里夹杂英文单词（专有名词、代码、命令除外）。\n"
    "- 专有名词（如 GitHub、Python）、代码、命令、报错信息可以保留原文。\n"
    "</language_rule>"
)


LANGUAGE_NAMES: dict[str, str] = {
    "zh": "中文",
    "zh-cn": "简体中文",
    "zh-tw": "繁體中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "ru": "Русский",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
}


def build_persona_anchor(persona: str, *, template: str | None = None) -> str:
    name = (persona or "").strip()
    if not name:
        return ""

    tpl = template or DEFAULT_ANCHOR_TEMPLATE
    try:
        return tpl.format(persona=name)
    except (KeyError, IndexError, ValueError):
        return DEFAULT_ANCHOR_TEMPLATE.format(persona=name)


def build_persona_hardening(persona: str = "", *, line: str | None = None) -> str:
    text = (line or DEFAULT_HARDENING_LINE).strip()
    if not text:
        return ""
    if persona.strip():
        return f"{text}（当前身份：{persona.strip()}）"
    return text


def normalize_language(lang: str) -> str:
    key = (lang or "").strip().lower()
    if not key:
        return ""
    return LANGUAGE_NAMES.get(key, (lang or "").strip())


def build_language_rule(language: str, *, template: str | None = None) -> str:
    name = normalize_language(language)
    if not name:
        return ""

    tpl = template or DEFAULT_LANGUAGE_RULE
    try:
        return tpl.format(lang=name)
    except (KeyError, IndexError, ValueError):
        return DEFAULT_LANGUAGE_RULE.format(lang=name)


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")

# 这些词算专有名词 / 技术词，出现在中文里不算混排
_LATIN_WHITELIST = {
    "ai",
    "api",
    "app",
    "bug",
    "cpu",
    "css",
    "csv",
    "dns",
    "excel",
    "git",
    "github",
    "gpu",
    "html",
    "http",
    "https",
    "id",
    "ip",
    "java",
    "json",
    "linux",
    "mac",
    "macos",
    "markdown",
    "mysql",
    "node",
    "npm",
    "ok",
    "pdf",
    "php",
    "python",
    "qt",
    "ram",
    "redis",
    "sql",
    "ssh",
    "token",
    "ui",
    "url",
    "usb",
    "ux",
    "vip",
    "vscode",
    "web",
    "windows",
    "word",
    "xml",
    "yaml",
    "zip",
}


def detect_mixed_language(text: str, *, max_ratio: float = 0.35) -> bool:
    """粗略判断文本是否中英混排（白名单内的专有名词不计）。

    独立工具函数，供调用方与测试使用；请求路径不会调用它，
    因此它本身不改变任何行为。

    Args:
        text: 待检查的文本。
        max_ratio: 有效英文词占比超过该阈值即视为混排。

    Returns:
        文本同时含中日韩字符与白名单之外的英文词时返回 True。
    """
    body = text or ""
    if not _CJK_RE.search(body):
        return False

    words = _LATIN_WORD_RE.findall(body)
    if not words:
        return False

    meaningful = [w for w in words if w.lower() not in _LATIN_WHITELIST]
    if not meaningful:
        return False

    cjk_chars = len(_CJK_RE.findall(body))
    if cjk_chars < 4:
        return False

    latin_ratio = len(meaningful) / max(len(meaningful) + cjk_chars / 2, 1)
    return latin_ratio > max_ratio
