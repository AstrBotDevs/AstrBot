"""使用此功能应该先 pip install baidu-aip"""

from typing import TypedDict, TypeGuard

from . import ContentSafetyStrategy


class BaiduAipViolation(TypedDict, total=False):
    msg: str


def _is_violation_list(value: object) -> TypeGuard[list[BaiduAipViolation]]:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        message = item.get("msg")
        if message is not None and not isinstance(message, str):
            return False
    return True


class BaiduAipStrategy(ContentSafetyStrategy):
    def __init__(self, appid: str, ak: str, sk: str) -> None:
        from aip import AipContentCensor  # type: ignore[unresolved-import]

        self.app_id = appid
        self.api_key = ak
        self.secret_key = sk
        self.client = AipContentCensor(self.app_id, self.api_key, self.secret_key)

    def check(self, content: str) -> tuple[bool, str]:
        res = self.client.textCensorUserDefined(content)
        conclusion_type = res.get("conclusionType")
        if not isinstance(conclusion_type, int):
            return False, ""
        if conclusion_type == 1:
            return True, ""

        data = res.get("data")
        conclusion = res.get("conclusion")
        if not _is_violation_list(data) or not isinstance(conclusion, str):
            return False, ""

        count = len(data)
        parts = [f"百度审核服务发现 {count} 处违规:\n"]
        for item in data:
            message = item.get("msg")
            if message:
                parts.append(f"{message};\n")
        parts.append("\n判断结果:" + conclusion)
        info = "".join(parts)
        return False, info
