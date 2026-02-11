from __future__ import annotations

import fnmatch
import re

from astrbot.core.star.modality import Modality


class RuleMatcher:
    """规则匹配引擎"""

    def matches(
        self,
        rule: dict | None,
        umo: str,
        modality: set[Modality] | None,
        message_text: str,
    ) -> bool:
        """评估规则是否匹配"""
        if rule is None:
            return True  # 无规则 = 匹配所有

        return self._evaluate(rule, umo, modality, message_text)

    def _evaluate(
        self,
        node: dict,
        umo: str,
        modality: set[Modality] | None,
        text: str,
    ) -> bool:
        node_type = node.get("type")

        if node_type == "and":
            children = node.get("children", [])
            return all(self._evaluate(c, umo, modality, text) for c in children)

        elif node_type == "or":
            children = node.get("children", [])
            return any(self._evaluate(c, umo, modality, text) for c in children)

        elif node_type == "not":
            children = node.get("children", [])
            if children:
                return not self._evaluate(children[0], umo, modality, text)
            return True

        elif node_type == "condition":
            return self._evaluate_condition(
                node.get("condition", {}), umo, modality, text
            )

        return False

    def _evaluate_condition(
        self,
        condition: dict,
        umo: str,
        modality: set[Modality] | None,
        text: str,
    ) -> bool:
        cond_type = condition.get("type")
        value = condition.get("value", "")
        operator = condition.get("operator", "include")

        # 计算基础匹配结果
        result = self._evaluate_condition_value(cond_type, value, umo, modality, text)

        # 根据 operator 决定是否取反
        if operator == "exclude":
            return not result
        return result

    @staticmethod
    def _evaluate_condition_value(
        cond_type: str | None,
        value: str,
        umo: str,
        modality: set[Modality] | None,
        text: str,
    ) -> bool:
        if cond_type == "umo":
            return fnmatch.fnmatch(umo, value)

        elif cond_type == "modality":
            if modality is None:
                return False
            try:
                target = Modality(value)
                return target in modality
            except ValueError:
                return False

        elif cond_type == "text_regex":
            try:
                return bool(re.search(value, text, re.IGNORECASE))
            except re.error:
                return False

        return False


# 单例
rule_matcher = RuleMatcher()
