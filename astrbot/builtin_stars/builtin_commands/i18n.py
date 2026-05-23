import json
from functools import lru_cache
from pathlib import Path
from typing import Any

LOCALE_DIR = Path(__file__).resolve().parent / "locales"


@lru_cache(maxsize=2)
def _load_locale(language: str) -> dict[str, Any]:
    with (LOCALE_DIR / f"{language}.json").open(encoding="utf-8") as f:
        return json.load(f)


def _resolve_key(data: dict[str, Any], translation_key: str) -> Any:
    value: Any = data
    for part in translation_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def t(context: Any, translation_key: str, **kwargs: Any) -> str:
    text = _resolve_key(_load_locale(context.get_current_language()), translation_key)
    if not isinstance(text, str):
        return translation_key
    if not kwargs:
        return text
    return text.format(**kwargs)
