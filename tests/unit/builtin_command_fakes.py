import json
from pathlib import Path

_I18N_DIR = (
    Path(__file__).parents[2]
    / "astrbot"
    / "builtin_stars"
    / "builtin_commands"
    / ".astrbot-plugin"
    / "i18n"
)
EN_CATALOG = json.loads((_I18N_DIR / "en-US.json").read_text(encoding="utf-8"))
ZH_CATALOG = json.loads((_I18N_DIR / "zh-CN.json").read_text(encoding="utf-8"))


class FakeI18n:
    """Translate builtin command keys from the checked-in catalogs."""

    def __init__(self, *, default_locale: str = "en-US") -> None:
        self.default_locale = default_locale
        self.catalogs = {"en-US": EN_CATALOG, "zh-CN": ZH_CATALOG}

    async def t(self, event, message_key: str, **kwargs) -> str:
        locale = self.default_locale
        getter = getattr(event, "get_extra", None) if event is not None else None
        if callable(getter):
            extra = getter("locale")
            if extra:
                locale = str(extra)
        bundle = self.catalogs.get(locale) or {}
        commands = bundle.get("commands") if isinstance(bundle, dict) else {}
        text = commands.get(message_key) if isinstance(commands, dict) else None
        if text is None and locale != "en-US":
            text = EN_CATALOG.get("commands", {}).get(message_key)
        if text is None:
            return message_key
        if not kwargs:
            return text
        try:
            return text.format(**kwargs)
        except KeyError, IndexError, ValueError:
            return text
