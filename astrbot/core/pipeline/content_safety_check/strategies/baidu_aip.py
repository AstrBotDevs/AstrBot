"""使用此功能应该先 pip install baidu-aip"""

from importlib import import_module
from typing import Protocol, TypedDict, TypeGuard, runtime_checkable

from . import ContentSafetyStrategy


class BaiduAipViolation(TypedDict, total=False):
    msg: str | None


def _is_violation_list(value: object) -> TypeGuard[list[BaiduAipViolation]]:
    if not isinstance(value, list):
        return False
    for item in value:
        if isinstance(item, dict):
            for key, message in item.items():
                if (
                    key == "msg"
                    and message is not None
                    and not isinstance(message, str)
                ):
                    return False
        else:
            return False
    return True


@runtime_checkable
class BaiduContentCensor(Protocol):
    def textCensorUserDefined(self, content: str) -> dict[str, object]: ...


class BaiduAipStrategy(ContentSafetyStrategy):
    def __init__(self, appid: str, ak: str, sk: str) -> None:
        censor_factory = import_module("aip").AipContentCensor

        self.app_id = appid
        self.api_key = ak
        self.secret_key = sk
        client = censor_factory(self.app_id, self.api_key, self.secret_key)
        if not isinstance(client, BaiduContentCensor):
            raise TypeError(
                "The installed Baidu SDK does not expose content censorship."
            )
        self.client: BaiduContentCensor = client

    def check(self, content: str) -> tuple[bool, str]:
        res = self.client.textCensorUserDefined(content)
        conclusion_type = res.get("conclusionType")
        if not isinstance(conclusion_type, int):
            return (False, "")
        if conclusion_type == 1:
            return (True, "")
        data = res.get("data")
        conclusion = res.get("conclusion")
        if not _is_violation_list(data) or not isinstance(conclusion, str):
            return (False, "")
        count = len(data)
        parts = [f"Baidu content moderation found {count} violations:\n"]
        for item in data:
            message = item.get("msg")
            if message:
                parts.append(f"{message};\n")
        parts.append("\nEvaluation: " + conclusion)
        info = "".join(parts)
        return (False, info)
