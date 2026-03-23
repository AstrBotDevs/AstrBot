"""Internationalization support for AstrBot TUI.

This module provides i18n support with Chinese and English languages.
Language is auto-detected from environment or can be set manually.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache


class Language(Enum):
    """Supported languages."""

    ZH = "zh"
    EN = "en"


# Translation dictionaries
_TRANSLATIONS: dict[Language, dict[str, str]] = {
    Language.ZH: {
        # Welcome messages
        "welcome_title": "欢迎使用 AstrBot TUI",
        "welcome_local_mode": "本地测试模式",
        "welcome_instructions": "输入消息后按 Enter 发送, ESC 或 Ctrl+C 退出",
        "welcome_language": "语言已自动检测为中文",

        # Status messages
        "status_ready": "就绪",
        "status_connected": "已连接",
        "status_disconnected": "未连接",
        "status_processing": "处理中...",
        "status_sending": "发送中...",

        # Message indicators
        "indicator_user": "我",
        "indicator_bot": "AI",
        "indicator_system": "系统",
        "indicator_tool": "工具",
        "indicator_reasoning": "推理",

        # Input hints
        "input_prompt": "> ",
        "input_placeholder": "输入消息...",

        # Error messages
        "error_empty_message": "消息不能为空",
        "error_send_failed": "发送失败",
        "error_connection_lost": "连接已断开",
        "error_unknown": "未知错误",

        # Tool messages
        "tool_using": "使用工具中",
        "tool_completed": "工具执行完成",
        "tool_failed": "工具执行失败",

        # Reasoning messages
        "reasoning_thinking": "思考中...",
        "reasoning_reasoning": "推理中...",
    },
    Language.EN: {
        # Welcome messages
        "welcome_title": "Welcome to AstrBot TUI",
        "welcome_local_mode": "Local Testing Mode",
        "welcome_instructions": "Type your message and press Enter to send. ESC or Ctrl+C to exit.",
        "welcome_language": "Language auto-detected as English",

        # Status messages
        "status_ready": "Ready",
        "status_connected": "Connected",
        "status_disconnected": "Disconnected",
        "status_processing": "Processing...",
        "status_sending": "Sending...",

        # Message indicators
        "indicator_user": "Me",
        "indicator_bot": "AI",
        "indicator_system": "Sys",
        "indicator_tool": "Tool",
        "indicator_reasoning": "Reason",

        # Input hints
        "input_prompt": "> ",
        "input_placeholder": "Type a message...",

        # Error messages
        "error_empty_message": "Message cannot be empty",
        "error_send_failed": "Failed to send",
        "error_connection_lost": "Connection lost",
        "error_unknown": "Unknown error",

        # Tool messages
        "tool_using": "Using tool",
        "tool_completed": "Tool completed",
        "tool_failed": "Tool failed",

        # Reasoning messages
        "reasoning_thinking": "Thinking...",
        "reasoning_reasoning": "Reasoning...",
    },
}


@lru_cache(maxsize=1)
def get_current_language() -> Language:
    """Get the current language based on environment or default.

    Detection order:
    1. ASTRBOT_TUI_LANG environment variable (zh/en)
    2. LANG environment variable (if contains zh/cn)
    3. LC_ALL environment variable (if contains zh/cn)
    4. Default to Chinese (most users are Chinese)
    """
    # Check explicit override first
    explicit = os.environ.get("ASTRBOT_TUI_LANG", "").lower()
    if explicit in ("zh", "en"):
        return Language.ZH if explicit == "zh" else Language.EN

    # Check LANG/LC_ALL for Chinese
    for env_var in ("LANG", "LC_ALL"):
        lang = os.environ.get(env_var, "").lower()
        if "zh" in lang or "cn" in lang:
            return Language.ZH

    # Default to Chinese for broader appeal
    return Language.ZH


def set_language(lang: Language) -> None:
    """Set the current language (clears all translation caches)."""
    get_current_language.cache_clear()
    _t_cached.cache_clear()
    # Set environment variable for persistence
    os.environ["ASTRBOT_TUI_LANG"] = lang.value


@lru_cache(maxsize=128)
def _t_cached(translation_key: str, lang: Language) -> str:
    """Cached translation lookup."""
    return _TRANSLATIONS.get(lang, {}).get(translation_key, translation_key)


def t(translation_key: str) -> str:
    """Get translation for the given key in the current language.

    Args:
        translation_key: Translation key (e.g., "welcome_title", "status_ready")

    Returns:
        Translated string, or the key itself if not found
    """
    return _t_cached(translation_key, get_current_language())


def tr(translation_key: str) -> str:
    """Get translation (alias for t())."""
    return t(translation_key)


class TUITranslations:
    """Translation accessor class for non-function contexts.

    Usage:
        translations = TUITranslations()
        print(translations.WELCOME_TITLE)
    """

    def __getattr__(self, key: str) -> str:
        return t(key)

    def __getitem__(self, key: str) -> str:
        return t(key)

    def get(self, key: str, default: str | None = None) -> str:
        """Get translation with default."""
        result = t(key)
        return default if result == key and default else result


# Convenience instance
translations = TUITranslations()
