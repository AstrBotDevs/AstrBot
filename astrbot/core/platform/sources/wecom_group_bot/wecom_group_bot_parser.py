"""消息推送机器人回调解析工具"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any

from astrbot.api import logger


_CAMEL_CASE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")


def _camel_to_snake(value: str) -> str:
    if not value:
        return value
    return _CAMEL_CASE_PATTERN.sub("_", value).lower()


def _element_to_data(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()

    data: dict[str, Any] = {}
    for child in children:
        key = _camel_to_snake(child.tag)
        value = _element_to_data(child)
        if key in data:
            existing = data[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                data[key] = [existing, value]
        else:
            data[key] = value
    return data


class WecomGroupBotParser:
    """根据配置解析企业微信消息推送回调"""

    def __init__(self, prefer_format: str = "xml") -> None:
        self.prefer_format = prefer_format.lower()

    def parse(self, payload: str) -> dict[str, Any]:
        text = (payload or "").strip()
        if not text:
            return {}

        try:
            if self._should_parse_as_json(text):
                return self._parse_json(text)
            return self._parse_xml(text)
        except Exception as exc:  # pragma: no cover - defensive log
            logger.error("解析企业微信消息推送机器人（原群机器人）回调失败: %s", exc)
            return {}

    def _should_parse_as_json(self, payload: str) -> bool:
        if self.prefer_format == "json":
            return True
        if self.prefer_format == "xml":
            return payload.startswith("<") is False
        return payload.lstrip().startswith("{")

    def _parse_json(self, payload: str) -> dict[str, Any]:
        data = json.loads(payload)
        return self._normalize_keys(data)

    def _parse_xml(self, payload: str) -> dict[str, Any]:
        root = ET.fromstring(payload)
        parsed: dict[str, Any] = {}
        for child in root:
            parsed[_camel_to_snake(child.tag)] = _element_to_data(child)
        return parsed

    def _normalize_keys(self, data: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in data.items():
            new_key = _camel_to_snake(str(key))
            if isinstance(value, dict):
                normalized[new_key] = self._normalize_keys(value)
            elif isinstance(value, list):
                normalized[new_key] = [
                    self._normalize_keys(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                normalized[new_key] = value
        return normalized
