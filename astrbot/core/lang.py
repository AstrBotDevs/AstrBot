# lang.py
from pathlib import Path
from fluent.runtime import FluentLocalization, FluentResourceLoader
from astrbot.core.utils.astrbot_path import get_astrbot_path


class Lang:
    def __init__(self, locale="zh-cn", files=None):
        self.locale = locale
        self.files = files
        self.load_locale(self.locale, self.files)

    def load_locale(self, locale="zh-cn", files=None):
        # 1. 定位 locales 文件夹
        base_dir = Path(get_astrbot_path()) / "locales"

        # 2. 搜索所有可用的语言文件夹 (作为语言包选项)
        self.available_locales = [d.name for d in base_dir.iterdir() if d.is_dir()]

        # 寻找匹配的 locale (忽略大小写)
        matched_locale = next(
            (l for l in self.available_locales if l.lower() == locale.lower()), locale
        )

        # 3. 默认搜索语言包下所有 .ftl 文件
        if files is None:
            files_set = set()
            for loc in self.available_locales:
                for ftl_file in (base_dir / loc).glob("*.ftl"):
                    files_set.add(ftl_file.name)
            files = list(files_set)

        # 4. 初始化 Loader 和 Localization
        loader = FluentResourceLoader(str(base_dir / "{locale}"))

        # 优先级: 指定的 locale -> 默认 zh-cn (如果存在)
        locales_preference = [matched_locale]
        if "zh-cn" in self.available_locales and matched_locale.lower() != "zh-cn":
            locales_preference.append("zh-cn")

        self._l10n = FluentLocalization(locales_preference, files, loader)

    def __call__(self, key: str, **kwargs) -> str:
        """
        让对象可以直接像函数一样调用：t("key")
        同时利用 **kwargs 简化参数传递
        """
        return self._l10n.format_value(key, kwargs)


t = Lang(locale="en")
