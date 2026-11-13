"""多语言指令(国际化)相关单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from astrbot.core.config.default import CONFIG_METADATA_3
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.utils.lang_utils import (
    DEFAULT_LANG,
    MultiLangAlias,
    localized_names,
    multi_alias,
    normalize_lang,
    resolve_lang,
)


async def _noop_handler(self, event) -> None:
    pass


class _FakeConfig(dict):
    pass


def _simple_event_zh(message_str: str):
    """构造一个简易消息事件(CommandFilter.filter 使用的字段)。

    注意:waking_check 阶段已剥离 wake_prefix("/"),此处直接传指令名。
    """
    evt = SimpleNamespace()
    evt.is_at_or_wake_command = True
    evt.get_message_str = lambda: message_str
    evt.get_extra = lambda key, default=None: getattr(evt, key, default)
    evt.set_extra = lambda key, value: setattr(evt, key, value)
    evt._astrbot_lang = "zh-CN"
    evt.unified_msg_origin = "test"
    return evt


class TestLangUtils:
    def test_normalize_lang_abbreviations(self):
        assert normalize_lang("zh") == "zh-CN"
        assert normalize_lang("ZH") == "zh-CN"
        assert normalize_lang("en-us") == "en-US"
        assert normalize_lang("ru") == "ru-RU"
        assert normalize_lang("jp") == "ja-JP"
        assert normalize_lang("日本語") == "ja-JP"
        assert normalize_lang("fr") is None
        assert normalize_lang("") is None
        assert normalize_lang(None) is None

    def test_resolve_lang_from_global_config(self):
        # 语言只来自全局配置;非法值回退默认
        assert resolve_lang({"language": "en-US"}) == "en-US"
        assert resolve_lang({"language": "zh"}) == "zh-CN"
        assert resolve_lang({"language": "fr"}) == DEFAULT_LANG
        assert resolve_lang({}) == DEFAULT_LANG
        assert resolve_lang(None) == DEFAULT_LANG

    def test_multi_alias(self):
        aliases = multi_alias(zh="帮助", ru="справка", jp="ヘルプ")
        assert isinstance(aliases, MultiLangAlias)
        assert set(aliases) == {"帮助", "справка", "ヘルプ"}
        assert aliases.lang_map == {
            "帮助": "zh-CN",
            "справка": "ru-RU",
            "ヘルプ": "ja-JP",
        }

    def test_multi_alias_supports_list(self):
        aliases = multi_alias(zh=["帮助", "说明"], en="help")
        assert set(aliases) == {"帮助", "说明", "help"}
        assert aliases.lang_map == {
            "帮助": "zh-CN",
            "说明": "zh-CN",
            "help": "en-US",
        }

    def test_localized_names_filters_stale_aliases(self):
        # 用户重命名/删除别名后,不应再展示已失效的本地化名称
        alias_lang_map = {"天气": "zh-CN", "天気": "ja-JP"}
        assert localized_names(alias_lang_map, ["天气", "天気"]) == {
            "zh-CN": "天气",
            "ja-JP": "天気",
        }
        assert localized_names(alias_lang_map, ["天气"]) == {"zh-CN": "天气"}
        assert localized_names(alias_lang_map, []) == {}

    def test_localized_names_ignores_empty_values(self):
        assert localized_names({"": "zh-CN", "天气": ""}, ["", "天气"]) == {}


class TestLangFilteredAliases:
    def _cfg(self, full_lang_aliases=False):
        return _FakeConfig(
            {
                "language": "zh-CN",
                "platform_settings": {"full_lang_aliases": full_lang_aliases},
            }
        )

    def _filter(self, cmd: str, alias, alias_lang_map=None):
        return CommandFilter(
            cmd,
            alias=alias,
            alias_lang_map=alias_lang_map,
            handler_md=SimpleNamespace(handler=_noop_handler),
        )

    def test_full_lang_off_zh_session_only_zh_alias(self):
        ml = multi_alias(zh="帮助", ru="справка", jp="ヘルプ")
        command_filter = self._filter("help", ml, dict(ml.lang_map))
        cfg = self._cfg(full_lang_aliases=False)
        # zh 会话:主名 + zh 别名可用(前缀已由 waking_check 剥离)
        assert command_filter.filter(_simple_event_zh("帮助"), cfg) is True
        assert command_filter.filter(_simple_event_zh("help"), cfg) is True
        # 非当前语言别名不可用
        assert command_filter.filter(_simple_event_zh("справка"), cfg) is False
        assert command_filter.filter(_simple_event_zh("ヘルプ"), cfg) is False

    def test_full_lang_on_all_aliases(self):
        ml = multi_alias(zh="帮助", ru="справка", jp="ヘルプ")
        command_filter = self._filter("help", ml, dict(ml.lang_map))
        cfg = self._cfg(full_lang_aliases=True)
        for alias in ("帮助", "справка", "ヘルプ"):
            assert command_filter.filter(_simple_event_zh(alias), cfg) is True

    def test_legacy_set_alias_always_active(self):
        # 无语言映射的 set 别名:开关关闭也生效
        command_filter = self._filter("help", {"帮助"})
        cfg = self._cfg(full_lang_aliases=False)
        assert command_filter.filter(_simple_event_zh("帮助"), cfg) is True
        assert command_filter.filter(_simple_event_zh("help"), cfg) is True

    def test_main_command_always_active(self):
        ml = multi_alias(zh="帮助", ru="справка", jp="ヘルプ")
        command_filter = self._filter("help", ml, dict(ml.lang_map))
        cfg = self._cfg(full_lang_aliases=False)
        # zh 会话:主命令 /help 依然可用
        assert command_filter.filter(_simple_event_zh("help"), cfg) is True


class TestFullLangAliasesMetadata:
    """「全语言别名」开关在 WebUI 配置元数据中的注册位置与翻译覆盖。"""

    KEY = "platform_settings.full_lang_aliases"
    LOCALES = ("zh-CN", "en-US", "ru-RU", "ja-JP")

    @staticmethod
    def _count(node, key) -> int:
        """统计 metadata 树中指定键出现的次数。"""
        if not isinstance(node, dict):
            return 0
        return sum(
            (1 if name == key else 0) + TestFullLangAliasesMetadata._count(value, key)
            for name, value in node.items()
        )

    def test_declared_once_under_platform_group(self):
        # 重复注册会让 WebUI 出现两个同名开关,且只有一处有翻译
        assert self._count(CONFIG_METADATA_3, self.KEY) == 1
        others = CONFIG_METADATA_3["platform_group"]["metadata"]["others"]
        assert self.KEY in others["items"]

    def test_translated_in_every_locale(self):
        root = Path(__file__).resolve().parents[1] / "dashboard/src/i18n/locales"
        for locale in self.LOCALES:
            metadata = json.loads(
                (root / locale / "features/config-metadata.json").read_text(
                    encoding="utf-8-sig"
                )
            )
            entry = metadata["platform_group"]["others"]["platform_settings"][
                "full_lang_aliases"
            ]
            assert entry["description"]
            assert entry["hint"]
            # 迁移到 platform_group 后不应在 ai_group 留下第二份
            assert "full_lang_aliases" not in metadata["ai_group"]["others"].get(
                "platform_settings", {}
            )
