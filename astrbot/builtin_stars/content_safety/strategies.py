from __future__ import annotations

import abc
import re

from astrbot.core import logger


class ContentSafetyStrategy(abc.ABC):
    @abc.abstractmethod
    def check(self, content: str) -> tuple[bool, str]:
        raise NotImplementedError


class KeywordsStrategy(ContentSafetyStrategy):
    def __init__(self, extra_keywords: list) -> None:
        self.keywords = []
        if extra_keywords is None:
            extra_keywords = []
        self.keywords.extend(extra_keywords)

    def check(self, content: str) -> tuple[bool, str]:
        for keyword in self.keywords:
            if re.search(keyword, content):
                return False, "内容安全检查不通过，匹配到敏感词。"
        return True, ""


class BaiduAipStrategy(ContentSafetyStrategy):
    def __init__(self, appid: str, ak: str, sk: str) -> None:
        from aip import AipContentCensor

        self.app_id = appid
        self.api_key = ak
        self.secret_key = sk
        self.client = AipContentCensor(self.app_id, self.api_key, self.secret_key)

    def check(self, content: str) -> tuple[bool, str]:
        res = self.client.textCensorUserDefined(content)
        if "conclusionType" not in res:
            return False, ""
        if res["conclusionType"] == 1:
            return True, ""
        if "data" not in res:
            return False, ""
        count = len(res["data"])
        parts = [f"百度审核服务发现 {count} 处违规：\n"]
        for i in res["data"]:
            parts.append(f"{i['msg']}；\n")
        parts.append("\n判断结果：" + res["conclusion"])
        info = "".join(parts)
        return False, info


class StrategySelector:
    def __init__(self, config: dict) -> None:
        self.enabled_strategies: list[ContentSafetyStrategy] = []
        if config["internal_keywords"]["enable"]:
            self.enabled_strategies.append(
                KeywordsStrategy(config["internal_keywords"]["extra_keywords"])
            )
        if config["baidu_aip"]["enable"]:
            try:
                self.enabled_strategies.append(
                    BaiduAipStrategy(
                        config["baidu_aip"]["app_id"],
                        config["baidu_aip"]["api_key"],
                        config["baidu_aip"]["secret_key"],
                    )
                )
            except ImportError:
                logger.warning("使用百度内容审核应该先 pip install baidu-aip")

    def check(self, content: str) -> tuple[bool, str]:
        for strategy in self.enabled_strategies:
            ok, info = strategy.check(content)
            if not ok:
                return False, info
        return True, ""
