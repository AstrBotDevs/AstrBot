import json
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

CORE_LOCALE_DIR = Path(__file__).resolve().parent / "locales"


class Language(str, Enum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


DEFAULT_LANGUAGE = Language.ZH_CN.value


def normalize_language(language: str | Language | None) -> str:
    if isinstance(language, Language):
        return language.value
    if language == Language.EN_US.value:
        return Language.EN_US.value
    return Language.ZH_CN.value


@lru_cache(maxsize=64)
def _load_locale(locale_dir: str, language: str) -> dict[str, Any]:
    locale_path = Path(locale_dir) / f"{language}.json"
    with locale_path.open(encoding="utf-8") as f:
        return json.load(f)


def _resolve_key(data: dict[str, Any], key: str) -> Any:
    value: Any = data
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def t(
    translation_key: str,
    *,
    locale: str | None = None,
    locale_dir: str | Path | None = None,
    **kwargs: Any,
) -> str:
    language = normalize_language(locale)
    resolved_locale_dir = str(locale_dir or CORE_LOCALE_DIR)
    text = _resolve_key(_load_locale(resolved_locale_dir, language), translation_key)

    if text is None and language != DEFAULT_LANGUAGE:
        text = _resolve_key(
            _load_locale(resolved_locale_dir, DEFAULT_LANGUAGE),
            translation_key,
        )
    if not isinstance(text, str):
        return translation_key
    if not kwargs:
        return text
    return text.format(**kwargs)
