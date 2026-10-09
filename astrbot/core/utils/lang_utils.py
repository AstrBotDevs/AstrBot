"""多语言指令(国际化)工具。

提供:
- 语言代码归一化与解析(全局配置 -> 默认)。
- ``multi_alias``:为插件指令注册多语言别名的便捷 helper。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from astrbot import logger

DEFAULT_LANG = "en-US"
SUPPORTED_LANGS = ("zh-CN", "en-US", "ru-RU", "ja-JP")

# 用户输入归一表:全部小写 -> 规范语言代码
_LANG_NORMALIZE = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_cn": "zh-CN",
    "中文": "zh-CN",
    "简体中文": "zh-CN",
    "en": "en-US",
    "en-us": "en-US",
    "en_us": "en-US",
    "us": "en-US",
    "english": "en-US",
    "ru": "ru-RU",
    "ru-ru": "ru-RU",
    "ru_ru": "ru-RU",
    "russian": "ru-RU",
    "jp": "ja-JP",
    "ja": "ja-JP",
    "ja-jp": "ja-JP",
    "ja_jp": "ja-JP",
    "japanese": "ja-JP",
    "日语": "ja-JP",
    "日本語": "ja-JP",
}


def normalize_lang(value: str | None) -> str | None:
    """归一化用户输入的语言代码,非法返回 ``None``。

    Args:
        value: 用户输入,如 ``"zh"``、``"en-us"``、``"日本語"``。

    Returns:
        规范语言代码(如 ``"zh-CN"``),无法识别时返回 ``None``。
    """
    if not value or not isinstance(value, str):
        return None
    key = value.strip().lower()
    return _LANG_NORMALIZE.get(key)


class MultiLangAlias(set):
    """多语言别名集合,额外携带 ``alias -> lang`` 映射。

    该映射用于"全语言别名"开关关闭时,按当前会话语言过滤别名。
    """

    def __init__(self, langs: dict[str, str | list[str]]) -> None:
        super().__init__()
        self.lang_map: dict[str, str] = {}
        for lang, aliases in langs.items():
            norm = normalize_lang(lang) or lang.lower()
            if isinstance(aliases, (list, tuple, set)):
                items = list(aliases)
            else:
                items = [aliases]
            for alias in items:
                alias = str(alias).strip()
                if not alias:
                    continue
                self.add(alias)
                self.lang_map[alias] = norm


def multi_alias(**langs: str | list[str]) -> MultiLangAlias:
    """为插件指令注册多语言别名。

    Args:
        **langs: 语言缩写(zh/en/ru/jp 等)到指令别名的映射。
            如 ``multi_alias(zh="帮助", ru="справка", jp="ヘルプ")``。

    Returns:
        ``MultiLangAlias`` 集合(可作 ``filter.command(..., alias=...)`` 使用)。

    Example:
        .. code-block:: python

            @filter.command("help", desc="显示帮助", alias=multi_alias(zh="帮助", ru="справка", jp="ヘルプ"))
            async def help_command(self, event): ...
    """
    return MultiLangAlias(langs)


async def get_lang(context: Any, umo: str | None = None) -> str:
    """获取全局语言配置(插件便捷 API)。

    等价于 ``await context.get_lang(umo)``。

    Args:
        context: ``star.Context`` 实例。
        umo: 保留参数(兼容插件调用),不影响结果。

    Returns:
        规范语言代码,如 ``"zh-CN"`` / ``"en-US"`` / ``"ru-RU"`` / ``"ja-JP"``。
    """
    return await context.get_lang(umo)


def resolve_lang(config: dict[str, Any] | None) -> str:
    """按"全局配置 -> 默认"解析当前语言。

    Args:
        config: AstrBot 配置(含 ``language`` 根字段)。

    Returns:
        规范语言代码;无法解析时返回 ``DEFAULT_LANG``。
    """
    norm = normalize_lang((config or {}).get("language"))
    return norm or DEFAULT_LANG


def localized_names(
    alias_lang_map: dict[str, str],
    effective_aliases: Iterable[str],
) -> dict[str, str]:
    """按当前生效的别名过滤出 ``语言代码 -> 本地化指令名``。

    别名可能被用户在 WebUI 中重命名或删除,因此展示用的本地化名称必须与当前
    生效的别名取交集,避免展示已经失效的名称。

    Args:
        alias_lang_map: ``multi_alias`` 注册的 ``别名 -> 语言`` 映射。
        effective_aliases: 当前生效的别名集合。

    Returns:
        语言代码到指令显示名的映射;同一语言存在多个别名时取先出现的。
    """
    aliases = set(effective_aliases)
    names: dict[str, str] = {}
    for alias, lang in alias_lang_map.items():
        if alias and lang and alias in aliases:
            names.setdefault(str(lang), str(alias))
    return names


def validate_global_language(config: dict[str, Any] | None) -> None:
    """启动时校验全局 ``language`` 配置,非法值时记一次 warning(不改写文件)。

    Args:
        config: AstrBot 配置(含 ``language`` 根字段)。
    """
    value = (config or {}).get("language")
    if value is None:
        return
    if normalize_lang(value) is None:
        logger.warning(
            "Global 'language' value '%s' is not recognized; falling back to %s. "
            "Valid values: %s.",
            value,
            DEFAULT_LANG,
            ", ".join(SUPPORTED_LANGS),
        )
