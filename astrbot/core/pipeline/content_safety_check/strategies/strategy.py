from astrbot import logger

from . import ContentSafetyStrategy


class StrategySelector:
    def __init__(self, config: dict) -> None:
        self.enabled_strategies: list[ContentSafetyStrategy] = []
        if config["internal_keywords"]["enable"]:
            from .keywords import KeywordsStrategy

            self.enabled_strategies.append(
                KeywordsStrategy(config["internal_keywords"]["extra_keywords"]),
            )
        if config["baidu_aip"]["enable"]:
            try:
                from .baidu_aip import BaiduAipStrategy
            except ImportError:
                logger.warning("使用百度内容审核应该先 pip install baidu-aip")
                return
            self.enabled_strategies.append(
                BaiduAipStrategy(
                    config["baidu_aip"]["app_id"],
                    config["baidu_aip"]["api_key"],
                    config["baidu_aip"]["secret_key"],
                ),
            )

    def check(self, content: str, locale: str | None = None) -> tuple[bool, str]:
        for strategy in self.enabled_strategies:
            ok, info = strategy.check(content, locale=locale)
            if not ok:
                return False, info
        return True, ""
